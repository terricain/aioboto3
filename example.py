"""
contextlib.AsyncExitStack requires python 3.7
"""
import contextlib

import aioboto3
from boto3.dynamodb.conditions import Key
from aiohttp import web

routes = web.RouteTableDef()


@routes.get('/')
async def hello(request):

    # request.app['table'] == Table object from boto3 docs
    response = await request.app['table'].query(
        KeyConditionExpression=Key('id').eq('lalalala')
    )

    return web.Response(text=str(response))


async def startup_tasks(app: web.Application) -> None:
    context_stack = contextlib.AsyncExitStack()
    app['context_stack'] = context_stack

    app['dynamo_resource'] = await context_stack.enter_async_context(
        aioboto3.resource('dynamodb', region_name='eu-west-1')
    )
    # By now, app['dynamo_resource'] will have methods like .Table() and list_tables() etc...

    # aioboto3 v8.0.0+ all service resources (aka Table(), Bucket() etc...) need to be awaited
    app['table'] = await app['dynamo_resource'].Table('somedynamodbtablename')


async def shutdown_tasks(app: web.Application) -> None:
    await app['context_stack'].aclose()
    # By now, app['dynamo_resource'] would be closed


_app = web.Application()
_app.add_routes(routes)
_app.on_startup.append(startup_tasks)
# _app.on_shutdown.append(shutdown_tasks)
web.run_app(_app, port=8000)
