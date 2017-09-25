# -*- coding: utf-8 -*-
"""
This class essentially overrides the boto3 session init, passing in
an async botocore session
"""


import aiobotocore.session
import boto3.session
import boto3.resources.base

from aioboto3.resources import AIOBoto3ResourceFactory


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
    :type botocore_session: botocore.session.Session
    :param botocore_session: Use this Botocore session instead of creating
                             a new default one.
    :type profile_name: string
    :param profile_name: The name of a profile to use. If not given, then
                         the default profile is used.
    """
    def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
                 aws_session_token=None, region_name=None,
                 botocore_session=None, profile_name=None, loop=None):
        if botocore_session is not None:
            self._session = botocore_session
        else:
            # Create a new default session
            self._session = aiobotocore.session.get_session(loop=loop)

        # Setup custom user-agent string if it isn't already customized
        if self._session.user_agent_name == 'Botocore':
            botocore_info = 'Botocore/{0}'.format(
                self._session.user_agent_version)
            if self._session.user_agent_extra:
                self._session.user_agent_extra += ' ' + botocore_info
            else:
                self._session.user_agent_extra = botocore_info
            self._session.user_agent_name = 'Boto3'
            self._session.user_agent_version = boto3.__version__

        if profile_name is not None:
            self._session.set_config_variable('profile', profile_name)

        if aws_access_key_id or aws_secret_access_key or aws_session_token:
            self._session.set_credentials(
                aws_access_key_id, aws_secret_access_key, aws_session_token)

        if region_name is not None:
            self._session.set_config_variable('region', region_name)

        self.resource_factory = AIOBoto3ResourceFactory(
            self._session.get_component('event_emitter'))
        self._setup_loader()
        self._register_default_handlers()

    def resource(self, *args, **kwargs):
        result = super(Session, self).resource(*args, **kwargs)

        return result
