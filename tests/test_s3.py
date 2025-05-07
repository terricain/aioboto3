import asyncio
import os
import datetime
import tempfile
from io import BytesIO
from unittest.mock import AsyncMock

from botocore.exceptions import ClientError
from boto3.s3.transfer import S3TransferConfig
import aiofiles
import pytest


@pytest.mark.asyncio
async def test_s3_download_file(s3_client, bucket_name, region):
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
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
async def test_s3_download_fileobj(s3_client, bucket_name, region):
    data = b'Hello World\n'
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
    await s3_client.put_object(Bucket=bucket_name, Key='test_file', Body=data)

    fh = BytesIO()
    await s3_client.download_fileobj(bucket_name, 'test_file', fh)

    fh.seek(0)
    assert fh.read() == data


@pytest.mark.asyncio
async def test_s3_download_fileobj_nonseekable_asyncwrite(s3_client, bucket_name, region):
    data = b'Hello World\n'
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
    await s3_client.put_object(Bucket=bucket_name, Key='test_file', Body=data)

    class FileObj:
        def __init__(self) -> None:
            self.data = b''

        async def write(self, b: bytes) -> int:
            self.data += b
            return len(b)

    fh = FileObj()
    await s3_client.download_fileobj(bucket_name, 'test_file', fh)

    assert fh.data == data


@pytest.mark.asyncio
async def test_s3_download_fileobj_nonseekable_syncwrite(s3_client, bucket_name, region):
    data = b'Hello World\n'
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
    await s3_client.put_object(Bucket=bucket_name, Key='test_file', Body=data)

    class FileObj:
        def __init__(self) -> None:
            self.data = b''

        def write(self, b: bytes) -> int:
            self.data += b
            return len(b)

    fh = FileObj()
    await s3_client.download_fileobj(bucket_name, 'test_file', fh)

    assert fh.data == data


@pytest.mark.asyncio
async def test_s3_download_file_404(s3_client, bucket_name, region):
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

    try:
        await s3_client.download_file(bucket_name, 'test_file', '/tmp/somefile')
        assert False, 'Fail, should of raised exception'
    except ClientError as err:
        assert err.response['Error']['Code'] == '404'


@pytest.mark.asyncio
async def test_s3_upload_fileobj(s3_client, bucket_name, region):
    data = b'Hello World\n'
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

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


def _count_running_tasks_excluding_current():
    current = asyncio.current_task()
    return len([t for t in asyncio.all_tasks() if t is not current and not t.done() and not t.cancelled()])


@pytest.mark.asyncio
async def test_s3_upload_fileobj_cancel(s3_client, bucket_name, region):
    before = _count_running_tasks_excluding_current()

    data = b"x" * 10_000_000
    await s3_client.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={'LocationConstraint': region}
    )

    fh = BytesIO(data)

    class SlowFakeFile:
        def __init__(self, fileobj):
            self.fileobj = fileobj

        async def read(self, size):
            await asyncio.sleep(0.3)
            return self.fileobj.read(size)

    slow_file = SlowFakeFile(fh)

    upload_task = asyncio.create_task(
        s3_client.upload_fileobj(
            slow_file,
            bucket_name,
            'test_slow_file'
        )
    )

    await asyncio.sleep(0.3)

    upload_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await upload_task

    after = _count_running_tasks_excluding_current()
    assert before == after, "Task leak detected"


@pytest.mark.asyncio
async def test_s3_upload_empty_fileobj(s3_client, bucket_name, region):
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

    fh = BytesIO(b'')
    fh.seek(0)

    callbacks = []

    def callback(bytes_sent):
        callbacks.append(bytes_sent)

    await s3_client.upload_fileobj(fh, bucket_name, 'test_file', Callback=callback)

    # We should of got 1 callback saying its written 12 bytes
    assert len(callbacks) == 1
    assert callbacks[0] == 0

    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file')
    assert len(await resp['Body'].read()) == 0


@pytest.mark.asyncio
async def test_s3_upload_fileobj_async(s3_client, bucket_name, region):
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

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
async def test_s3_upload_fileobj_async_multipart(s3_client, bucket_name, region):
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

    data = b'Hello World\n'

    tmpfile = tempfile.NamedTemporaryFile(delete=False)
    tmpfile.close()
    async with aiofiles.open(tmpfile.name, mode='wb') as fpw:
        await fpw.write(data)

    async with aiofiles.open(tmpfile.name, mode='rb') as fpr:
        config = S3TransferConfig(multipart_threshold=4)
        await s3_client.upload_fileobj(fpr, bucket_name, 'test_file', Config=config)

    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file')
    assert (await resp['Body'].read()) == data

@pytest.mark.parametrize('checksum_algo', ['CRC32', 'SHA1', None])
@pytest.mark.asyncio
async def test_s3_upload_fileobj_async_multipart_completes_with_checksum_on_parts(
    s3_client, bucket_name, region, checksum_algo):
    """This test verifies that when performing a multipart upload with a checksum algorithm:
    1. Each uploaded part includes the specified checksum type (e.g. CRC32 or SHA1)
    2. The complete_multipart_upload call receives all part checksums correctly

    Note that moto does not use checksums properly, hence unittest.mock was used to
    test the call args of `complete_multipart_upload`
    """
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

    data = b'Hello World\n'

    tmpfile = tempfile.NamedTemporaryFile(delete=False)
    tmpfile.close()
    async with aiofiles.open(tmpfile.name, mode='wb') as fpw:
        await fpw.write(data)

    mock_complete_multipart_upload = AsyncMock()
    s3_client.complete_multipart_upload = mock_complete_multipart_upload
    async with aiofiles.open(tmpfile.name, mode='rb') as fpr:
        config = S3TransferConfig(multipart_threshold=4)

        upload_fileobj_kwargs = {}
        if checksum_algo:
            upload_fileobj_kwargs = {'ExtraArgs': {'ChecksumAlgorithm': checksum_algo}}
        await s3_client.upload_fileobj(fpr, bucket_name, 'test_file', Config=config, **upload_fileobj_kwargs)

    mock_complete_multipart_upload.assert_called_once()
    args, kwargs = mock_complete_multipart_upload.call_args
    parts = kwargs['MultipartUpload']['Parts']
    if checksum_algo:
        expected_checksum_key = 'Checksum' + checksum_algo
        for part in parts:
            assert expected_checksum_key in part
    else:
        for part in parts:
            for key in part:
                assert not key.startswith('Checksum')



@pytest.mark.asyncio
async def test_s3_upload_fileobj_async_slow(s3_client, bucket_name, region):
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

    data = b'Hello World\n'

    class FakeFile:
        def __init__(self, filedata: bytes) -> None:
            self._data = filedata

        async def read(self, numbytes: int) -> bytes:
            result = self._data[:5]
            self._data = self._data[5:]
            return result

    await s3_client.upload_fileobj(FakeFile(data), bucket_name, 'test_file')

    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file')
    assert (await resp['Body'].read()) == data


@pytest.mark.asyncio
async def test_s3_upload_broken_fileobj(s3_client, bucket_name, region):
    class BrokenFile(object):
        def __init__(self, data: bytes):
            self._data = data

        def read(self, count):
            raise IOError("some bad file")

    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

    fh = BrokenFile(b'Hello World\n')
    try:
        await s3_client.upload_fileobj(fh, bucket_name, 'test_file')
    except Exception as err:
        print()

    uploads_resps = await s3_client.list_multipart_uploads(Bucket=bucket_name)
    assert len(uploads_resps.get('Uploads', [])) == 0


@pytest.mark.asyncio
async def test_s3_upload_fileobj_with_transform(s3_client, bucket_name, region):
    data = b'Hello World\n'
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

    fh = BytesIO()
    fh.write(data)
    fh.seek(0)

    processing = lambda x: x.lower()

    await s3_client.upload_fileobj(fh, bucket_name, 'test_file', Processing=processing)

    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file')
    assert (await resp['Body'].read()) == data.lower()


@pytest.mark.asyncio
async def test_s3_upload_file(s3_client, bucket_name, region):
    data = b'Hello World\n'
    filename = '/tmp/aioboto3_temp_s3_upload.txt'
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

    open(filename, 'wb').write(data)

    await s3_client.upload_file(filename, bucket_name, 'test_file')

    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file')
    assert (await resp['Body'].read()) == data


@pytest.mark.asyncio
async def test_s3_copy(s3_client, bucket_name, region):
    data = b'Hello World\n'

    filename = '/tmp/aioboto3_temp_s3_upload.txt'
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

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
async def test_s3_copy_multipart(s3_client, bucket_name, region):
    data = b'Hello World\n'

    filename = '/tmp/aioboto3_temp_s3_upload.txt'
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

    # Upload file
    open(filename, 'wb').write(data)
    await s3_client.upload_file(filename, bucket_name, 'test_file')

    # Copy file
    copy_source = {'Bucket': bucket_name, 'Key': 'test_file'}
    config = S3TransferConfig(multipart_threshold=4)
    await s3_client.copy(copy_source, bucket_name, 'test_file2', Config=config, ExtraArgs={'RequestPayer': 'requester'})

    # Get copied file
    resp = await s3_client.get_object(Bucket=bucket_name, Key='test_file2')
    assert (await resp['Body'].read()) == data


@pytest.mark.asyncio
async def test_s3_copy_from(s3_client, s3_resource, bucket_name, region):
    data = b'Hello World\n'
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

    fh = BytesIO()
    fh.write(data)
    fh.seek(0)

    await s3_client.upload_fileobj(fh, bucket_name, 'test_file')

    resource = await s3_resource.Object(bucket_name, "new_test_file")
    copy_source = bucket_name + "/test_file"
    copy_result = await resource.copy_from(CopySource=copy_source)
    assert 'CopyObjectResult' in copy_result

    resp = await s3_client.get_object(Bucket=bucket_name, Key='new_test_file')
    assert (await resp['Body'].read()) == data


@pytest.mark.asyncio
async def test_s3_resource_objects_all(s3_client, s3_resource, bucket_name, region):
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
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
async def test_s3_resource_objects_filter(s3_client, s3_resource, bucket_name, region):
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
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
async def test_s3_resource_objects_delete(s3_client, s3_resource, bucket_name, region):
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
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
async def test_s3_resource_objects_delete_filter(s3_client, s3_resource, bucket_name, region):
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
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
async def test_s3_object_summary_load(s3_client, s3_resource, bucket_name, region):
    data = b'Hello World\n'
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
    await s3_client.put_object(Bucket=bucket_name, Key='test_file', Body=data)

    obj = await s3_resource.ObjectSummary(bucket_name, 'test_file')
    obj_size = await obj.size
    assert obj_size == len(data)


@pytest.mark.asyncio
async def test_s3_bucket_creation_date(s3_client, s3_resource, bucket_name, region):
    await s3_client.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})

    bucket = await s3_resource.Bucket(bucket_name)
    creation_date = await bucket.creation_date
    assert isinstance(creation_date, datetime.datetime)
