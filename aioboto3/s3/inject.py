import asyncio
import aiofiles
import inspect
import logging
from io import BytesIO
from typing import Optional, Callable, BinaryIO, Dict, Any, Union, Tuple

from botocore.exceptions import ClientError
from boto3 import utils
from boto3.s3.transfer import S3TransferConfig
from boto3.s3.inject import bucket_upload_file, bucket_download_file, bucket_copy, bucket_upload_fileobj, bucket_download_fileobj

logger = logging.getLogger(__name__)


def inject_s3_transfer_methods(class_attributes, **kwargs):
    utils.inject_attribute(class_attributes, 'upload_file', upload_file)
    utils.inject_attribute(class_attributes, 'download_file', download_file)
    utils.inject_attribute(class_attributes, 'copy', copy)
    utils.inject_attribute(class_attributes, 'upload_fileobj', upload_fileobj)
    utils.inject_attribute(
        class_attributes, 'download_fileobj', download_fileobj
    )


def inject_object_summary_methods(class_attributes, **kwargs):
    utils.inject_attribute(class_attributes, 'load', object_summary_load)


def inject_bucket_methods(class_attributes, **kwargs):
    utils.inject_attribute(class_attributes, 'load', bucket_load)
    utils.inject_attribute(class_attributes, 'upload_file', bucket_upload_file)
    utils.inject_attribute(
        class_attributes, 'download_file', bucket_download_file
    )
    utils.inject_attribute(class_attributes, 'copy', bucket_copy)
    utils.inject_attribute(
        class_attributes, 'upload_fileobj', bucket_upload_fileobj
    )
    utils.inject_attribute(
        class_attributes, 'download_fileobj', bucket_download_fileobj
    )


async def object_summary_load(self, *args, **kwargs):
    response = await self.meta.client.head_object(
        Bucket=self.bucket_name, Key=self.key
    )
    if 'ContentLength' in response:
        response['Size'] = response.pop('ContentLength')
    self.meta.data = response


async def download_file(
    self, Bucket: str, Key: str, Filename: str, ExtraArgs=None, Callback=None, Config=None
):
    """Download an S3 object to a file asynchronously.

    Usage::

        import aioboto3
        s3 = aioboto3.resource('s3')
        await s3.meta.client.download_file('mybucket', 'hello.txt', '/tmp/hello.txt')

    Similar behaviour as S3Transfer's download_file() method,
    except that parameters are capitalised.
    """
    async with aiofiles.open(Filename, 'wb') as fileobj:
        await download_fileobj(
            self,
            Bucket,
            Key,
            fileobj,
            ExtraArgs=ExtraArgs,
            Callback=Callback,
            Config=Config
        )


async def _download_part(self, bucket: str, key: str, headers, start, file: Union[BytesIO, Any, None], semaphore, callback=None, io_queue: Optional[asyncio.Queue] = None) -> Union[None, Tuple[int, bytes]]:
    async with semaphore:  # limit number of concurrent downloads
        response = await self.get_object(
            Bucket=bucket, Key=key, Range=headers['Range']
        )
        content = await response['Body'].read()

        # If stream is not seekable, return it so it can be queued up to be written
        if io_queue:
            await io_queue.put((start, content))
        else:
            # Check if it's aiofiles file
            if inspect.iscoroutinefunction(file.seek) and inspect.iscoroutinefunction(file.write):
                await file.seek(start)
                await file.write(content)
            else:
                # Fallback to synchronous operations for file objects that are not async
                file.seek(start)
                file.write(content)

        # Call the wrapper callback with the number of bytes written, if provided
        if callback:
            try:
                callback(len(content))
            except:  # noqa: E722
                pass


async def download_fileobj(
    self, Bucket, Key, Fileobj, ExtraArgs=None, Callback=None, Config=None
):
    """Download an object from S3 to a file-like object.

    The file-like object must be in binary mode.

    This is a managed transfer which will perform a multipart download
    with asyncio if necessary.

    Usage::

        import boto3
        s3 = boto3.client('s3')

        async with aiofiles.open('filename', 'wb') as data:
            await s3.download_fileobj('mybucket', 'mykey', data)

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
        if ExtraArgs is None:
            ExtraArgs = {}
        # Get object metadata to determine the total size
        head_response = await self.head_object(Bucket=Bucket, Key=Key, **ExtraArgs)
    except ClientError as err:
        if err.response['Error']['Code'] == 'NoSuchKey':
            # Convert to 404 so it looks the same when boto3.download_file fails
            raise ClientError({'Error': {'Code': '404', 'Message': 'Not Found'}}, 'HeadObject')
        raise

    # Semaphore to limit the number of concurrent downloads
    semaphore = asyncio.Semaphore(10)

    # Size of each part (8MB)
    part_size = 8 * 1024 * 1024

    total_size = head_response['ContentLength']
    total_parts = (total_size + part_size - 1) // part_size

    # Keep track of total downloaded bytes
    total_downloaded = 0

    def wrapper_callback(bytes_transferred):
        nonlocal total_downloaded
        total_downloaded += bytes_transferred
        if Callback:
            try:
                Callback(total_downloaded)
            except:  # noqa: E722
                pass

    is_seekable = inspect.isfunction(Fileobj.seek) or inspect.iscoroutinefunction(Fileobj.seek)

    # This'll have around `semaphore` length items, somewhat more if writing is slow
    # TODO add limits so we dont fill up this list n blow out ram
    io_list = []
    io_queue = asyncio.Queue()

    async def queue_reader():
        is_async = inspect.iscoroutinefunction(Fileobj.write)

        written_pos = 0
        while written_pos < total_size:
            io_list.append(await io_queue.get())

            # Stuff might be out of order in io_list
            # so spin until there's nothing to queue off
            done_nothing = False
            while not done_nothing:
                done_nothing = True

                for chunk_start, data in io_list:
                    if chunk_start == written_pos:
                        if is_async:
                            await Fileobj.write(data)
                        else:
                            Fileobj.write(data)
                    written_pos += len(data)
                    done_nothing = False

    queue_reader_future = None
    if not is_seekable:
        queue_reader_future = asyncio.ensure_future(queue_reader())

    try:
        tasks = []
        for i in range(total_parts):
            start = i * part_size
            end = min(
                start + part_size, total_size
            )  # Ensure we don't go beyond the total size
            # Range headers, start at 0 so end which would be total_size, minus 1 = 0 indexed.
            headers = {'Range': f'bytes={start}-{end - 1}'}
            # Create a task for each part download
            tasks.append(
                _download_part(self, Bucket, Key, headers, start, Fileobj, semaphore, wrapper_callback, io_queue if not is_seekable else None)
            )

        # Run all the download tasks concurrently
        await asyncio.gather(*tasks)

        if queue_reader_future:
            await queue_reader_future

        logger.info(f'Downloaded file from {Bucket}/{Key}')

    except ClientError as e:
        raise Exception(
            f"Couldn't download file from {Bucket}/{Key}"
        ) from e


async def upload_fileobj(
    self,
    Fileobj: BinaryIO,
    Bucket: str,
    Key: str,
    ExtraArgs: Optional[Dict[str, Any]] = None,
    Callback: Optional[Callable[[int], None]] = None,
    Config: Optional[S3TransferConfig] = None,
    Processing: Callable[[bytes], bytes] = None
):
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

    :type Processing: method
    :param Processing: A method which takes a bytes buffer and convert it
        by custom logic.
    """
    kwargs = ExtraArgs or {}

    # I was debating setting up a queue etc...
    # If its too slow I'll then be bothered
    multipart_chunksize = 8388608 if Config is None else Config.multipart_chunksize
    io_chunksize = 262144 if Config is None else Config.io_chunksize
    max_concurrency = 10 if Config is None else Config.max_request_concurrency
    max_io_queue = 100 if Config is None else Config.max_io_queue_size

    # Start multipart upload
    resp = await self.create_multipart_upload(Bucket=Bucket, Key=Key, **kwargs)
    upload_id = resp['UploadId']
    finished_parts = []
    expected_parts = 0
    io_queue = asyncio.Queue(maxsize=max_io_queue)
    exception_event = asyncio.Event()
    exception = None
    sent_bytes = 0

    async def uploader() -> int:
        nonlocal sent_bytes
        nonlocal exception
        uploaded_parts = 0

        # Loop whilst no other co-routine has raised an exception
        while not exception:
            try:
                part_args = await io_queue.get()
            except asyncio.CancelledError:
                break

            # Submit part to S3
            try:
                resp = await self.upload_part(**part_args)
            except Exception as err:
                # Set the main exception variable to the current exception, trigger the exception event
                exception = err
                exception_event.set()
                # Exit the coro
                break

            # Success, add the result to the finished_parts, increment the sent_bytes
            finished_parts.append({'ETag': resp['ETag'], 'PartNumber': part_args['PartNumber']})
            current_bytes = len(part_args['Body'])
            sent_bytes += current_bytes
            uploaded_parts += 1
            logger.debug('Uploaded part to S3')

            # Call the callback, if it blocks then not good :/
            if Callback:
                try:
                    Callback(current_bytes)
                except:  # noqa: E722
                    pass

            # Mark task as done so .join() will work later on
            io_queue.task_done()

        # For testing return number of parts uploaded
        return uploaded_parts

    async def file_reader() -> None:
        nonlocal expected_parts
        nonlocal exception
        part = 0
        eof = False
        while not exception and not eof:
            part += 1
            multipart_payload = bytearray()
            loop_counter = 0
            while len(multipart_payload) < multipart_chunksize:
                try:
                    # Handles if .read() returns anything that can be awaited
                    data_chunk = Fileobj.read(io_chunksize)
                    if inspect.isawaitable(data_chunk):
                        # noinspection PyUnresolvedReferences
                        data = await data_chunk
                    else:
                        data = data_chunk
                        await asyncio.sleep(0.0)  # Yield to the eventloop incase .read() took ages
                except Exception as err:
                    # Caught some random exception whilst reading from a file
                    exception = err
                    exception_event.set()

                    # shortcircuit upload logic
                    eof = True
                    multipart_payload = bytearray()
                    break

                if data == b'' and loop_counter > 0:  # End of file, handles uploading empty files
                    eof = True
                    break
                multipart_payload += data
                loop_counter += 1

            # If file has ended but chunk has some data in it, upload it,
            # else if file ended just after a chunk then exit
            # if the first part is b'' then upload it as we're uploading an empty
            # file
            if not multipart_payload and part != 1:
                break

            if Processing:
                multipart_payload = Processing(multipart_payload)

            await io_queue.put({'Body': multipart_payload, 'Bucket': Bucket, 'Key': Key,
                                'PartNumber': part, 'UploadId': upload_id})
            logger.debug('Added part to io_queue')
            expected_parts += 1

    file_reader_future = asyncio.ensure_future(file_reader())
    futures = [asyncio.ensure_future(uploader()) for _ in range(0, max_concurrency)]

    # Wait for file reader to finish
    await file_reader_future
    # So by this point all of the file is read and in a queue

    # wait for either io queue is finished, or an exception has been raised
    _, pending = await asyncio.wait(
        {asyncio.create_task(io_queue.join()), asyncio.create_task(exception_event.wait())},
        return_when=asyncio.FIRST_COMPLETED
    )

    if exception_event.is_set() or len(finished_parts) != expected_parts:
        # An exception during upload or for some reason the finished parts dont match the expected parts, cancel upload
        await self.abort_multipart_upload(Bucket=Bucket, Key=Key, UploadId=upload_id)
        # Raise exception later after we've disposed of the pending co-routines
    else:
        # All io chunks from the queue have been successfully uploaded
        try:
            # Sort the finished parts as they must be in order
            finished_parts.sort(key=lambda item: item['PartNumber'])

            await self.complete_multipart_upload(
                Bucket=Bucket,
                Key=Key,
                UploadId=upload_id,
                MultipartUpload={'Parts': finished_parts}
            )
        except Exception as err:
            # We failed to complete the upload, try and abort, then return the orginal error
            exception = err
            try:
                await self.abort_multipart_upload(Bucket=Bucket, Key=Key, UploadId=upload_id)
            except:
                pass

    # Close either the Queue.join() coro, or the event.wait() coro
    for coro in pending:
        if not coro.done():
            coro.cancel()
            try:
                await coro
            except:
                pass

    # Cancel any remaining futures, though if successful they'll be done
    cancelled = []
    for future in futures:
        if not future.done():
            future.cancel()
            cancelled.append(future)
        else:
            uploaded_parts = future.result()
            logger.debug('Future uploaded {0} parts'.format(uploaded_parts))
    if cancelled:
        for uploaded_parts in await asyncio.gather(*cancelled, return_exceptions=True):
            if isinstance(uploaded_parts, int):
                logger.debug('Future uploaded {0} parts'.format(uploaded_parts))

    # Raise an exception now after everythings cleaned up
    if exception:
        raise exception


async def upload_file(
    self, Filename, Bucket, Key, ExtraArgs=None, Callback=None, Config=None
):
    """Upload a file to an S3 object.

    Usage::

        import boto3
        s3 = boto3.resource('s3')
        s3.meta.client.upload_file('/tmp/hello.txt', 'mybucket', 'hello.txt')

    Similar behavior as S3Transfer's upload_file() method,
    except that parameters are capitalized.
    """
    with open(Filename, 'rb') as open_file:
        await upload_fileobj(
            self,
            open_file,
            Bucket,
            Key,
            ExtraArgs=ExtraArgs,
            Callback=Callback,
            Config=Config
        )


async def copy(
    self, CopySource, Bucket, Key, ExtraArgs=None, Callback=None, SourceClient=None, Config=None
):
    assert 'Bucket' in CopySource
    assert 'Key' in CopySource

    if SourceClient is None:
        SourceClient = self

    if ExtraArgs is None:
        ExtraArgs = {}

    try:
        resp = await SourceClient.get_object(
            Bucket=CopySource['Bucket'], Key=CopySource['Key'], **ExtraArgs
        )
    except ClientError as err:
        if err.response['Error']['Code'] == 'NoSuchKey':
            # Convert to 404 so it looks the same when boto3.download_file fails
            raise ClientError({'Error': {'Code': '404', 'Message': 'Not Found'}}, 'HeadObject')
        raise

    file_obj = resp['Body']

    await self.upload_fileobj(
        file_obj,
        Bucket,
        Key,
        ExtraArgs=ExtraArgs,
        Callback=Callback,
        Config=Config
    )


async def bucket_load(self, *args, **kwargs):
    """
    Calls s3.Client.list_buckets() to update the attributes of the Bucket
    resource.
    """
    # The docstring above is phrased this way to match what the autogenerated
    # docs produce.

    # We can't actually get the bucket's attributes from a HeadBucket,
    # so we need to use a ListBuckets and search for our bucket.
    # However, we may fail if we lack permissions to ListBuckets
    # or the bucket is in another account. In which case, creation_date
    # will be None.
    self.meta.data = {}
    try:
        response = await self.meta.client.list_buckets()
        for bucket_data in response['Buckets']:
            if bucket_data['Name'] == self.name:
                self.meta.data = bucket_data
                break
    except ClientError as e:
        if not e.response.get('Error', {}).get('Code') == 'AccessDenied':
            raise
