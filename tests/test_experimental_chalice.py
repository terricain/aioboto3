import aioboto3
import boto3
import pytest
from chalice_app import app

from chalice.test import Client


def test_chalice_async_http(moto_patch, region, bucket_name):
    session = aioboto3.Session()

    app.aioboto3 = session

    with Client(app) as client:
        response = client.http.get('/hello/myname')
        assert response.status_code == 200
        assert response.json_body['hello'] == 'myname'


def test_chalice_async_http_s3_client(moto_patch, region, bucket_name):
    session = aioboto3.Session()

    app.aioboto3 = session

    s3 = boto3.client('s3', region_name=region)
    s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration={'LocationConstraint': region})
    resp = s3.list_buckets()
    bucket_response = [bucket['Name'] for bucket in resp['Buckets']]

    with Client(app) as client:
        response = client.http.get('/list_buckets')
        assert response.status_code == 200
        assert response.json_body['buckets'] == bucket_response
