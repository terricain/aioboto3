"""
Tests for the process-wide shared loader / alias cache / accepts_kwargs cache
introduced to fix issue #362 (event-loop CPU starvation when many coroutines
each create their own ``aioboto3.Session``).
"""

import aioboto3


def test_session_shares_loader_by_default():
    """Two default ``aioboto3.Session()`` instances should share the same
    botocore data loader instance, so the per-session JSON parse work happens
    at most once per process."""
    s1 = aioboto3.Session()
    s2 = aioboto3.Session()
    assert s1._session.get_component('data_loader') is s2._session.get_component('data_loader')


def test_aws_data_path_isolates_loader(monkeypatch):
    """Sessions constructed with different ``AWS_DATA_PATH`` values must get
    distinct loaders so that custom search paths remain isolated."""
    monkeypatch.setenv('AWS_DATA_PATH', '/tmp/aioboto3-test-path-a')
    s_a = aioboto3.Session()
    monkeypatch.setenv('AWS_DATA_PATH', '/tmp/aioboto3-test-path-b')
    s_b = aioboto3.Session()
    assert s_a._session.get_component('data_loader') is not s_b._session.get_component('data_loader')


def test_custom_botocore_session_preserves_its_loader():
    """If the caller passes their own ``botocore_session=``, the shared-loader
    injection must be skipped so the caller's loader is preserved untouched."""
    import aiobotocore.session

    custom = aiobotocore.session.get_session()
    custom_loader = custom.get_component('data_loader')
    s = aioboto3.Session(botocore_session=custom)
    assert s._session.get_component('data_loader') is custom_loader
