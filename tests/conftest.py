import pytest
import random
import string
import uuid

from aiobotocore.config import AioConfig
from aioboto3.session import Session


@pytest.fixture(scope="session", params=[True, False],
                ids=['debug[true]', 'debug[false]'])
def debug(request):
    return request.param


def moto_config():
    return {
        'aws_secret_access_key': 'xxx',
        'aws_access_key_id': 'xxx'
    }


@pytest.fixture
def region():
    return 'eu-central-1'


@pytest.fixture
def signature_version():
    return 'v4'


@pytest.fixture
def config(signature_version):
    return AioConfig(
        signature_version=signature_version,
        read_timeout=5,
        connect_timeout=5
    )


@pytest.fixture
def random_table_name():
    return 'test_' + ''.join([random.choice(string.hexdigits) for _ in range(0, 8)])


@pytest.fixture
def bucket_name():
    return 'test-bucket-' + str(uuid.uuid4())


@pytest.fixture
def dynamodb_resource(request, region, config, event_loop, dynamodb2_server):
    session = Session(region_name=region, loop=event_loop, **moto_config())

    async def f():
        return session.resource('dynamodb', region_name=region, endpoint_url=dynamodb2_server, config=config)

    resource = event_loop.run_until_complete(f())
    yield resource

    def fin():
        event_loop.run_until_complete(resource.close())

    request.addfinalizer(fin)


@pytest.fixture
def s3_client(request, region, config, event_loop, s3_server, bucket_name):
    session = Session(region_name=region, loop=event_loop, **moto_config())

    async def f():
        return session.client('s3', region_name=region, endpoint_url=s3_server, config=config)

    client = event_loop.run_until_complete(f())

    yield client

    def fin():
        event_loop.run_until_complete(client.close())

    request.addfinalizer(fin)


pytest_plugins = ['mock_server']
