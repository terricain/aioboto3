import asyncio

from boto3.dynamodb.conditions import Key
import pytest


@pytest.mark.asyncio
async def test_dynamo_resource_query(event_loop, dynamodb_resource, random_table_name):

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
async def test_dynamo_resource_put(event_loop, dynamodb_resource, random_table_name):
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
async def test_dynamo_resource_batch_write_flush_on_exit_context(event_loop, dynamodb_resource, random_table_name):
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
async def test_dynamo_resource_batch_write_flush_amount(event_loop, dynamodb_resource, random_table_name):
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
async def test_dynamo_resource_property(event_loop, dynamodb_resource, random_table_name):
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
async def test_dynamo_resource_waiter(event_loop, dynamodb_resource, random_table_name):
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
