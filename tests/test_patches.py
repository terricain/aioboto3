import hashlib

import boto3
from boto3.session import Session
from boto3.resources.action import BatchAction, ServiceAction, WaiterAction
from boto3.resources.response import ResourceHandler, RawHandler
from boto3.resources.collection import ResourceCollection, CollectionManager, CollectionFactory
from boto3.resources.factory import ResourceFactory
from boto3.dynamodb.table import register_table_methods, TableResource, BatchWriter
from boto3.s3.inject import inject_s3_transfer_methods, download_file, download_fileobj, upload_file, \
    upload_fileobj, copy
from dill.source import getsource

import aiobotocore


_API_DIGESTS = {
    # __init__.py
    boto3.setup_default_session: {'3600170f2c4dbd1896f636a21524b3b027405de1'},
    boto3.set_stream_logger: {'42a3ca2d28b00e219acfd03ae110a970eb2b9045'},
    boto3._get_default_session: {'5249535ea408e9497b1363f73b9fd46dcb068b06'},
    boto3.client: {'20c73aeb9feb10d1e5d7f6b3f7dedcab00c7fbcf'},
    boto3.resource: {'316deeb96e6af699be73670c7478357c6882eab3'},
    boto3.NullHandler: {'7f33bbce5d634afba1f0fff359644f288dcf671e'},

    # resources/action.py
    ServiceAction.__init__: {'b8b759abbe8fbfa9bad332b8ce8d30f55daf97f3'},
    ServiceAction.__call__: {'3e84efcb2badef725b998e1af27a4a6f6f1aa2ed'},
    BatchAction.__call__: {'8839f17467d16f98e4587fa750d74c9007dea134'},
    WaiterAction.__call__: {'57d4f3f74e7e774e3aeb13630292fa9183a790f8'},

    # resources/collection.py
    ResourceCollection.__iter__: {'6631cf4c177643738acff01aa7f3fa324a246ba9'},  # Logic inside anext
    ResourceCollection.pages: {'a26745155edd73004004af12e8fa8f617d2989b0'},
    CollectionManager.__init__: {'f40c0a368b747518a7b6998eab98920cb4d7d233'},
    CollectionFactory.load_from_definition: {'eadb8897327b2faf812b2a2d6fbf643c8f4f029a'},
    CollectionFactory._create_batch_action: {'435ff19f24325a515563fd9716b89158ac676a02'},

    # resources/factory.py
    ResourceFactory.__init__: {'dc2b647537ce3cecfe76e172cc4042eca4ed5b86'},
    ResourceFactory.load_from_definition: {'1f6c0b9298d63d3d50c64abdb3c7025c03cbbdf9'},
    ResourceFactory._create_autoload_property: {'62793a404067069d499246389f1b97601cb9b7a8'},
    ResourceFactory._create_waiter: {'69d8bd493fde2f6e3b32c5a6cf89059885832cff'},
    ResourceFactory._create_class_partial: {'5e421387dd4a4a40e871dc1597af21149eccf85a'},
    ResourceFactory._create_action: {'f0d07daf3e4dcf45ed07886fa5aa66e123b0d680'},

    # resources/response.py
    ResourceHandler.__call__: {'4927077955466d5ef3558b2148ba8ff8d19094bf'},
    RawHandler.__call__: {'5ea91e39ab1dc3587a4038805ee90235990b866d'},

    # session.py
    Session.__init__: {'7c25cbd2154cc87e732fe4a343900d7002195973'},
    Session._register_default_handlers: {'04f247de526b7a0af15737e04019ade52cc65446'},
    Session.resource: {'5e3568b28281a75eaf9725fab67c33dc16a18144'},

    # dynamodb/table.py
    register_table_methods: {'1d9191de712871b92e1e87f94c6583166a315113'},
    TableResource: {'a65f5e64ecca7d3cee3f6f337db36313d84dbad1'},
    BatchWriter: {'cc693bab78c81c5d11a308275734cc1815b0199a'},  # Class was pretty much rewritten so wasn't subclassed.

    # s3/inject.py
    inject_s3_transfer_methods: {'8540c89847b80cc1fb34627989eba14972c158d5'},
    download_file: {'5a05472514f9e34c5f64ca8bbcc80a1d27f1f5d1'},
    download_fileobj: {'237370745eb02e93a353fa806a64f3701c47995c', '9299d1abbd9d5c311e8a824a438e150ff24ebcd7'},
    upload_fileobj: {'d1db027e51d37cf1476377cfda436810b813044b'},
    upload_file: {'ad899c968fdfc294b46c54efbcb9912c5675ba09'},
    copy: {'c4423d0a6d3352553befdf0387987c09812fcaff'},
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
