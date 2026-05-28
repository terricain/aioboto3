# -*- coding: utf-8 -*-
"""
This class essentially overrides the boto3 session init, passing in
an async botocore session
"""

import copy
import functools
import os
import threading

import boto3.session
import boto3.resources.base
import boto3.utils
from boto3.session import DataNotFoundError, UnknownServiceError
from boto3.exceptions import ResourceNotExistsError, UnknownAPIVersionError

import aiobotocore.session
from aiobotocore.config import AioConfig
from botocore import compat as _botocore_compat
from botocore.exceptions import NoCredentialsError
from botocore.loaders import create_loader

from aioboto3.resources.factory import AIOBoto3ResourceFactory


# ---------------------------------------------------------------------------
# Cache ``accepts_kwargs`` results process-wide.
#
# Why: ``HierarchicalEmitter.register`` calls
# ``_verify_accept_kwargs(handler)`` once per handler registered, which in
# turn calls ``botocore.compat.accepts_kwargs`` -> ``inspect.getfullargspec``.
# When N coroutines each instantiate their own ``aioboto3.Session``, each
# session re-registers all 119 entries in ``handlers.BUILTIN_HANDLERS`` and
# pays the ``getfullargspec`` cost again for the same set of function
# objects. The result of ``accepts_kwargs(func)`` depends only on the
# function object's signature, which is immutable, so the result is safe
# to cache for the lifetime of the process. This is a strict subset of the
# work cached by ``functools.lru_cache``.
def _install_accepts_kwargs_cache():
    if getattr(_botocore_compat.accepts_kwargs, '_aioboto3_cached', False):
        return
    _original_accepts_kwargs = _botocore_compat.accepts_kwargs

    @functools.lru_cache(maxsize=None)
    def _cached_accepts_kwargs(func):
        return _original_accepts_kwargs(func)

    _cached_accepts_kwargs._aioboto3_cached = True  # type: ignore[attr-defined]
    # Patch the canonical reference. ``botocore/hooks.py`` looks up the
    # function via ``from botocore.compat import accepts_kwargs`` at import
    # time, so we also need to patch that local binding to make the cache
    # effective.
    _botocore_compat.accepts_kwargs = _cached_accepts_kwargs
    try:
        from botocore import hooks as _botocore_hooks
        _botocore_hooks.accepts_kwargs = _cached_accepts_kwargs
    except ImportError:  # pragma: no cover
        pass


_install_accepts_kwargs_cache()


# ---------------------------------------------------------------------------
# Share ``EventAliaser._alias_name_cache`` process-wide.
#
# Why: each ``HierarchicalEmitter`` created (one per
# ``aiobotocore.session.AioSession``) starts with an empty
# ``_alias_name_cache``. The cache is then warmed up during ``register``
# and ``emit`` calls. Because the alias rules (``EVENT_ALIASES``) are a
# module-level constant and the cache key is just the event name string,
# the cache contents are deterministic given the input event name. Sharing
# the cache across all emitters that use the default ``EVENT_ALIASES``
# saves the per-session string-splitting cost in ``_alias_event_name``.
# Cache lookups and writes on a Python ``dict`` are GIL-atomic, so this is
# safe under asyncio.
def _install_shared_alias_cache():
    try:
        from botocore.hooks import EventAliaser, EVENT_ALIASES
    except ImportError:  # pragma: no cover
        return
    if getattr(EventAliaser, '_aioboto3_alias_cache_shared', False):
        return

    _shared_default_cache: dict = {}
    _original_init = EventAliaser.__init__

    def _patched_init(self, event_emitter, event_aliases=None):
        _original_init(self, event_emitter, event_aliases)
        if self._event_aliases is EVENT_ALIASES:
            self._alias_name_cache = _shared_default_cache

    EventAliaser.__init__ = _patched_init  # type: ignore[method-assign]
    EventAliaser._aioboto3_alias_cache_shared = True  # type: ignore[attr-defined]


_install_shared_alias_cache()


# Process-wide shared data-loader cache, keyed by the effective AWS data
# path (i.e. ``self._session.get_config_variable('data_path')``).
#
# Why: each ``aiobotocore.session.get_session()`` builds its own loader,
# and each loader does its own JSON parsing of the botocore service
# models the first time a client is created on it. When N coroutines
# each create their own ``aioboto3.Session`` (the pattern in issue #362),
# they each pay ~60 ms of synchronous parse work, which serialises on the
# event loop and causes the "all responses arrive at the very end"
# symptom. The loader's cache is read-only after the initial load and
# safe to share across coroutines and threads (Python dict reads/writes
# of distinct keys are GIL-atomic; double-compute on a miss is
# idempotent).
#
# We key by data_path so that callers using ``AWS_DATA_PATH`` to inject
# custom service models still get a loader scoped to that path.
_SHARED_LOADER_CACHE: dict = {}
_SHARED_LOADER_LOCK = threading.Lock()


def _get_shared_loader(data_path):
    """Return a process-wide shared botocore Loader for the given data path.

    ``data_path`` is the resolved value of the ``data_path`` session config
    variable (typically the contents of ``AWS_DATA_PATH``); ``None`` means
    "use the default botocore + ~/.aws/models paths".
    """
    key = data_path
    loader = _SHARED_LOADER_CACHE.get(key)
    if loader is not None:
        return loader
    with _SHARED_LOADER_LOCK:
        loader = _SHARED_LOADER_CACHE.get(key)
        if loader is None:
            loader = create_loader(data_path)
            _SHARED_LOADER_CACHE[key] = loader
    return loader


def _install_shared_loader(botocore_session):
    """Replace the lazy ``data_loader`` component on ``botocore_session``
    with the shared process-wide loader.

    Must be called before anything else asks the session for the
    ``data_loader`` component.
    """
    data_path = botocore_session.get_config_variable('data_path')
    loader = _get_shared_loader(data_path)
    botocore_session.register_component('data_loader', loader)
    return loader


class Session(boto3.session.Session):
    """
    A session stores configuration state and allows you to create service
    clients and resources.

    :type aws_access_key_id: string
    :param aws_access_key_id: AWS access key ID
    :type aws_secret_access_key: string
    :param aws_secret_access_key: AWS secret access key
    :type aws_session_token: string
    :param aws_session_token: AWS temporary session token
    :type region_name: string
    :param region_name: Default region when creating new connections
    :type botocore_session: aiobotocore.session.AioSession
    :param botocore_session: Use this AioBotocore session instead of creating
                             a new default one.
    :type profile_name: string
    :param profile_name: The name of a profile to use. If not given, then
                         the default profile is used.
    :type aws_account_id: string
    :param aws_account_id: AWS account ID
    """
    def __init__(
        self,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_session_token=None,
        region_name=None,
        botocore_session=None,
        profile_name=None,
        aws_account_id=None,
    ):
        if botocore_session is not None:
            self._session = botocore_session
        else:
            # Create a new default session
            self._session = aiobotocore.session.get_session()
            # Inject a process-wide shared data loader so the first
            # ``get_component('data_loader')`` call (during ``client(...)``
            # / ``resource(...)``) does not re-parse the botocore service
            # model JSON for every Session instance. Only do this when we
            # *own* the session; if the caller passed their own
            # ``botocore_session`` we leave its loader semantics alone.
            _install_shared_loader(self._session)

        # Setup custom user-agent string if it isn't already customized
        if self._session.user_agent_name == 'Botocore':
            botocore_info = f'Botocore/{self._session.user_agent_version}'
            if self._session.user_agent_extra:
                self._session.user_agent_extra += ' ' + botocore_info
            else:
                self._session.user_agent_extra = botocore_info
            self._session.user_agent_name = 'Boto3'
            self._session.user_agent_version = boto3.__version__

        if profile_name is not None:
            self._session.set_config_variable('profile', profile_name)

        credentials_kwargs = {
            "aws_access_key_id": aws_access_key_id,
            "aws_secret_access_key": aws_secret_access_key,
            "aws_session_token": aws_session_token,
            "aws_account_id": aws_account_id,
        }

        if any(credentials_kwargs.values()):
            if self._account_id_set_without_credentials(**credentials_kwargs):
                raise NoCredentialsError()

            if aws_account_id is None:
                del credentials_kwargs["aws_account_id"]

            # This only works as dictionaries happen to be ordered.
            self._session.set_credentials(*credentials_kwargs.values())

        if region_name is not None:
            self._session.set_config_variable('region', region_name)

        self.resource_factory = AIOBoto3ResourceFactory(
            self._session.get_component('event_emitter')
        )
        self._setup_loader()
        self._register_default_handlers()

    def _setup_loader(self):
        """Override boto3.session.Session._setup_loader.

        The default implementation unconditionally appends ``boto3/data`` to
        the loader's ``search_paths``. With the shared loader, that would
        accumulate one duplicate entry per ``aioboto3.Session()`` call. We
        dedupe so the search path stays bounded.
        """
        self._loader = self._session.get_component('data_loader')
        boto3_data = os.path.join(
            os.path.dirname(boto3.session.__file__), 'data'
        )
        if boto3_data not in self._loader.search_paths:
            self._loader.search_paths.append(boto3_data)

    def resource(
        self,
        service_name,
        region_name=None,
        api_version=None,
        use_ssl=True,
        verify=None,
        endpoint_url=None,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_session_token=None,
        config=None
    ):
        try:
            resource_model = self._loader.load_service_model(
                service_name, 'resources-1', api_version
            )
        except UnknownServiceError:
            available = self.get_available_resources()
            has_low_level_client = (
                service_name in self.get_available_services()
            )
            raise ResourceNotExistsError(
                service_name, available, has_low_level_client
            )
        except DataNotFoundError:
            # This is because we've provided an invalid API version.
            available_api_versions = self._loader.list_api_versions(
                service_name, 'resources-1'
            )
            raise UnknownAPIVersionError(
                service_name, api_version, ', '.join(available_api_versions)
            )

        if api_version is None:
            # Even though botocore's load_service_model() can handle
            # using the latest api_version if not provided, we need
            # to track this api_version in boto3 in order to ensure
            # we're pairing a resource model with a client model
            # of the same API version.  It's possible for the latest
            # API version of a resource model in boto3 to not be
            # the same API version as a service model in botocore.
            # So we need to look up the api_version if one is not
            # provided to ensure we load the same API version of the
            # client.
            #
            # Note: This is relying on the fact that
            #   loader.load_service_model(..., api_version=None)
            # and loader.determine_latest_version(..., 'resources-1')
            # both load the same api version of the file.
            api_version = self._loader.determine_latest_version(
                service_name, 'resources-1'
            )

        # Creating a new resource instance requires the low-level client
        # and service model, the resource version and resource JSON data.
        # We pass these to the factory and get back a class, which is
        # instantiated on top of the low-level client.
        if config is not None:
            if config.user_agent_extra is None:
                config = copy.deepcopy(config)
                config.user_agent_extra = 'Resource'
        else:
            config = AioConfig(user_agent_extra='Resource')

        # client = blah part has been moved into a dodgy context class
        return ResourceCreatorContext(self, service_name, region_name, api_version,
                                      use_ssl, verify, endpoint_url, aws_access_key_id,
                                      aws_secret_access_key, aws_session_token, config,
                                      resource_model)

    def _register_default_handlers(self):
        # S3 customizations
        self._session.register(
            'creating-client-class.s3',
            boto3.utils.lazy_call(
                'aioboto3.s3.inject.inject_s3_transfer_methods'
            ),
        )
        self._session.register(
            'creating-resource-class.s3.Bucket',
            boto3.utils.lazy_call('aioboto3.s3.inject.inject_bucket_methods'),
        )
        self._session.register(
            'creating-resource-class.s3.Object',
            boto3.utils.lazy_call('boto3.s3.inject.inject_object_methods'),
        )
        self._session.register(
            'creating-resource-class.s3.ObjectSummary',
            boto3.utils.lazy_call(
                'aioboto3.s3.inject.inject_object_summary_methods'
            ),
        )

        # DynamoDb customizations
        self._session.register(
            'creating-resource-class.dynamodb',
            boto3.utils.lazy_call(
                'boto3.dynamodb.transform.register_high_level_interface'
            ),
            unique_id='high-level-dynamodb',
        )
        self._session.register(
            'creating-resource-class.dynamodb.Table',
            boto3.utils.lazy_call(
                'aioboto3.dynamodb.table.register_table_methods'
            ),
            unique_id='high-level-dynamodb-table',
        )

        # EC2 Customizations
        self._session.register(
            'creating-resource-class.ec2.ServiceResource',
            boto3.utils.lazy_call('boto3.ec2.createtags.inject_create_tags')
        )

        self._session.register(
            'creating-resource-class.ec2.Instance',
            boto3.utils.lazy_call(
                'boto3.ec2.deletetags.inject_delete_tags',
                event_emitter=self.events
            ),
        )


class ResourceCreatorContext(object):
    def __init__(self, session, service_name, region_name, api_version, use_ssl, verify,
                 endpoint_url, aws_access_key_id, aws_secret_access_key, aws_session_token,
                 config, resource_model):
        self.service_name = service_name
        self.resource_model = resource_model
        self.session = session
        self.api_version = api_version
        self.cls = None
        self.client = session.client(
            service_name, region_name=region_name, api_version=api_version,
            use_ssl=use_ssl, verify=verify, endpoint_url=endpoint_url,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_session_token=aws_session_token, config=config)

    async def __aenter__(self):
        client = await self.client.__aenter__()
        service_model = client.meta.service_model

        # Create a ServiceContext object to serve as a reference to
        # important read-only information about the general service.
        service_context = boto3.utils.ServiceContext(
            service_name=self.service_name,
            service_model=service_model,
            resource_json_definitions=self.resource_model['resources'],
            service_waiter_model=boto3.utils.LazyLoadedWaiterModel(
                self.session._session, self.service_name, self.api_version
            ),
        )

        # Create the service resource class.
        self.cls = (await self.session.resource_factory.load_from_definition(
            resource_name=self.service_name,
            single_resource_json_definition=self.resource_model['service'],
            service_context=service_context
        ))(client=client)

        return self.cls

    async def __aexit__(self, exc_type, exc, tb):
        await self.cls.__aexit__(exc_type, exc, tb)
