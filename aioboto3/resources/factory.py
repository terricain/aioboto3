import logging
from functools import partial

from boto3.resources.factory import ResourceFactory
from boto3.resources.model import ResourceModel
from boto3.resources.base import ResourceMeta
from boto3.docs import docstring
from boto3.exceptions import ResourceLoadException
from boto3.resources.factory import build_identifiers

from aioboto3.resources.collection import AIOCollectionFactory
from aioboto3.resources.action import AIOServiceAction, AIOWaiterAction
from aioboto3.resources.base import AIOBoto3ServiceResource

logger = logging.getLogger(__name__)


class AIOBoto3ResourceFactory(ResourceFactory):
    # noinspection PyMissingConstructor
    def __init__(self, emitter):
        self._collection_factory = AIOCollectionFactory()
        self._emitter = emitter

    async def load_from_definition(self, resource_name,
                                   single_resource_json_definition, service_context):
        logger.debug('Loading %s:%s', service_context.service_name,
                     resource_name)

        # Using the loaded JSON create a ResourceModel object.
        resource_model = ResourceModel(
            resource_name,
            single_resource_json_definition,
            service_context.resource_json_definitions
        )

        # Do some renaming of the shape if there was a naming collision
        # that needed to be accounted for.
        shape = None
        if resource_model.shape:
            shape = service_context.service_model.shape_for(
                resource_model.shape
            )
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
            attrs=attrs,
            meta=meta,
            resource_name=resource_name,
            resource_model=resource_model
        )

        # Load/Reload actions
        self._load_actions(
            attrs=attrs,
            resource_name=resource_name,
            resource_model=resource_model,
            service_context=service_context
        )

        # Attributes that get auto-loaded
        self._load_attributes(
            attrs=attrs,
            meta=meta,
            resource_name=resource_name,
            resource_model=resource_model,
            service_context=service_context)

        # Collections and their corresponding methods
        self._load_collections(
            attrs=attrs,
            resource_model=resource_model,
            service_context=service_context)

        # References and Subresources
        self._load_has_relations(
            attrs=attrs,
            resource_name=resource_name,
            resource_model=resource_model,
            service_context=service_context
        )

        # Waiter resource actions
        self._load_waiters(
            attrs=attrs,
            resource_name=resource_name,
            resource_model=resource_model,
            service_context=service_context
        )

        # Create the name based on the requested service and resource
        cls_name = resource_name
        if service_context.service_name == resource_name:
            cls_name = 'ServiceResource'
        cls_name = service_context.service_name + '.' + cls_name

        base_classes = [AIOBoto3ServiceResource]
        if self._emitter is not None:
            await self._emitter.emit(
                'creating-resource-class.%s' % cls_name,
                class_attributes=attrs,
                base_classes=base_classes,
                service_context=service_context
            )
        return type(str(cls_name), tuple(base_classes), attrs)

    def _create_autoload_property(
        factory_self,
        resource_name,
        name,
        snake_cased,
        member_model,
        service_context
    ):
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

    def _create_waiter(
        factory_self, resource_waiter_model, resource_name, service_context
    ):
        """
        Creates a new wait method for each resource where both a waiter and
        resource model is defined.
        """
        waiter = AIOWaiterAction(
            resource_waiter_model,
            waiter_resource_name=resource_waiter_model.name
        )

        async def do_waiter(self, *args, **kwargs):
            await waiter(self, *args, **kwargs)

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

    def _create_class_partial(
        factory_self, subresource_model, resource_name, service_context
    ):
        """
        Creates a new method which acts as a functools.partial, passing
        along the instance's low-level `client` to the new resource
        class' constructor.
        """
        name = subresource_model.resource.type

        async def create_resource(self, *args, **kwargs):
            # We need a new method here because we want access to the
            # instance's client.
            positional_args = []

            # We lazy-load the class to handle circular references.
            json_def = service_context.resource_json_definitions.get(name, {})
            resource_cls = await factory_self.load_from_definition(
                resource_name=name,
                single_resource_json_definition=json_def,
                service_context=service_context
            )

            # Assumes that identifiers are in order, which lets you do
            # e.g. ``sqs.Queue('foo').Message('bar')`` to create a new message
            # linked with the ``foo`` queue and which has a ``bar`` receipt
            # handle. If we did kwargs here then future positional arguments
            # would lead to failure.
            identifiers = subresource_model.resource.identifiers
            if identifiers is not None:
                for identifier, value in build_identifiers(identifiers, self):
                    positional_args.append(value)

            return partial(
                resource_cls, *positional_args, client=self.meta.client
            )(*args, **kwargs)

        create_resource.__name__ = str(name)
        create_resource.__doc__ = docstring.SubResourceDocstring(
            resource_name=resource_name,
            sub_resource_model=subresource_model,
            service_model=service_context.service_model,
            include_signature=False
        )
        return create_resource

    def _create_action(
        factory_self,
        action_model,
        resource_name,
        service_context,
        is_load=False
    ):
        """
        Creates a new method which makes a request to the underlying
        AWS service.
        """
        # Create the action in in this closure but before the ``do_action``
        # method below is invoked, which allows instances of the resource
        # to share the ServiceAction instance.
        action = AIOServiceAction(
            action_model, factory=factory_self, service_context=service_context
        )

        # A resource's ``load`` method is special because it sets
        # values on the resource instead of returning the response.
        if is_load:
            # We need a new method here because we want access to the
            # instance via ``self``.
            async def do_action(self, *args, **kwargs):
                response = await action(self, *args, **kwargs)
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
                response = await action(self, *args, **kwargs)

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

