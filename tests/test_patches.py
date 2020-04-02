import hashlib

import boto3
from boto3.session import Session
from boto3.resources.action import BatchAction, ServiceAction, WaiterAction
from boto3.resources.response import ResourceHandler, RawHandler
from boto3.resources.collection import ResourceCollection, CollectionManager, CollectionFactory
from boto3.resources.factory import ResourceFactory
from boto3.dynamodb.table import register_table_methods, TableResource, BatchWriter
from dill.source import getsource

import aiobotocore


_API_DIGESTS = {
    # __init__.py
    boto3.setup_default_session: {''},
    boto3.set_stream_logger(): {''},
    boto3._get_default_session: {''},
    boto3.client: {''},
    boto3.resource: {''},
    boto3.NullHandler: {''},

    # resources/action.py
    BatchAction.__call__: {''},
    ServiceAction.__init__: {''},
    ServiceAction.__call__: {''},
    WaiterAction.__init__: {''},
    WaiterAction.__call__: {''},

    # resources/collection.py
    ResourceCollection.__iter__: {''},  # Logic inside anext
    ResourceCollection.pages: {''},
    CollectionManager.__init__: {''},
    CollectionManager.all: {''},
    CollectionFactory.load_from_definition: {''},
    CollectionFactory._create_batch_action: {''},

    # resources/factory.py
    ResourceFactory.__init__: {''},
    ResourceFactory.load_from_definition: {''},
    ResourceFactory._create_action: {''},
    ResourceFactory._create_waiter: {''},
    ResourceFactory._create_autoload_property: {''},
    ResourceFactory._create_class_partial: {''},

    # resources/response.py
    ResourceHandler.__call__: {''},
    RawHandler.__call__: {''},

    # session.py
    Session.__init__: {''},
    Session._register_default_handlers: {''},
    Session.resource: {''},

    # dynamodb/table
    register_table_methods: {''},
    TableResource: {''},
    BatchWriter: {''},  # Class was pretty much rewritten so wasn't subclassed.
}


def test_patches():
    print("Boto3 version: {} aiobotocore version: {}".format(
        boto3.__version__, aiobotocore.__version__))

    success = True
    for obj, digests in _API_DIGESTS.items():
        digest = hashlib.sha1(getsource(obj).encode('utf-8')).hexdigest()
        if digest not in digests:
            print("Digest of {}:{} not found in: {}".format(
                obj.__qualname__, digest, digests))
            success = False

    assert success
