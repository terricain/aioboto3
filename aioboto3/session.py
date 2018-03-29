# -*- coding: utf-8 -*-
"""
This class essentially overrides the boto3 session init, passing in
an async botocore session
"""


import aiobotocore.session
import boto3.session
import boto3.resources.base
import boto3.utils

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

    def _register_default_handlers(self):

        # S3 customizations
        self._session.register(
            'creating-client-class.s3',
            boto3.utils.lazy_call(
                'aioboto3.s3.inject.inject_s3_transfer_methods'))
        self._session.register(
            'creating-resource-class.s3.Bucket',
            boto3.utils.lazy_call(
                'boto3.s3.inject.inject_bucket_methods'))
        self._session.register(
            'creating-resource-class.s3.Object',
            boto3.utils.lazy_call(
                'boto3.s3.inject.inject_object_methods'))
        self._session.register(
            'creating-resource-class.s3.ObjectSummary',
            boto3.utils.lazy_call(
                'boto3.s3.inject.inject_object_summary_methods'))

        # DynamoDb customizations
        self._session.register(
            'creating-resource-class.dynamodb',
            boto3.utils.lazy_call(
                'boto3.dynamodb.transform.register_high_level_interface'),
            unique_id='high-level-dynamodb')
        self._session.register(
            'creating-resource-class.dynamodb.Table',
            boto3.utils.lazy_call(
                'aioboto3.dynamodb.table.register_table_methods'),
            unique_id='high-level-dynamodb-table')

        # EC2 Customizations
        self._session.register(
            'creating-resource-class.ec2.ServiceResource',
            boto3.utils.lazy_call(
                'boto3.ec2.createtags.inject_create_tags'))

        self._session.register(
            'creating-resource-class.ec2.Instance',
            boto3.utils.lazy_call(
                'boto3.ec2.deletetags.inject_delete_tags',
                event_emitter=self.events))

    def resource(self, *args, **kwargs):
        result = super(Session, self).resource(*args, **kwargs)

        return result
