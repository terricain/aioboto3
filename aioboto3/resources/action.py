import logging

from boto3.resources.action import ServiceAction, WaiterAction
from boto3.resources.params import create_request_parameters
from boto3.resources.action import xform_name

from aioboto3.resources.response import AIOResourceHandler, AIORawHandler

logger = logging.getLogger(__name__)


class AIOServiceAction(ServiceAction):
    def __init__(self, action_model, factory=None, service_context=None):
        self._action_model = action_model

        # In the simplest case we just return the response, but if a
        # resource is defined, then we must create these before returning.
        resource_response_model = action_model.resource
        if resource_response_model:
            self._response_handler = AIOResourceHandler(
                search_path=resource_response_model.path,
                factory=factory,
                resource_model=resource_response_model,
                service_context=service_context,
                operation_name=action_model.request.operation
            )
        else:
            self._response_handler = AIORawHandler(action_model.path)

    async def __call__(self, parent, *args, **kwargs):
        operation_name = xform_name(self._action_model.request.operation)

        # First, build predefined params and then update with the
        # user-supplied kwargs, which allows overriding the pre-built
        # params if needed.
        params = create_request_parameters(parent, self._action_model.request)
        params.update(kwargs)

        logger.debug('Calling %s:%s with %r', parent.meta.service_name,
                     operation_name, params)

        response = await getattr(parent.meta.client, operation_name)(*args, **params)

        logger.debug('Response: %r', response)

        return await self._response_handler(parent, params, response)


class AioBatchAction(ServiceAction):
    async def __call__(self, parent, *args, **kwargs):
        service_name = None
        client = None
        responses = []
        operation_name = xform_name(self._action_model.request.operation)

        # Unlike the simple action above, a batch action must operate
        # on batches (or pages) of items. So we get each page, construct
        # the necessary parameters and call the batch operation.
        async for page in parent.pages():
            params = {}
            for index, resource in enumerate(page):
                # There is no public interface to get a service name
                # or low-level client from a collection, so we get
                # these from the first resource in the collection.
                if service_name is None:
                    service_name = resource.meta.service_name
                if client is None:
                    client = resource.meta.client

                create_request_parameters(
                    resource, self._action_model.request,
                    params=params, index=index)

            if not params:
                # There are no items, no need to make a call.
                break

            params.update(kwargs)

            logger.debug('Calling %s:%s with %r',
                         service_name, operation_name, params)

            response = await (getattr(client, operation_name)(*args, **params))

            logger.debug('Response: %r', response)

            responses.append(
                self._response_handler(parent, params, response))

        return responses


class AIOWaiterAction(WaiterAction):
    async def __call__(self, parent, *args, **kwargs):
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
