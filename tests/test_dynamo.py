import asyncio

from boto3.dynamodb.conditions import Key
import pytest


@pytest.mark.asyncio
async def test_dynamo_resource_query(dynamodb_resource, random_table_name):

    await dynamodb_resource.create_table(
        TableName=random_table_name,
        KeySchema=[{'AttributeName': 'pk', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'pk', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 123, 'WriteCapacityUnits': 123}
    )

    table = await dynamodb_resource.Table(random_table_name)
    await table.put_item(
        Item={'pk': 'test', 'test_col1': 'col'}
    )

    result = await table.query(
        KeyConditionExpression=Key('pk').eq('test')
    )
    assert result['Count'] == 1


@pytest.mark.asyncio
async def test_dynamo_resource_put(dynamodb_resource, random_table_name):
    await dynamodb_resource.create_table(
        TableName=random_table_name,
        KeySchema=[{'AttributeName': 'pk', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'pk', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 123, 'WriteCapacityUnits': 123}
    )

    table = await dynamodb_resource.Table(random_table_name)
    await table.put_item(
        Item={'pk': 'test', 'test_col1': 'col'}
    )

    result = await table.scan()
    assert result['Count'] == 1


@pytest.mark.asyncio
async def test_dynamo_resource_batch_write_flush_on_exit_context(dynamodb_resource, random_table_name):
    await dynamodb_resource.create_table(
        TableName=random_table_name,
        KeySchema=[{'AttributeName': 'pk', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'pk', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 123, 'WriteCapacityUnits': 123}
    )

    table = await dynamodb_resource.Table(random_table_name)
    async with table.batch_writer() as dynamo_writer:
        await dynamo_writer.put_item(Item={'pk': 'test', 'test_col1': 'col'})

    result = await table.scan()
    assert result['Count'] == 1


@pytest.mark.asyncio
async def test_dynamo_resource_batch_write_flush_amount(dynamodb_resource, random_table_name):
    await dynamodb_resource.create_table(
        TableName=random_table_name,
        KeySchema=[{'AttributeName': 'pk', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'pk', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 2, 'WriteCapacityUnits': 1}
    )

    table = await dynamodb_resource.Table(random_table_name)
    async with table.batch_writer(flush_amount=5, on_exit_loop_sleep=0.1) as dynamo_writer:
        await dynamo_writer.put_item(Item={'pk': 'test1', 'test_col1': 'col'})

        result = await table.scan()
        assert result['Count'] == 0

        await dynamo_writer.put_item(Item={'pk': 'test2', 'test_col1': 'col'})
        await dynamo_writer.put_item(Item={'pk': 'test3', 'test_col1': 'col'})
        await dynamo_writer.put_item(Item={'pk': 'test4', 'test_col1': 'col'})
        await dynamo_writer.put_item(Item={'pk': 'test5', 'test_col1': 'col'})
        await dynamo_writer.put_item(Item={'pk': 'test6', 'test_col1': 'col'})
        await dynamo_writer.put_item(Item={'pk': 'test7', 'test_col1': 'col'})
        await dynamo_writer.put_item(Item={'pk': 'test8', 'test_col1': 'col'})
        await dynamo_writer.put_item(Item={'pk': 'test9', 'test_col1': 'col'})

        # Flush should of happened after test5 so count should be 5 not 6
        result = await table.scan()
        assert result['Count'] == 5

    # On exit it should flush so count should be 6
    result = await table.scan()
    assert result['Count'] == 9


@pytest.mark.asyncio
async def test_flush_doesnt_reset_item_buffer(dynamodb_resource, random_table_name):
    await dynamodb_resource.create_table(
        TableName=random_table_name,
        KeySchema=[{'AttributeName': 'pk', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'pk', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 2, 'WriteCapacityUnits': 1}
    )

    table = await dynamodb_resource.Table(random_table_name)
    async with table.batch_writer(flush_amount=5, on_exit_loop_sleep=0.1) as dynamo_writer:
        dynamo_writer._items_buffer.extend([
            {'PutRequest': {'Item': {'pk': 'test1', 'test_col1': 'col'}}},
            {'PutRequest': {'Item': {'pk': 'test2', 'test_col1': 'col'}}},
            {'PutRequest': {'Item': {'pk': 'test3', 'test_col1': 'col'}}},
            {'PutRequest': {'Item': {'pk': 'test4', 'test_col1': 'col'}}},
            {'PutRequest': {'Item': {'pk': 'test5', 'test_col1': 'col'}}},
            {'PutRequest': {'Item': {'pk': 'test6', 'test_col1': 'col'}}},
        ])
        result = await table.scan()
        assert result['Count'] == 0

        await dynamo_writer.put_item(Item={'pk': 'test7', 'test_col1': 'col'})

        # Flush amount is 5 so count should be 5 not 6
        result = await table.scan()
        assert result['Count'] == 5

        assert len(dynamo_writer._items_buffer) == 2
        # the buffer doesn't have unprocessed items deleted

        # add more items than the flush size to check exit iterates over all items
        dynamo_writer._items_buffer.extend([
            {'PutRequest': {'Item': {'pk': 'test8', 'test_col1': 'col'}}},
            {'PutRequest': {'Item': {'pk': 'test9', 'test_col1': 'col'}}},
            {'PutRequest': {'Item': {'pk': 'test10', 'test_col1': 'col'}}},
            {'PutRequest': {'Item': {'pk': 'test11', 'test_col1': 'col'}}},
        ])

    # On exit it should flush so count should be 11
    result = await table.scan()
    assert result['Count'] == 11


@pytest.mark.asyncio
async def test_dynamo_resource_property(dynamodb_resource, random_table_name):
    await dynamodb_resource.create_table(
        TableName=random_table_name,
        KeySchema=[{'AttributeName': 'pk', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'pk', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 123, 'WriteCapacityUnits': 123}
    )

    table = await dynamodb_resource.Table(random_table_name)

    table_arn = table.table_arn
    assert asyncio.iscoroutine(table_arn)

    result = await table_arn
    assert result is not None


@pytest.mark.asyncio
async def test_dynamo_resource_waiter(dynamodb_resource, random_table_name):
    await dynamodb_resource.create_table(
        TableName=random_table_name,
        KeySchema=[{'AttributeName': 'pk', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'pk', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 123, 'WriteCapacityUnits': 123}
    )

    table = await dynamodb_resource.Table(random_table_name)

    await table.wait_until_exists()

    result = await table.table_arn
    assert result is not None
