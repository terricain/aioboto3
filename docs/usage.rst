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
