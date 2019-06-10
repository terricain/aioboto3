=====
Usage
=====

Ok as the useage nearly mimics that of boto3, I thought it best just to throw lots of examples at you instead.
The moral of the story is just prefix boto3 stuff with await.

This library "should" work with Python3.3/3.4 but I havent tested it, so try yield from if you want.

Slight differences
------------------

`aioboto3.resource` will return a boto3 like resource object, but it will also have an awaitable `.close()` and also has `__aenter__` and `__aexit__` which
allows you to use the `async with` syntax.


DynamoDB Examples
-----------------

Put an item into a DynamoDB table, then query it using the nice `Key().eq()` abstraction.

.. code-block:: python3

    import asyncio
    import aioboto3
    from boto3.dynamodb.conditions import Key


    async def main():
        async with aioboto3.resource('dynamodb', region_name='eu-central-1') as dynamo_resource:
            table = dynamo_resource.Table('test_table')

            await table.put_item(
                Item={'pk': 'test1', 'col1': 'some_data'}
            )

            result = await table.query(
                KeyConditionExpression=Key('pk').eq('test1')
            )

            print(result['Items'])

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

    # Outputs:
    #  [{'col1': 'some_data', 'pk': 'test1'}]


Use the batch writer to take care of dynamodb writing retries etc...

.. code-block:: python3

    import asyncio
    import aioboto3
    from boto3.dynamodb.conditions import Key


    async def main():
        async with aioboto3.resource('dynamodb', region_name='eu-central-1') as dynamo_resource:
            table = dynamo_resource.Table('test_table')

            # As the default batch size is 25, all of these will be written in one batch
            async with table.batch_writer() as dynamo_writer:
                await dynamo_writer.put_item(Item={'pk': 'test1', 'col1': 'some_data'})
                await dynamo_writer.put_item(Item={'pk': 'test2', 'col1': 'some_data'})
                await dynamo_writer.put_item(Item={'pk': 'test3', 'col1': 'some_data'})
                await dynamo_writer.put_item(Item={'pk': 'test4', 'col1': 'some_data'})
                await dynamo_writer.put_item(Item={'pk': 'test5', 'col1': 'some_data'})

            result = await table.scan()

            print(result['Count'])

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

    # Outputs:
    #  5


The ``batch_writer()`` can take a keyword argument of ``flush_amount`` which will change the desired flush amount and a keyword argument
of ``on_exit_loop_sleep``. The ``on_exit_loop_sleep`` argument will add an async sleep in the flush loop when you exit the context manager.


S3 Examples
-----------

Here are some examples of uploading, checking if an S3 object 
exists and streaming a file from S3, serving via aiohttp.

Upload
------

Here we upload from a file object and stream it from a file descriptor.

.. code-block:: python3

    async def upload(
        suite: str,
        release: str,
        filename: str,
        staging_path: Path,
        bucket: str,
        aws_secret_access_key: str,
        aws_access_key_id: str,
    ) -> str:
        blob_s3_key = f"{suite}/{release}/{filename}"
        if not staging_path.exists():
            LOG.error(
                f"Unable to upload {blob_s3_key} - "
                + f"Staging file {staging_path} does not exist"
            )
            return ""

        async with aioboto3.client(
            "s3",
            aws_secret_access_key=aws_secret_access_key_write,
            aws_access_key_id=aws_access_key_id_write,
        ) as s3:
            try:
                with staging_path.open("rb") as spfp:
                    LOG.info(f"Uploading {blob_s3_key} to s3")
                    await s3.upload_fileobj(spfp, bucket, blob_s3_key)
                    LOG.info(f"Finished Uploading {blob_s3_key} to s3")
            except Exception as e:
                LOG.error(
                    f"Unable to s3 upload {staging_path} to {blob_s3_key}: "
                    + f"{e} ({type(e)})"
                )
                return ""

        return f"s3://{blob_s3_key}"

Object Exists
-------------

Here we check to see if an object already exists

.. code-block:: python3

    async def blob_exists(
        suite: str,
        release: str,
        filename: str,
        bucket: str,
        aws_secret_access_key: str,
        aws_access_key_id: str,
    ) -> bool:
        blob_s3_key = f"{suite}/{release}/{filename}"
        async with aioboto3.client(
            "s3",
            aws_secret_access_key=aws_secret_access_key,
            aws_access_key_id=aws_access_key_id,
        ) as s3:
            object_list = await s3.list_objects_v2(
                Bucket=bucket, Prefix=blob_s3_key
            )
            for obj in object_list.get("Contents", []):
                if obj["Key"] == blob_s3_key:
                    return True

        return False

Streaming Download
------------------

Here we pull the object from S3 in chunks and serve it out to a HTTP request via `aiohttp <https://github.com/aio-libs/aiohttp>`_

.. code-block:: python3

    from aiohttp import web
    from multidict import MultiDict

    async def serve_blob(
        suite: str,
        release: str,
        filename: str,
        bucket: str,
        aws_secret_access_key: str,
        aws_access_key_id: str,
        request: web.Request,
        chunk_size: int = 69
    ) -> web.Response:
        blob_s3_key = f"{suite}/{release}/{filename}"

        if not await blob_exists(suite, release, filename):
            # Not included but generate an error response for the HTTP Restful API
            return self._gen_download_fnf_error(blob_s3_key)

        async with aioboto3.client(
            "s3",
            aws_secret_access_key=aws_secret_access_key,
            aws_access_key_id=aws_access_key_id,
        ) as s3:
            LOG.info(f"Serving {self.bucket} {blob_s3_key}")
            s3_ob = await s3.get_object(Bucket=bucket, Key=blob_s3_key)

            ob_info = s3_ob["ResponseMetadata"]["HTTPHeaders"]
            resp = web.StreamResponse(
                headers=MultiDict(
                    {
                        "CONTENT-DISPOSITION": (
                            f"attachment; filename={file_metadata['filename']}"
                        ),
                        "Content-Type": ob_info["content-type"],
                    }
                )
            )
            resp.content_type = ob_info["content-type"]
            resp.content_length = ob_info["content-length"]
            await resp.prepare(request)

            async with s3_ob["Body"] as stream:
                file_data = await stream.read(chunk_size)
                while file_data:
                    await resp.write(file_data)
                    file_data = await stream.read(chunk_size)

        return resp

Misc
----

As you can see, it also works for standard client connections too.

.. code-block:: python3

    import asyncio
    import aioboto3


    async def main():
        async with aioboto3.client('ssm', region_name='eu-central-1') as ssm_client:
            result = await ssm_client.describe_parameters()

            print(result['Parameters'])


    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

    # Outputs:
    #  []


TODO
----

More examples
