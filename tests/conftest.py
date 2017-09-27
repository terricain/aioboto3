import asyncio
import pytest
import random
import string

from aiobotocore.config import AioConfig
from aioboto3.session import Session


@pytest.fixture(scope="session", params=[True, False],
                ids=['debug[true]', 'debug[false]'])
def debug(request):
    return request.param


@pytest.yield_fixture
def loop(request, debug):
    try:
        old_loop = asyncio.get_event_loop()
    except RuntimeError:
        old_loop = None

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(None)
    loop.set_debug(debug)

    yield loop

    loop.close()
    asyncio.set_event_loop(old_loop)


@pytest.mark.tryfirst
def pytest_pycollect_makeitem(collector, name, obj):
    if collector.funcnamefilter(name):
        item = pytest.Function(name, parent=collector)
        if 'run_loop' in item.keywords:
            return list(collector._genfunctions(name, obj))


@pytest.mark.tryfirst
def pytest_pyfunc_call(pyfuncitem):
    """
    Run asyncio marked test functions in an event loop instead of a normal
    function call.
    """
    if 'run_loop' in pyfuncitem.keywords:
        funcargs = pyfuncitem.funcargs
        loop = funcargs['loop']
        testargs = {arg: funcargs[arg]
                    for arg in pyfuncitem._fixtureinfo.argnames}

        if not asyncio.iscoroutinefunction(pyfuncitem.obj):
            func = asyncio.coroutine(pyfuncitem.obj)
        else:
            func = pyfuncitem.obj
        loop.run_until_complete(func(**testargs))
        return True


def pytest_runtest_setup(item):
    if 'run_loop' in item.keywords and 'loop' not in item.fixturenames:
        # inject an event loop fixture for all async tests
        item.fixturenames.append('loop')


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
def dynamodb_resource(region, config, event_loop, dynamodb2_server):
    session = Session(region_name=region, loop=event_loop, **moto_config())
    resource = session.resource('dynamodb', region_name=region, endpoint_url=dynamodb2_server, config=config)
    yield resource

    # Clean up
    yield from resource.close()


pytest_plugins = ['mock_server']
