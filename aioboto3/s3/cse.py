import asyncio
import base64
import json
import os
import sys
from typing import Dict, Union, IO

import aioboto3
from botocore.config import Config as _Config
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher
from cryptography.hazmat.primitives.ciphers.algorithms import AES
from cryptography.hazmat.primitives.ciphers.modes import CBC
from cryptography.hazmat.primitives.padding import PKCS7
from cryptography.exceptions import InvalidTag


class DecryptError(Exception):
    pass


class S3CSE(object):
    def __init__(self, s3_region: str, kms_region: str, boto_config: _Config = None):
        self._s3_region = s3_region
        self._loop: asyncio.AbstractEventLoop = None
        self._kms_region = kms_region
        self._config = boto_config
        self._backend = default_backend()

        self.kms_client = None
        self.s3_client = None

    async def setup(self):
        if sys.version_info < (3, 7):
            self._loop = asyncio.get_event_loop()
        else:
            self._loop = asyncio.get_running_loop()
        self.kms_client = aioboto3.client('kms', region_name=self._kms_region, config=self._config)
        self.s3_client = aioboto3.client('s3', region_name=self._s3_region, config=self._config)

    async def close(self):
        await self.kms_client.close()
        await self.s3_client.close()

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    # noinspection PyPep8Naming
    async def get_object(self, Bucket: str, Key: str) -> bytes:
        if self.s3_client is None:
            await self.setup()

        s3_response = await self.s3_client.get_object(Bucket=Bucket, Key=Key)
        file_data = await s3_response['Body'].read()
        metadata = s3_response['Metadata']

        if 'x-amz-key' not in metadata and 'x-amz-key-v2' not in metadata:
            # No crypto
            return file_data

        if 'x-amz-key' in metadata:
            # Crypto V1
            return await self._decrypt_v1(file_data, metadata)
        else:
            # Crypto V2
            return await self._decrypt_v2(file_data, metadata)

    async def _decrypt_v1(self, file_data: bytes, metadata: Dict[str, str]) -> bytes:
        raise NotImplementedError('S3 V1 crypto not supported, get me an example and i\'ll add it')

    async def _decrypt_v2(self, file_data: bytes, metadata: Dict[str, str]) -> bytes:
        if metadata['x-amz-wrap-alg'] != 'kms':
            raise NotImplementedError('Non KMS ({0}) client-side decryption supported'.format(metadata['x-amz-wrap-alg']))

        # x-amz-key-v2 - Contains base64 encrypted key
        # x-amz-iv - AES IVs
        # x-amz-matdesc - JSON Description of client-side master key (used as encryption context as is)
        # x-amz-unencrypted-content-length - Unencrypted content length
        # x-amz-wrap-alg - Key wrapping algo, either AESWrap, RSA/ECB/OAEPWithSHA-256AndMGF1Padding or KMS
        # x-amz-cek-alg - AES/GCM/NoPadding or AES/CBC/PKCS5Padding
        # x-amz-tag-len - AEAD Tag length in bits

        kms_data = await self.kms_client.decrypt(
            CiphertextBlob=base64.b64decode(metadata['x-amz-key-v2']),
            EncryptionContext=json.loads(metadata['x-amz-matdesc'])
        )
        aes_key = kms_data['Plaintext']

        iv = base64.b64decode(metadata['x-amz-iv'])

        if metadata.get('x-amz-cek-alg', 'AES/CBC/PKCS5Padding') == 'AES/GCM/NoPadding':
            aesgcm = AESGCM(aes_key)

            try:
                result = await self._loop.run_in_executor(None, lambda: aesgcm.decrypt(iv, file_data, None))
            except InvalidTag:
                raise DecryptError('Failed to decrypt, AEAD tag is incorrect. Possible key or IV are incorrect')

        else:
            # AES/CBC/PKCS5Padding
            aescbc = Cipher(AES(aes_key), CBC(iv), backend=self._backend).decryptor()
            padded_result = await self._loop.run_in_executor(None, lambda: (aescbc.update(file_data) + aescbc.finalize()))

            unpadder = PKCS7(AES.block_size).unpadder()
            result = await self._loop.run_in_executor(None, lambda: (unpadder.update(padded_result) + unpadder.finalize()))

        return result

    async def put_object(self, Body: Union[bytes, IO], Bucket: str, Key: str, KMSKeyId: str, AuthenticatedEncryption: bool = True):
        if self.s3_client is None:
            await self.setup()

        if hasattr(Body, 'read'):
            Body = Body.read()

        metadata = {}

        encryption_context = {'kms_cmk_id': KMSKeyId}
        kms_response = await self.kms_client.generate_data_key(
            KeyId=KMSKeyId,
            EncryptionContext=encryption_context,
            KeySpec='AES_256'
        )

        aes_key = kms_response['Plaintext']

        if AuthenticatedEncryption:
            metadata['x-amz-cek-alg'] = 'AES/GCM/NoPadding'
            metadata['x-amz-tag-len'] = '128'
            iv = os.urandom(12)

            # 16byte 128bit authentication tag forced
            aesgcm = AESGCM(aes_key)

            result = await self._loop.run_in_executor(None, lambda: aesgcm.encrypt(iv, Body, None))

        else:
            metadata['x-amz-cek-alg'] = 'AES/CBC/PKCS5Padding'
            iv = os.urandom(16)

            padder = PKCS7(AES.block_size).padder()
            padded_result = await self._loop.run_in_executor(None, lambda: (padder.update(Body) + padder.finalize()))

            aescbc = Cipher(AES(aes_key), CBC(iv), backend=self._backend).encryptor()
            result = await self._loop.run_in_executor(None, lambda: (aescbc.update(padded_result) + aescbc.finalize()))

        metadata.update({
            'x-amz-unencrypted-content-length': str(len(Body)),
            'x-amz-wrap-alg': 'kms',
            'x-amz-matdesc': json.dumps(encryption_context),
            'x-amz-key-v2': base64.b64encode(kms_response['CiphertextBlob']).decode(),
            'x-amz-iv': base64.b64encode(iv).decode()
        })

        await self.s3_client.put_object(
            Bucket=Bucket,
            Key=Key,
            Body=result,
            Metadata=metadata
        )
