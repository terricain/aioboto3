======================================
AWS Chalice Integration (EXPERIMENTAL)
======================================

How it works
------------

Using ``aioboto3.experimental.async_chalice.AsyncChalice`` as the main app entrypoint for a chalice app adds some shims in so
that you can use ``async def`` functions with HTTP routes normally. Additionally a ``app.aioboto3`` contains an aioboto3 Session
object which can be used to get s3 clients etc... Passing in a session to ``AsyncChalice`` overrides the default empty session.

Chalice has some interesting quirks to how it works, most notably the eventloop can disappear between invocations so storing references
to anything which could store the current event loop is not recommended. Because of this, caching aioboto3 clients and resources is not
a good idea and realistically because this code is designed to be ran in a lambda, said caching buys you little.

The Chalice integration is very experimental, until someone runs it for a while and has faith in it, I would not recommend using this for
anything critical.

Example
-------

.. code-block:: python

    from aioboto3.experimental.async_chalice import AsyncChalice

    app = AsyncChalice(app_name='testclient')


    @app.route('/hello/{name}')
    async def hello(name):
        return {'hello': name}


    @app.route('/list_buckets')
    async def get_list_buckets():
        async with app.aioboto3.client("s3") as s3:
            resp = await s3.list_buckets()

        return {"buckets": [bucket['Name'] for bucket in resp['Buckets']]}
