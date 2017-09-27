import asyncio
import logging
import sys

from boto3.resources.factory import ResourceFactory
from boto3.resources.model import ResourceModel
from boto3.resources.base import ServiceResource, ResourceMeta
from boto3.resources.action import ServiceAction
from boto3.docs import docstring
from botocore import xform_name
from boto3.resources.params import create_request_parameters
import inspect


PY_35 = sys.version_info >= (3, 5)

logger = logging.getLogger(__name__)


class AIOServiceAction(ServiceAction):
    def __call__(self, parent, *args, **kwargs):
        """
        Perform the action's request operation after building operation
        parameters and build any defined resources from the response.

        :type parent: :py:class:`~boto3.resources.base.ServiceResource`
        :param parent: The resource instance to which this action is attached.
        :rtype: dict or ServiceResource or list(ServiceResource)
        :return: The response, either as a raw dict or resource instance(s).
        """
        operation_name = xform_name(self._action_model.request.operation)

        # First, build predefined params and then update with the
        # user-supplied kwargs, which allows overriding the pre-built
        # params if needed.
        params = create_request_parameters(parent, self._action_model.request)
        params.update(kwargs)

        logger.debug('Calling %s:%s with %r', parent.meta.service_name,
                    operation_name, params)

        response = yield from getattr(parent.meta.client, operation_name)(**params)

        logger.debug('Response: %r', response)

        return self._response_handler(parent, params, response)


class AIOBoto3ServiceResource(ServiceResource):
    if PY_35:
        @asyncio.coroutine
        def __aenter__(self):
            return self

        @asyncio.coroutine
        def __aexit__(self, exc_type, exc_val, exc_tb):
            yield from self.meta.client.close()
            return False

    def close(self):
        return self.meta.client.close()


class AIOBoto3ResourceFactory(ResourceFactory):
    def load_from_definition(self, resource_name,
                             single_resource_json_definition, service_context):
        """
        Loads a resource from a model, creating a new
        :py:class:`~boto3.resources.base.ServiceResource` subclass
        with the correct properties and methods, named based on the service
        and resource name, e.g. EC2.Instance.

        :type resource_name: string
        :param resource_name: Name of the resource to look up. For services,
                              this should match the ``service_name``.

        :type single_resource_json_definition: dict
        :param single_resource_json_definition:
            The loaded json of a single service resource or resource
            definition.

        :type service_context: :py:class:`~boto3.utils.ServiceContext`
        :param service_context: Context about the AWS service

        :rtype: Subclass of :py:class:`~boto3.resources.base.ServiceResource`
        :return: The service or resource class.
        """
        logger.debug('Loading %s:%s', service_context.service_name,
                     resource_name)

        # Using the loaded JSON create a ResourceModel object.
        resource_model = ResourceModel(
            resource_name, single_resource_json_definition,
            service_context.resource_json_definitions
        )

        # Do some renaming of the shape if there was a naming collision
        # that needed to be accounted for.
        shape = None
        if resource_model.shape:
            shape = service_context.service_model.shape_for(
                resource_model.shape)
        resource_model.load_rename_map(shape)

        # Set some basic info
        meta = ResourceMeta(
            service_context.service_name, resource_model=resource_model)
        attrs = {
            'meta': meta,
        }

        # Create and load all of attributes of the resource class based
        # on the models.

        # Identifiers
        self._load_identifiers(
            attrs=attrs, meta=meta, resource_name=resource_name,
            resource_model=resource_model
        )

        # Load/Reload actions
        self._load_actions(
            attrs=attrs, resource_name=resource_name,
            resource_model=resource_model, service_context=service_context
        )

        # Attributes that get auto-loaded
        self._load_attributes(
            attrs=attrs, meta=meta, resource_name=resource_name,
            resource_model=resource_model,
            service_context=service_context)

        # Collections and their corresponding methods
        self._load_collections(
            attrs=attrs, resource_model=resource_model,
            service_context=service_context)

        # References and Subresources
        self._load_has_relations(
            attrs=attrs, resource_name=resource_name,
            resource_model=resource_model, service_context=service_context
        )

        # Waiter resource actions
        self._load_waiters(
            attrs=attrs, resource_name=resource_name,
            resource_model=resource_model, service_context=service_context
        )

        # Create the name based on the requested service and resource
        cls_name = resource_name
        if service_context.service_name == resource_name:
            cls_name = 'AIOServiceResource'
        cls_name = service_context.service_name + '.' + cls_name

        base_classes = [AIOBoto3ServiceResource]
        if self._emitter is not None:
            self._emitter.emit(
                'creating-resource-class.%s' % cls_name,
                class_attributes=attrs, base_classes=base_classes,
                service_context=service_context)
        return type(str(cls_name), tuple(base_classes), attrs)

    def _create_action(factory_self, action_model, resource_name,
                       service_context, is_load=False):
        """
        Creates a new method which makes a request to the underlying
        AWS service.
        """
        # Create the action in in this closure but before the ``do_action``
        # method below is invoked, which allows instances of the resource
        # to share the ServiceAction instance.
        action = AIOServiceAction(
            action_model, factory=factory_self,
            service_context=service_context
        )

        # A resource's ``load`` method is special because it sets
        # values on the resource instead of returning the response.
        if is_load:
            # We need a new method here because we want access to the
            # instance via ``self``.
            @asyncio.coroutine
            def do_action(self, *args, **kwargs):
                response = action(self, *args, **kwargs)
                self.meta.data = response

            # Create the docstring for the load/reload mehtods.
            lazy_docstring = docstring.LoadReloadDocstring(
                action_name=action_model.name,
                resource_name=resource_name,
                event_emitter=factory_self._emitter,
                load_model=action_model,
                service_model=service_context.service_model,
                include_signature=False
            )
        else:
            # We need a new method here because we want access to the
            # instance via ``self``.
            @asyncio.coroutine
            def do_action(self, *args, **kwargs):
                response = action(self, *args, **kwargs)

                if hasattr(self, 'load'):
                    # Clear cached data. It will be reloaded the next
                    # time that an attribute is accessed.
                    # TODO: Make this configurable in the future?
                    self.meta.data = None

                return response

            lazy_docstring = docstring.ActionDocstring(
                resource_name=resource_name,
                event_emitter=factory_self._emitter,
                action_model=action_model,
                service_model=service_context.service_model,
                include_signature=False
            )

        do_action.__name__ = str(action_model.name)
        do_action.__doc__ = lazy_docstring
        return do_action
