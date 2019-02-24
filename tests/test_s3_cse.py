import pytest
import uuid

import aioboto3.s3.cse as cse


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
