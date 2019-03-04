import asyncio
from typing import Optional, Callable, BinaryIO, Dict, Any

from botocore.exceptions import ClientError
from boto3 import utils
from boto3.s3.transfer import S3TransferConfig


def inject_s3_transfer_methods(class_attributes, **kwargs):
    utils.inject_attribute(class_attributes, 'upload_file', upload_file)
    utils.inject_attribute(class_attributes, 'download_file', download_file)
    utils.inject_attribute(class_attributes, 'copy', copy)
    utils.inject_attribute(class_attributes, 'upload_fileobj', upload_fileobj)
    utils.inject_attribute(class_attributes, 'download_fileobj', download_fileobj)


async def download_file(self, Bucket, Key, Filename, ExtraArgs=None, Callback=None, Config=None):
    """Download an S3 object to a file.

    Usage::

        import boto3
        s3 = boto3.resource('s3')
        s3.meta.client.download_file('mybucket', 'hello.txt', '/tmp/hello.txt')

    Similar behavior as S3Transfer's download_file() method,
    except that parameters are capitalized.
    """
    with open(Filename, 'wb') as open_file:
        await download_fileobj(self, Bucket, Key, open_file, ExtraArgs=ExtraArgs, Callback=Callback, Config=Config)


async def download_fileobj(self, Bucket, Key, Fileobj, ExtraArgs=None, Callback=None, Config=None):
    """Download an object from S3 to a file-like object.

    The file-like object must be in binary mode.

    This is a managed transfer which will perform a multipart download in
    multiple threads if necessary.

    Usage::

        import boto3
        s3 = boto3.client('s3')

        with open('filename', 'wb') as data:
            s3.download_fileobj('mybucket', 'mykey', data)

    :type Fileobj: a file-like object
    :param Fileobj: A file-like object to download into. At a minimum, it must
        implement the `write` method and must accept bytes.

    :type Bucket: str
    :param Bucket: The name of the bucket to download from.

    :type Key: str
    :param Key: The name of the key to download from.

    :type ExtraArgs: dict
    :param ExtraArgs: Extra arguments that may be passed to the
        client operation.

    :type Callback: method
    :param Callback: A method which takes a number of bytes transferred to
        be periodically called during the download.

    :type Config: boto3.s3.transfer.TransferConfig
    :param Config: The transfer configuration to be used when performing the
        download.
    """

    try:
        resp = await self.get_object(Bucket=Bucket, Key=Key)
    except ClientError as err:
        if err.response['Error']['Code'] == 'NoSuchKey':
            # Convert to 404 so it looks the same when boto3.download_file fails
            raise ClientError({'Error': {'Code': '404', 'Message': 'Not Found'}}, 'HeadObject')
        raise

    body = resp['Body']

    while True:
        data = await body.read(4096)

        if data == b'':
            break

        if Callback:
            try:
                Callback(len(data))
            except:  # noqa: E722
                pass

        Fileobj.write(data)
        await asyncio.sleep(0.0)


async def upload_fileobj(self, Fileobj: BinaryIO, Bucket: str, Key: str, ExtraArgs: Optional[Dict[str, Any]] = None,
                         Callback: Optional[Callable[[int], None]] = None,
                         Config: Optional[S3TransferConfig] = None):
    """Upload a file-like object to S3.

    The file-like object must be in binary mode.

    This is a managed transfer which will perform a multipart upload in
    multiple threads if necessary.

    Usage::

        import boto3
        s3 = boto3.client('s3')

        with open('filename', 'rb') as data:
            s3.upload_fileobj(data, 'mybucket', 'mykey')

    :type Fileobj: a file-like object
    :param Fileobj: A file-like object to upload. At a minimum, it must
        implement the `read` method, and must return bytes.

    :type Bucket: str
    :param Bucket: The name of the bucket to upload to.

    :type Key: str
    :param Key: The name of the key to upload to.

    :type ExtraArgs: dict
    :param ExtraArgs: Extra arguments that may be passed to the
        client operation.

    :type Callback: method
    :param Callback: A method which takes a number of bytes transferred to
        be periodically called during the upload.

    :type Config: boto3.s3.transfer.TransferConfig
    :param Config: The transfer configuration to be used when performing the
        upload.
    """
    if not ExtraArgs:
        ExtraArgs = {}

    # I was debating setting up a queue etc...
    # If its too slow I'll then be bothered
    multipart_chunksize = 8388608 if Config is None else Config.multipart_chunksize
    io_chunksize = 262144 if Config is None else Config.io_chunksize
    # max_concurrency = 10 if Config is None else Config.max_concurrency
    # max_io_queue = 100 if config is None else Config.max_io_queue

    # Start multipart upload

    resp = await self.create_multipart_upload(Bucket=Bucket, Key=Key, **ExtraArgs)
    upload_id = resp['UploadId']

    part = 0
    parts = []
    running = True
    sent_bytes = 0

    try:
        while running:
            part += 1
            multipart_payload = b''
            while len(multipart_payload) < multipart_chunksize:
                if asyncio.iscoroutinefunction(Fileobj.read):  # handles if we pass in aiofiles obj
                    data = await Fileobj.read(io_chunksize)
                else:
                    data = Fileobj.read(io_chunksize)

                if data == b'':  # End of file
                    running = False
                    break
                multipart_payload += data

            # Submit part to S3
            resp = await self.upload_part(
                Body=multipart_payload,
                Bucket=Bucket,
                Key=Key,
                PartNumber=part,
                UploadId=upload_id
            )
            parts.append({'ETag': resp['ETag'], 'PartNumber': part})
            sent_bytes += len(multipart_payload)
            try:
                Callback(sent_bytes)  # Attempt to call the callback, if it fails, ignore, if no callback, ignore
            except:  # noqa: E722
                pass

        # By now the uploads must have been done
        await self.complete_multipart_upload(
            Bucket=Bucket,
            Key=Key,
            UploadId=upload_id,
            MultipartUpload={'Parts': parts}
        )
    except:  # noqa: E722
        # Cancel multipart upload
        await self.abort_multipart_upload(
            Bucket=Bucket,
            Key=Key,
            UploadId=upload_id
        )

        raise


async def upload_file(self, Filename, Bucket, Key, ExtraArgs=None, Callback=None, Config=None):
    """Upload a file to an S3 object.

    Usage::

        import boto3
        s3 = boto3.resource('s3')
        s3.meta.client.upload_file('/tmp/hello.txt', 'mybucket', 'hello.txt')

    Similar behavior as S3Transfer's upload_file() method,
    except that parameters are capitalized.
    """
    with open(Filename, 'rb') as open_file:
        await upload_fileobj(self, open_file, Bucket, Key, ExtraArgs=ExtraArgs, Callback=Callback, Config=Config)


async def copy(self, CopySource, Bucket, Key, ExtraArgs=None, Callback=None, Config=None):
    assert 'Bucket' in CopySource
    assert 'Key' in CopySource

    try:
        resp = await self.get_object(Bucket=CopySource['Bucket'], Key=CopySource['Key'])
    except ClientError as err:
        if err.response['Error']['Code'] == 'NoSuchKey':
            # Convert to 404 so it looks the same when boto3.download_file fails
            raise ClientError({'Error': {'Code': '404', 'Message': 'Not Found'}}, 'HeadObject')
        raise

    file_obj = resp['Body']

    await self.upload_fileobj(file_obj, Bucket, Key, ExtraArgs=ExtraArgs, Callback=Callback, Config=Config)
