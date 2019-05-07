import logging

from boto3.resources.factory import ResourceFactory
from boto3.resources.model import ResourceModel
from boto3.resources.base import ServiceResource, ResourceMeta
from boto3.resources.action import ServiceAction
from boto3.docs import docstring
from botocore import xform_name
from boto3.exceptions import ResourceLoadException
from boto3.resources.params import create_request_parameters


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

    async def async_call(self, parent, *args, **kwargs):
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

        response = await getattr(parent.meta.client, operation_name)(**params)

        logger.debug('Response: %r', response)

        return self._response_handler(parent, params, response)


class AIOWaiterAction(object):
    """
    A class representing a callable waiter action on a resource, for example
    ``s3.Bucket('foo').wait_until_bucket_exists()``.
    The waiter action may construct parameters from existing resource
    identifiers.

    :type waiter_model: :py:class`~boto3.resources.model.Waiter`
    :param waiter_model: The action waiter.
    :type waiter_resource_name: string
    :param waiter_resource_name: The name of the waiter action for the
                                 resource. It usually begins with a
                                 ``wait_until_``
    """
    def __init__(self, waiter_model, waiter_resource_name):
        self._waiter_model = waiter_model
        self._waiter_resource_name = waiter_resource_name

    def __call__(self, parent, *args, **kwargs):
        """
        Perform the wait operation after building operation
        parameters.

        :type parent: :py:class:`~boto3.resources.base.ServiceResource`
        :param parent: The resource instance to which this action is attached.
        """
        client_waiter_name = xform_name(self._waiter_model.waiter_name)

        # First, build predefined params and then update with the
        # user-supplied kwargs, which allows overriding the pre-built
        # params if needed.
        params = create_request_parameters(parent, self._waiter_model)
        params.update(kwargs)

        logger.debug('Calling %s:%s with %r',
                    parent.meta.service_name,
                    self._waiter_resource_name, params)

        client = parent.meta.client
        waiter = client.get_waiter(client_waiter_name)
        response = waiter.wait(**params)

        logger.debug('Response: %r', response)

    async def async_call(self, parent, *args, **kwargs):
        """
        Perform the wait operation after building operation
        parameters.

        :type parent: :py:class:`~boto3.resources.base.ServiceResource`
        :param parent: The resource instance to which this action is attached.
        """
        client_waiter_name = xform_name(self._waiter_model.waiter_name)

        # First, build predefined params and then update with the
        # user-supplied kwargs, which allows overriding the pre-built
        # params if needed.
        params = create_request_parameters(parent, self._waiter_model)
        params.update(kwargs)

        logger.debug('Calling %s:%s with %r',
                    parent.meta.service_name,
                    self._waiter_resource_name, params)

        client = parent.meta.client
        waiter = client.get_waiter(client_waiter_name)
        response = await waiter.wait(**params)

        logger.debug('Response: %r', response)


class AIOBoto3ServiceResource(ServiceResource):
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.meta.client.close()
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
            cls_name = 'ServiceResource'
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
            async def do_action(self, *args, **kwargs):
                # response = action(self, *args, **kwargs)
                response = await action.async_call(self, *args, **kwargs)
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
            async def do_action(self, *args, **kwargs):
                response = await action.async_call(self, *args, **kwargs)

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

    def _create_waiter(factory_self, resource_waiter_model, resource_name,
                       service_context):
        """
        Creates a new wait method for each resource where both a waiter and
        resource model is defined.
        """
        waiter = AIOWaiterAction(resource_waiter_model,
                                 waiter_resource_name=resource_waiter_model.name)

        async def do_waiter(self, *args, **kwargs):
            await waiter.async_call(self, *args, **kwargs)

        do_waiter.__name__ = str(resource_waiter_model.name)
        do_waiter.__doc__ = docstring.ResourceWaiterDocstring(
            resource_name=resource_name,
            event_emitter=factory_self._emitter,
            service_model=service_context.service_model,
            resource_waiter_model=resource_waiter_model,
            service_waiter_model=service_context.service_waiter_model,
            include_signature=False
        )
        return do_waiter

    def _create_autoload_property(factory_self, resource_name, name,
                                  snake_cased, member_model, service_context):
        """
        Creates a new property on the resource to lazy-load its value
        via the resource's ``load`` method (if it exists).
        """
        # The property loader will check to see if this resource has already
        # been loaded and return the cached value if possible. If not, then
        # it first checks to see if it CAN be loaded (raise if not), then
        # calls the load before returning the value.
        async def property_loader(self):
            if self.meta.data is None:
                if hasattr(self, 'load'):
                    await self.load()
                else:
                    raise ResourceLoadException(
                        '{0} has no load method'.format(
                            self.__class__.__name__))

            return self.meta.data.get(name)

        property_loader.__name__ = str(snake_cased)
        property_loader.__doc__ = docstring.AttributeDocstring(
            service_name=service_context.service_name,
            resource_name=resource_name,
            attr_name=snake_cased,
            event_emitter=factory_self._emitter,
            attr_model=member_model,
            include_signature=False
        )

        return property(property_loader)
