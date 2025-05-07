import boto3
import pytest
import random
import string
import uuid
from unittest import mock
from typing import Dict, Type, TypeVar

import pytest_asyncio

from aiobotocore.config import AioConfig
from aioboto3.session import Session


@pytest.fixture(scope="session", params=[True, False],
                ids=['debug[true]', 'debug[false]'])
def debug(request):
    return request.param


def moto_config() -> Dict[str, str]:
    return {
        'aws_secret_access_key': 'xxx',
        'aws_access_key_id': 'xxx'
    }


@pytest.fixture
def region() -> str:
    return 'eu-central-1'


@pytest.fixture
def signature_version() -> str:
    return 'v4'


@pytest.fixture
def config(signature_version: str) -> AioConfig:
    return AioConfig(
        signature_version=signature_version,
        read_timeout=5,
        connect_timeout=5
    )


@pytest.fixture
def random_table_name() -> str:
    return 'test_' + ''.join([random.choice(string.hexdigits) for _ in range(0, 8)])


@pytest.fixture
def bucket_name() -> str:
    return 'test-bucket-' + str(uuid.uuid4())


@pytest.fixture
def kms_key_alias() -> str:
    return 'alias/test-' + uuid.uuid4().hex


@pytest.fixture
def s3_key_name() -> str:
    return uuid.uuid4().hex


@pytest_asyncio.fixture
async def dynamodb_resource(request, region: str, config: AioConfig, dynamodb2_server: str) -> "ServiceResource":
    session = Session(region_name=region, **moto_config())

    async with session.resource('dynamodb', region_name=region, endpoint_url=dynamodb2_server, config=config) as resource:
        yield resource


@pytest_asyncio.fixture
async def s3_client(request, region: str, config: AioConfig, s3_server: str, bucket_name: str) -> "S3":
    session = Session(region_name=region, **moto_config())

    async with session.client('s3', region_name=region, endpoint_url=s3_server, config=config) as client:
        yield client


@pytest_asyncio.fixture
async def s3_resource(request, region: str, config: AioConfig, s3_server: str, bucket_name: str) -> "ServiceResource":
    session = Session(region_name=region, **moto_config())

    async with session.resource('s3', region_name=region, endpoint_url=s3_server, config=config) as resource:
        yield resource


T = TypeVar('T')


def create_fake_session(base_class: Type[T], url_overrides: Dict[str, str]) -> Type[T]:
    class FakeSession(base_class):
        def __init__(self, *args, **kwargs):
            super(FakeSession, self).__init__(*args, **kwargs)

            self.__url_overrides = url_overrides
            self.__secret_key = 'ABCDEFGABCDEFGABCDEF'
            self.__access_key = 'YTYHRSshtrsTRHSrsTHRSTrthSRThsrTHsr'

        def client(self, *args, **kwargs):

            if 'endpoint_url' not in kwargs and args[0] in self.__url_overrides:
                kwargs['endpoint_url'] = self.__url_overrides[args[0]]

            kwargs['aws_access_key_id'] = self.__secret_key
            kwargs['aws_secret_access_key'] = self.__access_key

            return super(FakeSession, self).client(*args, **kwargs)

        def resource(self, *args, **kwargs):

            if 'endpoint_url' not in kwargs and args[0] in self.__url_overrides:
                kwargs['endpoint_url'] = self.__url_overrides[args[0]]

            kwargs['aws_access_key_id'] = self.__secret_key
            kwargs['aws_secret_access_key'] = self.__access_key

            return super(FakeSession, self).resource(*args, **kwargs)
    return FakeSession


@pytest.fixture(scope='function')
def moto_patch(request, region, config, s3_server, kms_server):
    FakeAioboto3Session = create_fake_session(Session, {
        's3': s3_server,
        'kms': kms_server
    })
    FakeBoto3Session = create_fake_session(boto3.Session, {
        's3': s3_server,
    })

    sessions = [
        mock.patch('aioboto3.Session', FakeAioboto3Session),
        mock.patch('aioboto3.session.Session', FakeAioboto3Session),
        mock.patch('boto3.Session', FakeBoto3Session),
        mock.patch('boto3.session.Session', FakeBoto3Session)
    ]
    for session in sessions:
        session.start()

    yield

    for session in sessions:
        session.stop()


pytest_plugins = ['mock_server']
