import logging
from typing import cast, AsyncIterator, Any

from botocore import xform_name
from boto3.resources.action import ServiceAction
from boto3.resources.params import create_request_parameters


logger = logging.getLogger(__name__)


class AioBatchAction(ServiceAction):
    """
    An action which operates on a batch of items in a collection, typically
    a single page of results from the collection's underlying service
    operation call. For example, this allows you to delete up to 999
    S3 objects in a single operation rather than calling ``.delete()`` on
    each one individually.

    :type action_model: :py:class`~boto3.resources.model.Action`
    :param action_model: The action model.

    :type factory: ResourceFactory
    :param factory: The factory that created the resource class to which
                    this action is attached.

    :type service_context: :py:class:`~boto3.utils.ServiceContext`
    :param service_context: Context about the AWS service
    """
    async def __call__(self, parent, *args, **kwargs):
        """
        Perform the batch action's operation on every page of results
        from the collection.

        :type parent:
            :py:class:`~boto3.resources.collection.ResourceCollection`
        :param parent: The collection iterator to which this action
                       is attached.
        :rtype: list(dict)
        :return: A list of low-level response dicts from each call.
        """
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

            response = await (getattr(client, operation_name)(**params))

            logger.debug('Response: %r', response)

            responses.append(
                self._response_handler(parent, params, response))

        return responses
