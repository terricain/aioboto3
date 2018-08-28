=======
History
=======

4.1.0 (2018-08-28)
------------------

* aiobotocore dependancy bump

4.0.2 (2018-08-03)
------------------

* Dependancy bump

4.0.0 (2018-05-09)
------------------

* Dependancy bump
* Now using aiobotocore 0.8.0
* Dropped < py3.5 support
* Now using async def / await syntax
* Fixed boto3 dependancy so it only uses a boto3 version supported by aiobotocore's max botocore dependancy
* Important, ```__call__``` in ```AIOServiceAction``` tries to yield from a coroutine in a non-coroutine, this code shouldn't be hit
  anymore but I can't guarantee that, so instead ```__call__``` was duplicated and awaited properly so "should" be fine.
  Credit goes to Arnulfo Solis for doing PR.

3.0.0 (2018-03-29)
------------------

* Dependancy bump
* Asyncified dynamodb Table Batch Writer + Tests
* Added batch writer examples
* Now using aiobotocore 0.6.0

2.2.0 (2018-01-24)
------------------

* Dependancy bump

2.1.0 (2018-01-23)
------------------

* Dependancy bump
* Fix bug where extras isn't packaged

2.0.0 (2017-12-30)
------------------

* Patched most s3transfer functions

1.1.2 (2017-11-29)
------------------

* Fixup of lingering GPL license texts

0.1.0 (2017-09-25)
------------------

* First release on PyPI.
