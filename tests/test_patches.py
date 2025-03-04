import hashlib

import boto3
from boto3.session import Session
from boto3.resources.action import BatchAction, ServiceAction, WaiterAction
from boto3.resources.response import ResourceHandler, RawHandler
from boto3.resources.collection import ResourceCollection, CollectionManager, CollectionFactory
from boto3.resources.factory import ResourceFactory
from boto3.dynamodb.table import register_table_methods, TableResource, BatchWriter
from boto3.s3.inject import inject_s3_transfer_methods, download_file, download_fileobj, upload_file, \
    upload_fileobj, copy, inject_object_summary_methods, inject_bucket_methods, object_summary_load, \
    bucket_load
from boto3.s3.transfer import S3TransferConfig
from dill.source import getsource
from chalice.app import Chalice, RestAPIEventHandler, __version__ as chalice_version

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
    ServiceAction.__init__: {'b8b759abbe8fbfa9bad332b8ce8d30f55daf97f3', '21c079bf5e234c3fcb632c7f689eccf0c4d2935b'},
    ServiceAction.__call__: {'f3cb58a5e36bf3355723c69ec244990180a2d5bc', '56c98dd3a54b2859a8834a1e4d676fe38fae013e'},
    BatchAction.__call__: {'ea58ac6ba436740cc3766b8c115ee0222b665c9a', '63387ccf7f57ffc39be7fde1de187776622bb1c4'},
    WaiterAction.__call__: {'d3c379619530e8f2b3b7cb8a3421dcb0acfd0f73', '616339d5d6af86431108d84118f490d879dd9fa2'},

    # resources/collection.py
    ResourceCollection.__iter__: {'6631cf4c177643738acff01aa7f3fa324a246ba9'},  # Logic inside anext
    ResourceCollection.pages: {'a26745155edd73004004af12e8fa8f617d2989b0', '28ae6e6fe35b930bbf65a162225bb4e23fc9eec0', '5e57180839503cdd6de71cefe5b8c8b862273ad1'},
    CollectionManager.__init__: {'f40c0a368b747518a7b6998eab98920cb4d7d233', '7007f88626a41fec98a5efd79c24395d89ded879'},
    CollectionFactory.load_from_definition: {'eadb8897327b2faf812b2a2d6fbf643c8f4f029a', '06c878d737216948ef9cfda476594466d34b5d97', '143dccdee71618317880686f3b3ae8f31eee5d2e'},
    CollectionFactory._create_batch_action: {'435ff19f24325a515563fd9716b89158ac676a02', 'a911563aaf703994b63c5e2b51c0205b82f05673'},

    # resources/factory.py
    ResourceFactory.__init__: {'dc2b647537ce3cecfe76e172cc4042eca4ed5b86'},
    ResourceFactory.load_from_definition: {'1f6c0b9298d63d3d50c64abdb3c7025c03cbbdf9', 'c995f96439b1837d6caaf461e37f01580cd840d5'},
    ResourceFactory._create_autoload_property: {'62793a404067069d499246389f1b97601cb9b7a8', '812f8f8cd1445582c83b09ff2fce1e799daba419', '49c51a5503d40a8be2aba6cf99b3896cd8f97bac'},
    ResourceFactory._create_waiter: {'69d8bd493fde2f6e3b32c5a6cf89059885832cff', 'abb12827964c8bab17f4d99466d1a60ab97ec0a9'},
    ResourceFactory._create_class_partial: {'5e421387dd4a4a40e871dc1597af21149eccf85a', 'cba44eb792b11f2ff47146f0f610e0bfb17de1b5'},
    ResourceFactory._create_action: {'1cbbe9ee45eeff7b40d3cde21df34f5cff540c94'},

    # resources/response.py
    ResourceHandler.__call__: {'4927077955466d5ef3558b2148ba8ff8d19094bf', 'e3bdc52aa8d22642d1118921d984808b9019ce63'},
    RawHandler.__call__: {'5ea91e39ab1dc3587a4038805ee90235990b866d'},

    # session.py
    Session.__init__: {'039bdfe7082256a3bffe3492fc6d84f1480fbd6a'},
    Session._register_default_handlers: {'04f247de526b7a0af15737e04019ade52cc65446', '74fa15629c9ea69f79f3a5285357dbf53f734f2d', 'e30e5c3a0f6bc8f002ba679d4bae831914fc67a0'},
    Session.resource: {'5e3568b28281a75eaf9725fab67c33dc16a18144', 'b110781f5a5d148dd1d614e7611650a16cbea372'},

    # dynamodb/table.py
    register_table_methods: {'1d9191de712871b92e1e87f94c6583166a315113'},
    TableResource: {'a65f5e64ecca7d3cee3f6f337db36313d84dbad1', '2b803c9437bbee6b369369a279fcb0e34c821ab2', 'b9d2f960fbffafdd8b88f7036c4dbe1a76e93f66'},
    BatchWriter: {'d32584de13fb42efb39ae6841d4a55d162f5e7dd'},  # Class was pretty much rewritten so wasn't subclassed.

    # s3/inject.py
    inject_s3_transfer_methods: {'8540c89847b80cc1fb34627989eba14972c158d5', '19e91a5002e1d5b30a08024f25a9ba875010bacc'},
    inject_object_summary_methods: {'a9e2005d1663a5eb17b6b9667835fa251864ccef'},
    inject_bucket_methods: {'63316226fdd4d7c043eaf35e07b6b2ac331b4872', 'dfe1c2219ced56b0aaa74c4a84210fd20463392e'},
    object_summary_load: {'3e4db1310105ced8ac2af17598603812ca18cbbe', '98a5a726f105388322a845ba97e08f1e53ee9d69'},
    bucket_load: {'2d40d03ca9ec91eb5de8a8f40e0f35634ab1d987'},
    download_file: {'5a05472514f9e34c5f64ca8bbcc80a1d27f1f5d1', 'a31ffcb7ba368f951d16babedcc48252cc5cb2af', '79bc1c0838e825eb54a3a5b48193c1ceac65947c', '5f0d6be6c3e86fd8fff2bc260d185a777327db27'},
    download_fileobj: {'237370745eb02e93a353fa806a64f3701c47995c', '9299d1abbd9d5c311e8a824a438e150ff24ebcd7', '91c0900c26c0078b623b9550c4fb9ef6afc4a528', 'b4189d56b7a61a7dee6e643489cca4e65da95b98'},
    upload_fileobj: {'d1db027e51d37cf1476377cfda436810b813044b', '3b953e17cfc4a3c6ad75c3890af60aebeea4bee8', 'e03eb92c3b2f260b1c036382f2ca9fcb1f293fcd'},
    upload_file: {'063eaca7bec14af8ccd041e3a87ff5c9ef7252ca', 'ad899c968fdfc294b46c54efbcb9912c5675ba09', 'df7552000d9111f71a05bd9880e9b6ef0f2f21bc', 'ace4ec5d8f8f0ebb70715faff51b95a1d2c02b69'},
    copy: {'c4423d0a6d3352553befdf0387987c09812fcaff', 'e8154a4de3b97dd2ab29d250c005b03e8fc7ed71', '7f9edd96f418e09c00d26538a7382b217e0843e5', '95d246b78893b525d30508870afc6b00297312f5'},
    S3TransferConfig.__init__: {'f418b3dab3c6f073f19feaf1172359bdc3863e22'},
}

_CHALICE_API_DIGESTS = {
    # experimental/async_chalice.py
    Chalice.__call__: {'d1d4f2b1a1bd6574500dec1f181fcfe8345f5ac6'},
    RestAPIEventHandler._get_view_function_response: {'ccf22bac60d89704c445baa9c2c881f525b70652'}
}

def test_patches():
    print("Boto3 version: {} aiobotocore version: {}".format(boto3.__version__, aiobotocore.__version__))

    success = True
    for obj, digests in _API_DIGESTS.items():
        digest = hashlib.sha1(getsource(obj).encode('utf-8')).hexdigest()
        if digest not in digests:
            print("Digest of {}:{} not found in: {}".format(obj.__qualname__, digest, digests))
            success = False

    assert success


def test_chalice_patches():
    print("Chalice version: {}".format(chalice_version))

    success = True
    for obj, digests in _CHALICE_API_DIGESTS.items():
        digest = hashlib.sha1(getsource(obj).encode('utf-8')).hexdigest()
        if digest not in digests:
            print("Digest of {}:{} not found in: {}".format(obj.__qualname__, digest, digests))
            success = False

    assert success
