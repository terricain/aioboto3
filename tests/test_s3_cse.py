import base64
import json

import pytest

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
# async def test_cse1(event_loop, s3_moto_patch, kms_moto_patch, region, bucket_name, kms_key_alias):
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
async def test_kms_crypto_context_success(event_loop, s3_moto_patch, kms_moto_patch, region, bucket_name, kms_key_alias):
    kms_client = kms_moto_patch('kms', region_name=region)
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
async def test_kms_crypto_context_decrypt_no_key(event_loop, s3_moto_patch, kms_moto_patch, region, bucket_name, kms_key_alias):
    # Create context
    kms_context = cse.KMSCryptoContext(kms_client_args={'region_name': region})
    await kms_context.setup()

    with pytest.raises(ValueError):
        # Cant get KMS encryption key without key id specified
        await kms_context.get_encryption_aes_key()

    await kms_context.close()


@pytest.mark.asyncio
async def test_kms_cse_encrypt_decrypt_aes_cbc(event_loop, s3_moto_patch, region, bucket_name, s3_key_name):
    s3_client, s3_resource = s3_moto_patch
    s3_client = s3_client('s3', region_name=region)

    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

    aes_key = b'O\x8b\xdc\x92\x87k\x9aJ{m\x82\xb3\x96\xf7\x93]\xa1\xb2Cl\x86<5\xbe\x13\xaf\xa8\x94\xa2O3\xef'
    encrypted_aes_key = b'encrypted_aes_key'
    material_descrition = {'kms_cmk_id': 'alias/cmk_id'}

    kms_crypto_context = cse.MockKMSCryptoContext(aes_key, material_descrition,
                                                  encrypted_aes_key, authenticated_encryption=False)
    s3_cse = cse.S3CSE(kms_crypto_context, s3_client_args={'region_name': region})

    async with s3_cse:
        # Upload file
        await s3_cse.put_object(Body=DATA, Bucket=bucket_name, Key=s3_key_name)

        encrypted_resp = await s3_client.get_object(Bucket=bucket_name, Key=s3_key_name)
        encrypted_resp['Body'] = await encrypted_resp['Body'].read()

        # Check it doesnt start with lorem ipsum
        assert not encrypted_resp['Body'].startswith(DATA[:10])

        # Check metadata for KMS encryption
        assert encrypted_resp['Metadata']['x-amz-cek-alg'] == 'AES/CBC/PKCS5Padding'
        assert encrypted_resp['Metadata']['x-amz-wrap-alg'] == 'kms'
        assert base64.b64decode(encrypted_resp['Metadata']['x-amz-key-v2']) == encrypted_aes_key
        assert encrypted_resp['Metadata']['x-amz-unencrypted-content-length'] == str(len(DATA))
        assert encrypted_resp['Metadata']['x-amz-matdesc'] == json.dumps(material_descrition)
        assert 'x-amz-iv' in encrypted_resp['Metadata']
        assert 'x-amz-tag-len' not in encrypted_resp['Metadata']

        # This is a quick test to ensure decryption works, and resp['Body'] looks like an aiohttp obj
        unencrypted_resp = await s3_cse.get_object(Bucket=bucket_name, Key=s3_key_name)
        unencrypted_resp['Body'] = await unencrypted_resp['Body'].read()

        assert unencrypted_resp['Body'] == DATA

        # Whilst were here, try range get_object with AES/CBC, should fail
        # TODO moto doesnt return Metadata when doing range get
        # with pytest.raises(cse.DecryptError):
        #    await s3_cse.get_object(Bucket=bucket_name, Key=s3_key_name, Range='bytes=20-30')


@pytest.mark.asyncio
async def test_kms_cse_encrypt_decrypt_aes_gcm(event_loop, s3_moto_patch, region, bucket_name, s3_key_name):
    s3_client, s3_resource = s3_moto_patch
    s3_client = s3_client('s3', region_name=region)

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
