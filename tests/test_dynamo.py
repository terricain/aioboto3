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

    table = dynamodb_resource.Table(random_table_name)
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

    table = dynamodb_resource.Table(random_table_name)
    await table.put_item(
        Item={'pk': 'test', 'test_col1': 'col'}
    )

    result = await table.scan()
    assert result['Count'] == 1
