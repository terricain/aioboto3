========================
Async AWS SDK for Python
========================


.. image:: https://img.shields.io/pypi/v/aioboto3.svg
        :target: https://pypi.python.org/pypi/aioboto3

.. image:: https://img.shields.io/travis/terrycain/aioboto3.svg
        :target: https://travis-ci.org/terrycain/aioboto3

.. image:: https://readthedocs.org/projects/aioboto3/badge/?version=latest
        :target: https://aioboto3.readthedocs.io
        :alt: Documentation Status

.. image:: https://pyup.io/repos/github/terrycain/aioboto3/shield.svg
     :target: https://pyup.io/repos/github/terrycain/aioboto3/
     :alt: Updates


This package is mostly just a wrapper combining the great work of boto3_ and aiobotocore_.

aiobotocore allows you to use near enough all of the boto3 client commands in an async manner just by prefixing the command with `await`.

With aioboto3 you can now usxe the higher level APIs provided by boto3 in an asynchronous manner. Mainly I developed this as I wanted to use the boto3 dynamodb Table object in some async
microservices.

While all resources in boto3 should work I havent tested them all, so if what your after is not in the table below then try it out, if it works drop me an issue with a simple test case
and I'll add it to the table.

+---------------------------+--------------------+
| Services                  | Status             |
+===========================+====================+
| DynamoDB Service Resource | Tested and working |
+---------------------------+--------------------+
| DynamoDB Table            | Tested and working |
+---------------------------+--------------------+
| S3                        | Working            |
+---------------------------+--------------------+
| Kinesis                   | Working            |
+---------------------------+--------------------+
| SSM Parameter Store       | Working            |
+---------------------------+--------------------+
| Athena                    | Working            |
+---------------------------+--------------------+


Example
-------

Simple example of using aioboto3 to put items into a dynamodb table

.. code-block:: python

    import asyncio
    import aioboto3
    from boto3.dynamodb.conditions import Key


    async def main():
        async with aioboto3.resource('dynamodb', region_name='eu-central-1') as dynamo_resource:
            table = dynamo_resource.Table('test_table')

            await table.put_item(
                Item={'pk': 'test1', 'col1': 'some_data'}
            )

            result = await table.query(
                KeyConditionExpression=Key('pk').eq('test1')
            )

            print(result['Items'])

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

    # Outputs:
    #  [{'col1': 'some_data', 'pk': 'test1'}]


Things that either dont work or have been patched
-------------------------------------------------

As this library literally wraps boto3, its inevitable that some things won't magically be async.

- ``s3_client.copy``  This is performed by the s3transfer module. I believe ``s3_client.copy_object`` performs the same function

Fixed:

- ``s3_client.download_file*``  This is performed by the s3transfer module. -- Patched with get_object
- ``s3_client.upload_file*``  This is performed by the s3transfer module. -- Patched with put_object
- ``dynamodb_resource.Table.batch_writer``  This now returns an async context manager which performs the same function

Documentation
-------------

Docs are here - https://aioboto3.readthedocs.io/en/latest/

Examples here - https://aioboto3.readthedocs.io/en/latest/usage.html


Features
========

* Closely mimics the usage of boto3.

Todo
====

* More Examples
* Set up docs
* Look into monkey-patching the aws xray sdk to be more async if it needs to be.


Credits
-------

This package was created with Cookiecutter_ and the `audreyr/cookiecutter-pypackage`_ project template.
It also makes use of the aiobotocore_ and boto3_ libraries. All the credit goes to them, this is mainly a wrapper with some examples.

.. _aiobotocore: https://github.com/aio-libs/aiobotocore
.. _boto3: https://github.com/boto/boto3
.. _Cookiecutter: https://github.com/audreyr/cookiecutter
.. _`audreyr/cookiecutter-pypackage`: https://github.com/audreyr/cookiecutter-pypackage
