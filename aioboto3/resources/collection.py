import logging
from typing import AsyncIterator, Any, cast

from boto3.docs import docstring
from boto3.resources.collection import CollectionFactory, ResourceCollection, CollectionManager, merge_dicts
from boto3.resources.params import create_request_parameters

from aioboto3.resources.action import AioBatchAction, AIOResourceHandler

logger = logging.getLogger(__name__)


class AIOResourceCollection(ResourceCollection):
    """
    Converted the ResourceCollection.pages() function to an async generator so that we can do
    async for on a paginator inside that function

    Converted the __iter__
    """
    async def __anext__(self):
        limit = self._params.get('limit', None)

        count = 0
        async for page in cast(AsyncIterator[Any], self.pages()):
            for item in page:
                yield item

                count += 1
                if limit is not None and count >= limit:
                    return

    def __aiter__(self):
        return self.__anext__()

    def __iter__(self):
        raise NotImplementedError('Use async-for instead')

    async def pages(self):
        client = self._parent.meta.client
        cleaned_params = self._params.copy()
        limit = cleaned_params.pop('limit', None)
        page_size = cleaned_params.pop('page_size', None)
        params = create_request_parameters(self._parent, self._model.request)
        merge_dicts(params, cleaned_params, append_lists=True)

        # Is this a paginated operation? If so, we need to get an
        # iterator for the various pages. If not, then we simply
        # call the operation and return the result as a single
        # page in a list. For non-paginated results, we just ignore
        # the page size parameter.
        if client.can_paginate(self._py_operation_name):
            logger.debug(
                'Calling paginated %s:%s with %r',
                self._parent.meta.service_name,
                self._py_operation_name,
                params
            )
            paginator = client.get_paginator(self._py_operation_name)
            pages = paginator.paginate(
                PaginationConfig={'MaxItems': limit, 'PageSize': page_size},
                **params
            )
        else:
            async def _aiopaginatordummy():
                yield await getattr(client, self._py_operation_name)(**params)

            logger.debug(
                'Calling %s:%s with %r',
                self._parent.meta.service_name,
                self._py_operation_name,
                params
            )
            pages = _aiopaginatordummy()

        # Now that we have a page iterator or single page of results
        # we start processing and yielding individual items.
        count = 0
        async for page in pages:
            page_items = []
            for item in await self._handler(self._parent, params, page):
                page_items.append(item)

                # If the limit is set and has been reached, then
                # we stop processing items here.
                count += 1
                if limit is not None and count >= limit:
                    break

            yield page_items

            # Stop reading pages if we've reached out limit
            if limit is not None and count >= limit:
                break


class AIOCollectionManager(CollectionManager):
    _collection_cls = AIOResourceCollection

    def __init__(self, collection_model, parent, factory, service_context):
        self._model = collection_model
        operation_name = self._model.request.operation
        self._parent = parent

        search_path = collection_model.resource.path
        self._handler = AIOResourceHandler(
            search_path=search_path,
            factory=factory,
            resource_model=collection_model.resource,
            service_context=service_context,
            operation_name=operation_name
        )


class AIOCollectionFactory(CollectionFactory):
    def load_from_definition(
        self, resource_name, collection_model, service_context, event_emitter
    ):
        attrs = {}
        collection_name = collection_model.name

        # Create the batch actions for a collection
        self._load_batch_actions(
            attrs,
            resource_name,
            collection_model,
            service_context.service_model,
            event_emitter
        )
        # Add the documentation to the collection class's methods
        self._load_documented_collection_methods(
            attrs=attrs,
            resource_name=resource_name,
            collection_model=collection_model,
            service_model=service_context.service_model,
            event_emitter=event_emitter,
            base_class=AIOResourceCollection
        )

        if service_context.service_name == resource_name:
            cls_name = (
                f'{service_context.service_name}.{collection_name}Collection'
            )
        else:
            cls_name = f'{service_context.service_name}.{resource_name}.{collection_name}Collection'

        collection_cls = type(str(cls_name), (AIOResourceCollection,), attrs)

        # Add the documentation to the collection manager's methods
        self._load_documented_collection_methods(
            attrs=attrs,
            resource_name=resource_name,
            collection_model=collection_model,
            service_model=service_context.service_model,
            event_emitter=event_emitter,
            base_class=AIOCollectionManager
        )
        attrs['_collection_cls'] = collection_cls
        cls_name += 'Manager'

        return type(str(cls_name), (AIOCollectionManager,), attrs)

    def _create_batch_action(
        factory_self,
        resource_name,
        snake_cased,
        action_model,
        collection_model,
        service_model,
        event_emitter
    ):
        """
        Creates a new method which makes a batch operation request
        to the underlying service API.
        """
        action = AioBatchAction(action_model)

        def batch_action(self, *args, **kwargs):
            return action(self, *args, **kwargs)

        batch_action.__name__ = str(snake_cased)
        batch_action.__doc__ = docstring.BatchActionDocstring(
            resource_name=resource_name,
            event_emitter=event_emitter,
            batch_action_model=action_model,
            service_model=service_model,
            collection_model=collection_model,
            include_signature=False
        )
        return batch_action
