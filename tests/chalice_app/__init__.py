from aioboto3.experimental.async_chalice import AsyncChalice

app = AsyncChalice(app_name='testclient')


@app.route('/hello/{name}')
async def hello(name):
    return {'hello': name}


@app.route('/list_buckets')
async def get_list_buckets():
    async with app.aioboto3.client("s3") as s3:
        resp = await s3.list_buckets()

    return {"buckets": [bucket['Name'] for bucket in resp['Buckets']]}
