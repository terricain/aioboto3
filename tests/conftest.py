import pytest
import random
import string
import uuid
import mock

from aiobotocore.config import AioConfig
from aioboto3.session import Session
import aioboto3


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
def kms_key_alias():
    return 'alias/test-' + uuid.uuid4().hex


@pytest.fixture
def s3_key_name():
    return uuid.uuid4().hex


@pytest.fixture
async def dynamodb_resource(request, region, config, event_loop, dynamodb2_server):
    session = Session(region_name=region, **moto_config())

    async with session.resource('dynamodb', region_name=region, endpoint_url=dynamodb2_server, config=config) as resource:
        yield resource


@pytest.fixture
async def s3_client(request, region, config, event_loop, s3_server, bucket_name):
    session = Session(region_name=region, **moto_config())

    async with session.client('s3', region_name=region, endpoint_url=s3_server, config=config) as client:
        yield client


@pytest.fixture
async def s3_resource(request, region, config, event_loop, s3_server, bucket_name):
    session = Session(region_name=region, **moto_config())

    async with session.resource('s3', region_name=region, endpoint_url=s3_server, config=config) as resource:
        yield resource


@pytest.fixture(scope='function')
def s3_moto_patch(request, region, config, event_loop, s3_server):
    from aioboto3 import client as orig_client, resource as orig_resource

    s3_url = s3_server

    def fake_client(*args, **kwargs):
        nonlocal s3_url
        if 'endpoint_url' not in kwargs and args[0] == 's3':
            kwargs['endpoint_url'] = s3_url
            kwargs['aws_access_key_id'] = 'ABCDEFGABCDEFGABCDEF'
            kwargs['aws_secret_access_key'] = 'YTYHRSshtrsTRHSrsTHRSTrthSRThsrTHsr'

        return orig_client(*args, **kwargs)

    def fake_res(*args, **kwargs):
        nonlocal s3_url
        if 'endpoint_url' not in kwargs and args[0] == 's3':
            kwargs['endpoint_url'] = s3_url
            kwargs['aws_access_key_id'] = 'ABCDEFGABCDEFGABCDEF'
            kwargs['aws_secret_access_key'] = 'YTYHRSshtrsTRHSrsTHRSTrthSRThsrTHsr'
        return orig_resource(*args, **kwargs)

    client_patcher = mock.patch('aioboto3.client', fake_client)
    resource_patcher = mock.patch('aioboto3.resource', fake_res)

    client_patcher.start()
    resource_patcher.start()

    yield fake_client, fake_res

    client_patcher.stop()
    resource_patcher.stop()
    aioboto3.DEFAULT_SESSION = None


@pytest.fixture
def kms_moto_patch(request, region, config, event_loop, kms_server):
    from aioboto3 import client as orig_client

    kms_url = kms_server

    def fake_client(*args, **kwargs):
        nonlocal kms_url
        if 'endpoint_url' not in kwargs and args[0] == 'kms':
            kwargs['endpoint_url'] = kms_url
            kwargs['aws_access_key_id'] = 'ABCDEFGABCDEFGABCDEF'
            kwargs['aws_secret_access_key'] = 'YTYHRSshtrsTRHSrsTHRSTrthSRThsrTHsr'
        return orig_client(*args, **kwargs)

    client_patcher = mock.patch('aioboto3.client', fake_client)
    client_patcher.start()

    yield fake_client

    client_patcher.stop()


pytest_plugins = ['mock_server']
