# -*- coding: utf-8 -*-

"""Top-level package for Async AWS SDK for Python."""
import logging
from aioboto3.session import Session

__author__ = """Terri Cain"""
__email__ = 'terri@dolphincorp.co.uk'


try:
    from aioboto3._version import __version__
except PackageNotFoundError:
    __version__ = "0.0.0"


# Set up logging to ``/dev/null`` like a library is supposed to.
# http://docs.python.org/3.3/howto/logging.html#configuring-logging-for-a-library
class NullHandler(logging.Handler):
    def emit(self, record):
        pass


logging.getLogger('boto3').addHandler(NullHandler())
