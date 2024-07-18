=====
Usage
=====

Ok as the usage nearly mimics that of boto3, I thought it best just to throw lots of examples at you instead.
The moral of the story is just prefix boto3 stuff with await.

This library "should" work with Python3.3/3.4 but I havent tested it, so try yield from if you want.

Slight differences
------------------

``aioboto3.resource`` will return a boto3 like resource object, but it will also have an awaitable ``.close()`` and also
has ``__aenter__`` and ``__aexit__`` which allows you to use the ``async with`` syntax.

Service resources like ``s3.Bucket`` need to be created using await now, e.g. ``bucket = await s3_resource.Bucket('somebucket')``


DynamoDB Examples
-----------------

Put an item into a DynamoDB table, then query it using the nice ``Key().eq()`` abstraction.

.. code-block:: python3

    import asyncio
    import aioboto3
    from boto3.dynamodb.conditions import Key


    async def main():
        session = aioboto3.Session()
        async with session.resource('dynamodb', region_name='eu-central-1') as dynamo_resource:
            table = await dynamo_resource.Table('test_table')

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
        session = aioboto3.Session()
        async with session.resource('dynamodb', region_name='eu-central-1') as dynamo_resource:
            table = await dynamo_resource.Table('test_table')

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

Here are some examples of uploading and streaming a file from S3, serving via aiohttp.

Upload
~~~~~~

Here we upload from a file object and stream it from a file descriptor.

.. code-block:: python3

    async def upload(
        suite: str,
        release: str,
        filename: str,
        staging_path: Path,
        bucket: str,
    ) -> str:
        blob_s3_key = f"{suite}/{release}/{filename}"

        session = aioboto3.Session()
        async with session.client("s3") as s3:
            try:
                with staging_path.open("rb") as spfp:
                    LOG.info(f"Uploading {blob_s3_key} to s3")
                    await s3.upload_fileobj(spfp, bucket, blob_s3_key)
                    LOG.info(f"Finished Uploading {blob_s3_key} to s3")
            except Exception as e:
                LOG.error(f"Unable to s3 upload {staging_path} to {blob_s3_key}: {e} ({type(e)})")
                return ""

        return f"s3://{blob_s3_key}"

Streaming Download
~~~~~~~~~~~~~~~~~~

Here we pull the object from S3 in chunks and serve it out to a HTTP request via `aiohttp <https://github.com/aio-libs/aiohttp>`_

.. code-block:: python3

    from aiohttp import web
    from multidict import MultiDict


    async def serve_blob(
        suite: str,
        release: str,
        filename: str,
        bucket: str,
        request: web.Request,
        chunk_size: int = 69 * 1024
    ) -> web.StreamResponse:
        blob_s3_key = f"{suite}/{release}/{filename}"

        session = aioboto3.Session()
        async with session.client("s3") as s3:
            LOG.info(f"Serving {bucket} {blob_s3_key}")
            s3_ob = await s3.get_object(Bucket=bucket, Key=blob_s3_key)

            ob_info = s3_ob["ResponseMetadata"]["HTTPHeaders"]
            resp = web.StreamResponse(
                headers=MultiDict(
                    {
                        "CONTENT-DISPOSITION": (
                            f"attachment; filename='{filename}'"
                        ),
                        "Content-Type": ob_info["content-type"],
                    }
                )
            )
            resp.content_type = ob_info["content-type"]
            resp.content_length = ob_info["content-length"]
            await resp.prepare(request)

            stream = s3_ob["Body"]
            while file_data := await stream.read(chunk_size):
                await resp.write(file_data)

        return resp

S3 Resource Objects
~~~~~~~~~~~~~~~~~~~

The S3 Bucket object also works but its methods have been asyncified. E.g.

.. code-block:: python3

    import aioboto3


    async def main():
        session = aioboto3.Session()
        async with session.resource("s3") as s3:

            bucket = await s3.Bucket('mybucket')
            async for s3_object in bucket.objects.all():
                print(s3_object)

            async for s3_object in bucket.objects.filter(Prefix='someprefix/'):
                print(s3_object)

            await bucket.objects.all().delete()

            # or
            await bucket.objects.filter(Prefix='test/').delete()


Misc
----

Clients
~~~~~~~

As you can see, it also works for standard client connections too.

.. code-block:: python3

    import asyncio
    import aioboto3


    async def main():
        session = aioboto3.Session()
        async with session.client('ssm', region_name='eu-central-1') as ssm_client:
            result = await ssm_client.describe_parameters()

            print(result['Parameters'])


    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

    # Outputs:
    #  []

Retries
~~~~~~~

Use **AioConfig**, the async extension of `Config <https://boto3.amazonaws.com/v1/documentation/api/latest/guide/retries.html>`_. Pass it to the client as you would with standard boto3.

The code below will eventually retrieve a list of 20 copies of the organization root response. It prints a list of the number of retries required to get each response.

`ListRoots <https://docs.aws.amazon.com/organizations/latest/APIReference/API_ListRoots.html>`_ is a convenient test function because it only reads data and it has a low `throttling limit <https://docs.aws.amazon.com/organizations/latest/userguide/orgs_reference_limits.html>`_ (per account, 1 per second and 2 burst).

.. code-block:: python3

    import asyncio
    from aioboto3 import Session
    from aiobotocore.config import AioConfig

    try_hard = AioConfig(retries={"max_attempts": 100})

    async def main():
        coro = Session().client("organizations", config=try_hard)
        async with coro as client:
            resp_list = await asyncio.gather(
                *[client.list_roots() for _ in range(20)]
            )
            print([r["ResponseMetadata"]["RetryAttempts"] for r in resp_list])

    asyncio.run(main())

It will return a list with objects like this:

.. code-block:: python3

    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5, 4, 6, 4, 4, 4, 4, 4, 5, 5]


The list is ordered by response timestamp, earliest first. This time the first 10 responses don't retry. The next 10 responses each took between 4 and 6 retries.

The default `max_retries` value is 4. That's not enough for 20 concurrent requests. If you remove the `config` parameter, the code will surely fail like this.

``botocore.errorfactory.TooManyRequestsException: An error occurred (TooManyRequestsException) when calling the ListRoots operation (reached max retries: 4): AWS Organizations can't complete your request because another request is already in progress. Try again later.``

AioHTTP Server Example
~~~~~~~~~~~~~~~~~~~~~~

Since aioboto3 v8.0.0+, ``.client`` and ``.resource`` are now async context managers, so it breaks some normal patterns when used with long
running processes like web servers.

This example creates an AsyncExitStack which essentially does ``async with`` on the context manager retuned by ``.resource``, saves the exit
coroutine so that it can be called later to clean up. If you comment out and run ``_app.on_shutdown.append(shutdown_tasks)``, you'll
receive a warning stating that an AioHTTP session was not closed.


.. code-block:: python3

    """
    contextlib.AsyncExitStack requires python 3.7
    """
    import contextlib

    import aioboto3
    from boto3.dynamodb.conditions import Key
    from aiohttp import web

    routes = web.RouteTableDef()
    session = aioboto3.Session()


    @routes.get('/')
    async def hello(request):

        # request.app['table'] == Table object from boto3 docs
        response = await request.app['table'].query(
            KeyConditionExpression=Key('id').eq('lalalala')
        )

        return web.Response(text=str(response))


    async def startup_tasks(app: web.Application) -> None:
        context_stack = contextlib.AsyncExitStack()
        app['context_stack'] = context_stack

        app['dynamo_resource'] = await context_stack.enter_async_context(
            session.resource('dynamodb', region_name='eu-west-1')
        )
        # By now, app['dynamo_resource'] will have methods like .Table() and list_tables() etc...

        # aioboto3 v8.0.0+ all service resources (aka Table(), Bucket() etc...) need to be awaited
        app['table'] = await app['dynamo_resource'].Table('somedynamodbtablename')


    async def shutdown_tasks(app: web.Application) -> None:
        await app['context_stack'].aclose()
        # By now, app['dynamo_resource'] would be closed


    _app = web.Application()
    _app.add_routes(routes)
    _app.on_startup.append(startup_tasks)
    _app.on_shutdown.append(shutdown_tasks)
    web.run_app(_app, port=8000)


TODO
----

More examples
