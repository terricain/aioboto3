import base64
import json

import pytest

import aioboto3
import aioboto3.s3.cse as cse

# Need big chunk of data for range test
DATA = b'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed efficitur, turpis at molestie molestie, ' \
       b'felis nunc consequat neque, a suscipit ipsum magna a lacus. Nam rhoncus pulvinar dignissim. Sed non sapien porta, ' \
       b'fringilla ipsum vitae, rutrum lorem. Ut mi massa, ultricies eget auctor malesuada, euismod eu nisl. Quisque ' \
       b'pellentesque egestas enim, at finibus nibh semper eget. Maecenas vestibulum massa id elit sagittis dignissim. ' \
       b'Nullam felis ligula, pellentesque a odio quis, sagittis consectetur tortor.\n' \
       b'Cras eget gravida nisl. Nulla nisi ex, facilisis a aliquet maximus, sodales sit amet ligula. Nulla ornare ante ' \
       b'quis varius eleifend. Nunc elementum mi imperdiet, luctus lectus ut, bibendum nunc. Nunc placerat, diam et faucibus ' \
       b'feugiat, lacus mi consequat lectus, in tincidunt nunc ex a massa. Suspendisse potenti. Phasellus congue diam nec ' \
       b'mattis sagittis. Duis hendrerit bibendum dictum. Sed et sapien non urna ultrices vehicula. Curabitur id massa ut ' \
       b'velit placerat tristique ac eu nisi.\n' \
       b'Sed sollicitudin, lectus et dignissim sodales, turpis purus blandit neque, sit amet tempus sem massa id turpis. ' \
       b'Integer porttitor rutrum orci, nec dapibus velit hendrerit vitae. Mauris pellentesque ipsum faucibus laoreet ' \
       b'viverra. Fusce mattis, urna a ullamcorper condimentum, orci lectus pellentesque enim, non vestibulum leo tortor ' \
       b'ut arcu. Donec fringilla gravida elit vel ullamcorper. Proin consectetur id eros in lacinia. Donec pellentesque ' \
       b'nunc vitae viverra condimentum. Maecenas nec lacus elementum, tristique ipsum ut, dapibus velit. Donec tempus quam ' \
       b'cursus, aliquam tellus vel, pretium lacus. Nulla ultrices ex ac felis sagittis malesuada. Aliquam sollicitudin ut ' \
       b'turpis eget laoreet.'


# Waiting for generate_data_key on kms
# https://github.com/spulec/moto/pull/1555

# @pytest.mark.skip(reason="no way of currently testing this")
# @pytest.mark.asyncio
# async def test_cse1(event_loop, moto_patch, region, bucket_name, kms_key_alias):
#     kms_client = kms_moto_patch('kms', region_name=region)
#     s3_client, s3_resource = s3_moto_patch
#     s3_client = s3_client('s3', region_name=region)
#
#     # Setup KMS
#     resp = await kms_client.create_key(KeyUsage='ENCRYPT_DECRYPT', Origin='AWS_KMS')
#     key_id = resp['KeyMetadata']['KeyId']
#
#     await kms_client.create_alias(AliasName=kms_key_alias, TargetKeyId=key_id)
#
#     # Setup bucket
#     await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
#
#     s3_data = str(uuid.uuid4()).encode()
#     s3_file = uuid.uuid4().hex
#
#     async with S3CSE(s3_region=region, kms_region=region) as s3_cse:
#         await s3_cse.put_object(
#             Body=s3_data,
#             Bucket=bucket_name,
#             Key=s3_file,
#             KMSKeyId=kms_key_alias,
#             AuthenticatedEncryption=True
#         )
#
#         s3_raw_object = await s3_client.get_object(Bucket=bucket_name, Key=s3_file)
#         s3_raw_object_data = await s3_raw_object['Body'].read()
#
#         result = await s3_cse.get_object(Bucket=bucket_name, Key=s3_file)
#
#         print()

@pytest.mark.xfail(reason="Waiting for moto to accept PR and release")
@pytest.mark.asyncio
async def test_kms_crypto_context_success(moto_patch, region, bucket_name, kms_key_alias):
    session = aioboto3.Session()

    async with session.client('kms', region_name=region) as kms_client:
        resp = await kms_client.create_key(KeyUsage='ENCRYPT_DECRYPT', Origin='AWS_KMS')
        key_id = resp['KeyMetadata']['KeyId']

        await kms_client.create_alias(AliasName=kms_key_alias, TargetKeyId=key_id)

        # Create context
        kms_context = cse.KMSCryptoContext(kms_key_alias, kms_client_args={'region_name': region})
        assert kms_context.kms_key == kms_key_alias

        await kms_context.setup()
        assert kms_context._kms_client is not None

        aes_key, material_description, encrypted_aes_key = await kms_context.get_encryption_aes_key()

        # Material description should denote what key is used
        assert material_description['kms_cmk_id'] == kms_key_alias

        resp = await kms_client.decrypt(CiphertextBlob=encrypted_aes_key, EncryptionContext=material_description)
        assert aes_key == resp['Plaintext']

        await kms_context.close()


@pytest.mark.asyncio
async def test_kms_crypto_context_decrypt_no_key(moto_patch, region, bucket_name, kms_key_alias):
    # Create context
    kms_context = cse.KMSCryptoContext(kms_client_args={'region_name': region})
    await kms_context.setup()

    with pytest.raises(ValueError):
        # Cant get KMS encryption key without key id specified
        await kms_context.get_encryption_aes_key()

    await kms_context.close()


@pytest.mark.asyncio
async def test_kms_cse_encrypt_decrypt_aes_gcm(moto_patch, region, bucket_name, s3_key_name):
    session = aioboto3.Session()

    async with session.client('s3', region_name=region) as s3_client:
        await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

        aes_key = b'O\x8b\xdc\x92\x87k\x9aJ{m\x82\xb3\x96\xf7\x93]\xa1\xb2Cl\x86<5\xbe\x13\xaf\xa8\x94\xa2O3\xef'
        encrypted_aes_key = b'encrypted_aes_key'
        material_descrition = {'kms_cmk_id': 'alias/cmk_id'}

        kms_crypto_context = cse.MockKMSCryptoContext(aes_key, material_descrition,
                                                      encrypted_aes_key, authenticated_encryption=True)
        s3_cse = cse.S3CSE(kms_crypto_context, s3_client_args={'region_name': region})

        async with s3_cse:
            # Upload file
            await s3_cse.put_object(Body=DATA, Bucket=bucket_name, Key=s3_key_name)

            encrypted_resp = await s3_client.get_object(Bucket=bucket_name, Key=s3_key_name)
            encrypted_resp['Body'] = await encrypted_resp['Body'].read()

            # Check it doesnt start with lorem ipsum
            assert not encrypted_resp['Body'].startswith(DATA[:10])

            # Check metadata for KMS encryption
            assert encrypted_resp['Metadata']['x-amz-cek-alg'] == 'AES/GCM/NoPadding'
            assert encrypted_resp['Metadata']['x-amz-tag-len'] == '128'
            assert encrypted_resp['Metadata']['x-amz-wrap-alg'] == 'kms'
            assert base64.b64decode(encrypted_resp['Metadata']['x-amz-key-v2']) == encrypted_aes_key
            assert encrypted_resp['Metadata']['x-amz-unencrypted-content-length'] == str(len(DATA))
            assert encrypted_resp['Metadata']['x-amz-matdesc'] == json.dumps(material_descrition)
            assert 'x-amz-iv' in encrypted_resp['Metadata']

            # This is a quick test to ensure decryption works, and resp['Body'] looks like an aiohttp obj
            unencrypted_resp = await s3_cse.get_object(Bucket=bucket_name, Key=s3_key_name)
            unencrypted_resp['Body'] = await unencrypted_resp['Body'].read()

            assert unencrypted_resp['Body'] == DATA

            # Test range get
            # TODO moto doesnt return metadata during range get
            # unencrypted_range_resp = await s3_cse.get_object(Bucket=bucket_name, Key=s3_key_name, Range='bytes=500-700')
            # unencrypted_range_resp['Body'] = await unencrypted_range_resp['Body'].read()
            # assert len(unencrypted_range_resp['Body']) == 200
            # assert unencrypted_range_resp['Body'] == DATA[500:700]


@pytest.mark.asyncio
async def test_symmetric_cse_encrypt_decrypt_aes_cbc(moto_patch, region, bucket_name, s3_key_name):
    session = aioboto3.Session()

    async with session.client('s3', region_name=region) as s3_client:
        await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

        aes_key = b'O\x8b\xdc\x92\x87k\x9aJ{m\x82\xb3\x96\xf7\x93]\xa1\xb2Cl\x86<5\xbe\x13\xaf\xa8\x94\xa2O3\xef'

        symmetric_crypto_context = cse.SymmetricCryptoContext(aes_key)
        s3_cse = cse.S3CSE(symmetric_crypto_context, s3_client_args={'region_name': region})

        async with s3_cse:
            # Upload file
            await s3_cse.put_object(Body=DATA, Bucket=bucket_name, Key=s3_key_name)

            encrypted_resp = await s3_client.get_object(Bucket=bucket_name, Key=s3_key_name)
            encrypted_resp['Body'] = await encrypted_resp['Body'].read()

            # Check it doesnt start with lorem ipsum
            assert not encrypted_resp['Body'].startswith(DATA[:10])

            # Check metadata for KMS encryption
            assert len(base64.b64decode(encrypted_resp['Metadata']['x-amz-key'])) == 48
            assert encrypted_resp['Metadata']['x-amz-unencrypted-content-length'] == str(len(DATA))
            assert encrypted_resp['Metadata']['x-amz-matdesc'] == '{}'

            assert 'x-amz-iv' in encrypted_resp['Metadata']
            assert 'x-amz-cek-alg' not in encrypted_resp['Metadata']
            assert 'x-amz-key-v2' not in encrypted_resp['Metadata']
            assert 'x-amz-wrap-alg' not in encrypted_resp['Metadata']
            assert 'x-amz-tag-len' not in encrypted_resp['Metadata']

            # This is a quick test to ensure decryption works, and resp['Body'] looks like an aiohttp obj
            unencrypted_resp = await s3_cse.get_object(Bucket=bucket_name, Key=s3_key_name)
            unencrypted_resp['Body'] = await unencrypted_resp['Body'].read()

            assert unencrypted_resp['Body'] == DATA

            # Whilst were here, try range get_object with AES/CBC, should fail
            # TODO moto doesnt return Metadata when doing range get
            # with pytest.raises(cse.DecryptError):
            #     await s3_cse.get_object(Bucket=bucket_name, Key=s3_key_name, Range='bytes=20-30')


@pytest.mark.asyncio
async def test_asymmetric_cse_encrypt_decrypt_aes_cbc(moto_patch, region, bucket_name, s3_key_name):
    session = aioboto3.Session()

    async with session.client('s3', region_name=region) as s3_client:
        await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

        private_key = b'0\x82\x02w\x02\x01\x000\r\x06\t*\x86H\x86\xf7\r\x01\x01\x01\x05\x00\x04\x82\x02a0\x82\x02]\x02\x01\x00\x02\x81\x81\x00\xbb x \x88x\xa6\x1b\x94\r\x93\x82\x9bU4j\x90//4\x97\xfd\x0c\xdf\xd3\x10\xab}\x99\x19\xe4\xfe\xf1=\x8aM\xca\x06\xa6\xf3\xa5\xce8\x19Q\xcc\x12\x1a\xc2\xc4\xd9w\xeex\xf6\xbc\x1f\xb2u\xb3Z\x0e!fsLJ>\x7fi\xdcc\xb9:\xee2\xf8h5h\x1f\x96\xab\xa4\xfc\x02\x12=D\xde\xde}i~\xe8\xe1y\x16\xc0\xe1\xeb\xca\x16\xbde@+\x00\x9e\xbf\x12\xe7\x0c\xa7#\x88\x80\xa04\xe2M\xc2\x1f\xc2\x8a\xfc\x08M\x02\x03\x01\x00\x01\x02\x81\x81\x00\x92\x1d\x0fO\xaf\xe0-+\xd9\x96$9VZ\xd8\x9b\xe0\xcb\xc7\x1bU\x16UH,\x01\x976r&\xa3\x05b\x8f?\xff\xef\xa0\xf4\x19\xc9\xbc\xd5W\x07\xe4\xc5\xba9\x9d\x05\x85\xbd"\x9c\xdeV\r\xbe\x13\xf6\\\x94<\x99\xa0/\xa8\x8f\xd8\x14\xa3\x88\x88\x1b\xdf\xee\xbb\xaf\xcd\xc7k{\xb2\x9e\x90B\x05)\x7f\xedo\x95\xb9[\xf4\x8fQ\xc0\xee\xd0\xc9\xb9\x1e\xbfP\xe7\x8c\x87\xab\x87\n\xfd\xcb\x04\xe5\x9bEv\x0f)8\x94R;\xf8B\xc1\x02A\x00\xe8D\x96\xdd\x1f\xd4\xd1\xbc\xd2p\xd0\x11\x99pkp\xa9\xb5\xdd:\xa7\xdfn\xd6%\x82\xaeK\xb20\xd2\x03\xf2\r\x06\x1as\xc3_\x95\xf3\xab`>\xaa\x1c\xc1\x19]\xa3\xf2]Q+\xf9\xebi\x9feQ\xd6\xf4\xe3\x11\x02A\x00\xce? \xe6=\xad\x14\xf5\x96PY\xf8\xc1\xaa\xb8y\x9f{\xd8\xf4\x94\x8b}\x9c\\\xec\x10\x7f\xfbD"\xbbd\xa3g\x85\xbd\x97\x18\xd7\xde\x99\xb7\x1dw\xbfwb\xbb\xaa\x01\xaf~\x8aW K\xed;{\xf6t\x99}\x02A\x00\x9b\x13\xf8\x9a\x89?B\x0eM\x7fo\x1c\xe1\x12\xd3Yt\xa6m\xa0U\'tL\\\xdd$\xdc{\x8b\xe7\x1d%F\x96\xd5\xa0\x87H\xd1\xc8\xd0\x9a\xc1\x1c9x\xa0$\nk\xae\xec\x9cm\x10F\x04[\xd4\xc9\xad\xd5\xd1\x02@I\xf9V\x81~I\xa0$\xdd\xbf\x00&:\xc0R\xde<\x97\x9d\x1fLP#\xc3{\x88\xa7\xfa_R\xf6\xea#\x94\x80B\xf5\xd7E\xef\xd7Ef\xeaH\xd3\x01\xad\x06\x06Z\x08i\xe8\x90\x8bb\xf09\xcf\xa2{\xfb\xb9\x02@D\xbaAV\x03\x94,\xc7\xf3/\xbd\xf3I\xc2\x0fAI\xcd\x9e\xa1\xce\xdf\xa7\x19S\x86\xf3\xc2\x854]\xac\xab\xc8\x8f@\x03_-?{>\x1f\xcc\x1a@\xdb\n\xf0v5\xe4tL\xf3\x16kD\xb5\x83L(3\xd2'
        public_key = b'0\x81\x9f0\r\x06\t*\x86H\x86\xf7\r\x01\x01\x01\x05\x00\x03\x81\x8d\x000\x81\x89\x02\x81\x81\x00\xbb x \x88x\xa6\x1b\x94\r\x93\x82\x9bU4j\x90//4\x97\xfd\x0c\xdf\xd3\x10\xab}\x99\x19\xe4\xfe\xf1=\x8aM\xca\x06\xa6\xf3\xa5\xce8\x19Q\xcc\x12\x1a\xc2\xc4\xd9w\xeex\xf6\xbc\x1f\xb2u\xb3Z\x0e!fsLJ>\x7fi\xdcc\xb9:\xee2\xf8h5h\x1f\x96\xab\xa4\xfc\x02\x12=D\xde\xde}i~\xe8\xe1y\x16\xc0\xe1\xeb\xca\x16\xbde@+\x00\x9e\xbf\x12\xe7\x0c\xa7#\x88\x80\xa04\xe2M\xc2\x1f\xc2\x8a\xfc\x08M\x02\x03\x01\x00\x01'

        private_key = cse.AsymmetricCryptoContext.from_der_private_key(private_key)
        public_key = cse.AsymmetricCryptoContext.from_der_public_key(public_key)

        symmetric_crypto_context = cse.AsymmetricCryptoContext(public_key=public_key, private_key=private_key)
        s3_cse = cse.S3CSE(symmetric_crypto_context, s3_client_args={'region_name': region})

        async with s3_cse:
            # Upload file
            await s3_cse.put_object(Body=DATA, Bucket=bucket_name, Key=s3_key_name)

            encrypted_resp = await s3_client.get_object(Bucket=bucket_name, Key=s3_key_name)
            encrypted_resp['Body'] = await encrypted_resp['Body'].read()

            # Check it doesnt start with lorem ipsum
            assert not encrypted_resp['Body'].startswith(DATA[:10])

            # Check metadata for KMS encryption
            assert len(base64.b64decode(encrypted_resp['Metadata']['x-amz-key'])) == 128  # 1024bit key
            assert encrypted_resp['Metadata']['x-amz-unencrypted-content-length'] == str(len(DATA))
            assert encrypted_resp['Metadata']['x-amz-matdesc'] == '{}'

            assert 'x-amz-iv' in encrypted_resp['Metadata']
            assert 'x-amz-cek-alg' not in encrypted_resp['Metadata']
            assert 'x-amz-key-v2' not in encrypted_resp['Metadata']
            assert 'x-amz-wrap-alg' not in encrypted_resp['Metadata']
            assert 'x-amz-tag-len' not in encrypted_resp['Metadata']

            # This is a quick test to ensure decryption works, and resp['Body'] looks like an aiohttp obj
            unencrypted_resp = await s3_cse.get_object(Bucket=bucket_name, Key=s3_key_name)
            unencrypted_resp['Body'] = await unencrypted_resp['Body'].read()

            assert unencrypted_resp['Body'] == DATA

            # Whilst were here, try range get_object with AES/CBC, should fail
            # TODO moto doesnt return Metadata when doing range get
            # with pytest.raises(cse.DecryptError):
            #     await s3_cse.get_object(Bucket=bucket_name, Key=s3_key_name, Range='bytes=20-30')


def test_adjust_iv():
    iv = b'+^\xa5\x9a\xe1\x97p\x0f)\xf2\x10C'
    after = b'+^\xa5\x9a\xe1\x97p\x0f)\xf2\x10C\x00\x00\x00\x02'
    actual = cse._adjust_iv_for_range(iv, 0)

    assert after == actual


def test_increment_blocks():
    before = b'+^\xa5\x9a\xe1\x97p\x0f)\xf2\x10C\x00\x00\x00\x01'
    after = b'+^\xa5\x9a\xe1\x97p\x0f)\xf2\x10C\x00\x00\x00\x02'

    actual = cse._increment_blocks(before, 1)

    assert after == actual


def test_compute_j0():
    before = b'+^\xa5\x9a\xe1\x97p\x0f)\xf2\x10C'
    after = b'+^\xa5\x9a\xe1\x97p\x0f)\xf2\x10C\x00\x00\x00\x02'

    actual = cse._compute_j0(before)

    assert after == actual


def test_get_adjusted_crypto_range():
    actual_start, actual_end = cse._get_adjusted_crypto_range(3, 64)

    assert actual_start == 0
    assert actual_end == 256


# Testing max size clamping
@pytest.mark.parametrize('input,expected', [
    (0, 256),
    (257, 512),
    (9223372036854775807, 9223372036854775807),
])
def test_get_cipher_block_upper_bound(input, expected):
    result = cse._get_cipher_block_upper_bound(input)

    assert result == expected


# Testing min size clamping
@pytest.mark.parametrize('input,expected', [
    (0, 0),
    (20, 0),
    (257, 128),
    (510, 256),
])
def test_get_cipher_block_lower_bound(input, expected):
    result = cse._get_cipher_block_lower_bound(input)

    assert result == expected
