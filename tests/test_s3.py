import os
from io import BytesIO

from botocore.exceptions import ClientError
import pytest


@pytest.mark.asyncio
async def test_s3_download_file(event_loop, s3_client, bucket_name):
    await s3_client.create_bucket(Bucket=bucket_name)
    await s3_client.put_object(Bucket=bucket_name, Key='test_file', Body=b'Hello World\n')

    download_file = '/tmp/aioboto3_temp_s3_download.txt'
    try:
        os.remove(download_file)
    except OSError:
        pass

    callback_called = False

    def download_callback(b):
        nonlocal callback_called
        callback_called = True

    await s3_client.download_file(bucket_name, 'test_file', download_file, Callback=download_callback)

    assert callback_called
    assert os.path.exists(download_file)
    assert os.path.isfile(download_file)

    try:
        os.remove(download_file)
    except OSError:
        pass


@pytest.mark.asyncio
async def test_s3_download_fileobj(event_loop, s3_client, bucket_name):
    data = b'Hello World\n'
    await s3_client.create_bucket(Bucket=bucket_name)
    await s3_client.put_object(Bucket=bucket_name, Key='test_file', Body=data)

    fh = BytesIO()
    await s3_client.download_fileobj(bucket_name, 'test_file', fh)

    fh.seek(0)
    assert fh.read() == data


@pytest.mark.asyncio
async def test_s3_download_file_404(event_loop, s3_client, bucket_name):
    await s3_client.create_bucket(Bucket=bucket_name)

    try:
        await s3_client.download_file(bucket_name, 'test_file', '/tmp/somefile')
        assert False, 'Fail, should of raised exception'
    except ClientError as err:
        assert err.response['Error']['Code'] == '404'


@pytest.mark.asyncio
async def test_s3_upload_fileobj(event_loop, s3_client, bucket_name):
    data = b'Hello World\n'
    await s3_client.create_bucket(Bucket=bucket_name)

    fh = BytesIO()
    fh.write(data)
    fh.seek(0)

    await s3_client.upload_fileobj(fh, bucket_name, 'test_file')

    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file')
    assert (await resp['Body'].read()) == data


@pytest.mark.asyncio
async def test_s3_upload_file(event_loop, s3_client, bucket_name):
    data = b'Hello World\n'
    filename = '/tmp/aioboto3_temp_s3_upload.txt'
    await s3_client.create_bucket(Bucket=bucket_name)

    open(filename, 'wb').write(data)

    await s3_client.upload_file(filename, bucket_name, 'test_file')

    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file')
    assert (await resp['Body'].read()) == data
