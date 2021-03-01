import os
import tempfile
from io import BytesIO

from botocore.exceptions import ClientError
import aiofiles
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

    callbacks = []

    def callback(bytes_sent):
        callbacks.append(bytes_sent)

    await s3_client.upload_fileobj(fh, bucket_name, 'test_file', Callback=callback)

    # We should of got 1 callback saying its written 12 bytes
    assert len(callbacks) == 1
    assert callbacks[0] == 12

    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file')
    assert (await resp['Body'].read()) == data


@pytest.mark.asyncio
async def test_s3_upload_fileobj_async(event_loop, s3_client, bucket_name):
    await s3_client.create_bucket(Bucket=bucket_name)

    data = b'Hello World\n'

    tmpfile = tempfile.NamedTemporaryFile(delete=False)
    tmpfile.close()
    async with aiofiles.open(tmpfile.name, mode='wb') as fpw:
        await fpw.write(data)

    async with aiofiles.open(tmpfile.name, mode='rb') as fpr:
        await s3_client.upload_fileobj(fpr, bucket_name, 'test_file')

    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file')
    assert (await resp['Body'].read()) == data


@pytest.mark.asyncio
async def test_s3_upload_broken_fileobj(event_loop, s3_client, bucket_name):
    class BrokenFile(object):
        def __init__(self, data: bytes):
            self._data = data

        def read(self, count):
            raise IOError("some bad file")

    await s3_client.create_bucket(Bucket=bucket_name)

    fh = BrokenFile(b'Hello World\n')
    try:
        await s3_client.upload_fileobj(fh, bucket_name, 'test_file')
    except Exception as err:
        print()

    uploads_resps = await s3_client.list_multipart_uploads(Bucket=bucket_name)
    assert len(uploads_resps.get('Uploads', [])) == 0


@pytest.mark.asyncio
async def test_s3_upload_fileobj_with_transform(event_loop, s3_client, bucket_name):
    data = b'Hello World\n'
    await s3_client.create_bucket(Bucket=bucket_name)

    fh = BytesIO()
    fh.write(data)
    fh.seek(0)

    processing = lambda x: x.lower()

    await s3_client.upload_fileobj(fh, bucket_name, 'test_file', Processing=processing)

    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file')
    assert (await resp['Body'].read()) == data.lower()


@pytest.mark.asyncio
async def test_s3_upload_file(event_loop, s3_client, bucket_name):
    data = b'Hello World\n'
    filename = '/tmp/aioboto3_temp_s3_upload.txt'
    await s3_client.create_bucket(Bucket=bucket_name)

    open(filename, 'wb').write(data)

    await s3_client.upload_file(filename, bucket_name, 'test_file')

    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file')
    assert (await resp['Body'].read()) == data


@pytest.mark.asyncio
async def test_s3_copy(event_loop, s3_client, bucket_name):
    data = b'Hello World\n'

    # TODO ============================================= generate largeish file

    filename = '/tmp/aioboto3_temp_s3_upload.txt'
    await s3_client.create_bucket(Bucket=bucket_name)

    # Upload file
    open(filename, 'wb').write(data)
    await s3_client.upload_file(filename, bucket_name, 'test_file')

    # Copy file
    copy_source = {'Bucket': bucket_name, 'Key': 'test_file'}
    await s3_client.copy(copy_source, bucket_name, 'test_file2')

    # Get copied file
    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file2')
    assert (await resp['Body'].read()) == data


@pytest.mark.asyncio
async def test_s3_resource_objects_all(event_loop, s3_client, s3_resource, bucket_name):
    await s3_client.create_bucket(Bucket=bucket_name)
    files_to_create = {'test/file1', 'test2/file1', 'test2/file2'}
    for file in files_to_create:
        await s3_client.put_object(Bucket=bucket_name, Key=file, Body=b'Hello World\n')

    files = []
    bucket = await s3_resource.Bucket(bucket_name)
    async for item in bucket.objects.all():
        files.append(item.key)

    assert len(files) == len(files_to_create)
    assert set(files) == files_to_create


@pytest.mark.asyncio
async def test_s3_resource_objects_filter(event_loop, s3_client, s3_resource, bucket_name):
    await s3_client.create_bucket(Bucket=bucket_name)
    files_to_create = {'test/file1', 'test2/file1', 'test2/file2'}
    for file in files_to_create:
        await s3_client.put_object(Bucket=bucket_name, Key=file, Body=b'Hello World\n')

    files = []
    bucket = await s3_resource.Bucket(bucket_name)
    async for item in bucket.objects.filter(Prefix='test2/'):
        files.append(item.key)

    assert len(files) == 2
    assert all([file.startswith('test2/') for file in files])


@pytest.mark.asyncio
async def test_s3_resource_objects_delete(event_loop, s3_client, s3_resource, bucket_name):
    await s3_client.create_bucket(Bucket=bucket_name)
    files_to_create = {'test/file1', 'test2/file1', 'test2/file2'}
    for file in files_to_create:
        await s3_client.put_object(Bucket=bucket_name, Key=file, Body=b'Hello World\n')

    bucket = await s3_resource.Bucket(bucket_name)
    await bucket.objects.all().delete()

    files = []
    async for item in bucket.objects.all():
        files.append(item.key)

    assert not files


@pytest.mark.asyncio
async def test_s3_resource_objects_delete_filter(event_loop, s3_client, s3_resource, bucket_name):
    await s3_client.create_bucket(Bucket=bucket_name)
    files_to_create = {'test/file1', 'test2/file1', 'test2/file2'}
    for file in files_to_create:
        await s3_client.put_object(Bucket=bucket_name, Key=file, Body=b'Hello World\n')

    bucket = await s3_resource.Bucket(bucket_name)
    await bucket.objects.filter(Prefix='test2/').delete()

    files = []
    async for item in bucket.objects.all():
        files.append(item.key)

    assert len(files) == 1
    assert files[0] == 'test/file1'


@pytest.mark.asyncio
async def test_s3_object_summary_load(event_loop, s3_client, s3_resource, bucket_name):
    data = b'Hello World\n'
    await s3_client.create_bucket(Bucket=bucket_name)
    await s3_client.put_object(Bucket=bucket_name, Key='test_file', Body=data)

    obj = await s3_resource.ObjectSummary(bucket_name, 'test_file')
    obj_size = await obj.size
    assert obj_size == len(data)
