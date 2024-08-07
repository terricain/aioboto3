import asyncio
from typing import Optional

from chalice import Chalice
from chalice.app import RestAPIEventHandler

from aioboto3 import Session


class AsyncRestAPIEventHandler(RestAPIEventHandler):
    def _get_view_function_response(self, view_function, function_args):
        # Wrap the view_function so that we can return either the normal response
        # or if its a co-routine, run it in an event loop first.
        # Saves duplicating the whole function.
        def _fake_view_function(**kwargs):
            response = view_function(**kwargs)
            if asyncio.iscoroutine(response):
                # Always run in a new loop as chalice would close an existing one anyway
                new_loop = asyncio.new_event_loop()
                response = new_loop.run_until_complete(response)
                new_loop.close()

            return response
        return super(AsyncRestAPIEventHandler, self)._get_view_function_response(_fake_view_function, function_args)


class AsyncChalice(Chalice):
    def __init__(self, *args, aioboto3_session: Optional[Session] = None, **kwargs):
        super(AsyncChalice, self).__init__(*args, **kwargs)

        self.aioboto3 = aioboto3_session or Session()

    def __call__(self, event, context):
        self.lambda_context = context
        handler = AsyncRestAPIEventHandler(
            self.routes, self.api, self.log, self.debug,
            middleware_handlers=self._get_middleware_handlers('http')
        )
        self.current_request = handler.create_request_object(event, context)
        return handler(event, context)

