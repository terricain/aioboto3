=============================
AWS S3 Client-side Encryption
=============================

How it works (KMS Managed Keys)
-------------------------------

Overall the entire procedure isn't incredibly complex, just not very well documented (unless my google skills are failing me).

Decryption
++++++++++

Firstly get the object from S3, it'll have various crypto goodies in the object's metadata.

- metadata: ``x-amz-unencrypted-content-length`` - Resultant length of the plaintext
- metadata: ``x-amz-key-v2`` - this is the base64'd kms encrypted aes key.
- metadata: ``x-amz-matdesc`` - JSON KMS encryption context, has which KMS key encrypted the aes key
- metadata: ``x-amz-iv`` - AES IVs
- metadata: ``x-amz-cek-alg`` - Which AES aglorithm was used, AES/CBC/PKCS5Padding or AES/GCM/NoPadding
- metadata: ``x-amz-tag-len`` - If using AES-GCM then this is a fixed value of 128 otherwise it is not present
- metadata: ``x-amz-wrap-alg`` - Always KMS when using KMS managed master keys

Send ``x-amz-key-v2`` and ``x-amz-matdesc`` to KMS, that will return the decrypted AES key

Decode the file with either CBC or GCM based on ``x-amz-cek-alg``.

If CBC was used, you'll also need to remove the PKCS5Padding. This snippet would do that ``a = a[:-a[-1]]``, what it does is removes N bytes off the end of
the bytestring, the padding is a fixed value which is the same number as how many bytes to remove (lookup PKCS5Padding).

If GCM was used, during the decryption a tag appened to the plaintext is also verified for some added protection.

Encryption
++++++++++

Simply enough, you do the majority of the above... backwards.

Call the ``generate_data_key`` KMS API (with the encryption context) to get both an encrypted AES key and decypted AES key.
Generete IV's. Encrypt your data. Assemble all the required metadata (use the KMS provided encrypted AES key for ``x-amz-key-v2``), then push to S3.


Example
-------

.. code-block:: python

    import asyncio
    import aioboto3
    from aioboto3.s3.cse import S3CSE

    async def main():
        some_data = b'Some sensitive data for S3'

        async with S3CSE(s3_region='eu-central-1', kms_region='eu-central-1') as s3_cse:
            # Upload some binary data
            await s3_cse.put_object(
                Body=some_data
                Bucket='some-bucket',
                Key='encrypted_file',
                KMSKeyId='alias/some-KMSKey',
                AuthenticatedEncryption=True
            )

            result = await s3_cse.get_object(
                Bucket='some-bucket',
                Key='encrypted_file'
            )
            print(result)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

    # Outputs:
    #  b'Some sensitive data for S3'

As you can see from the arguments to S3CSE you can encrypt/decrypt using KMS in a different region to S3 (not that I'd advise it). ``AuthenticatedEncryption``
switches between AES-GCM (AE=True) and AES-CBC (AE=False)

The arguments to these functions needs some tweaking, currently you can't specify any other S3 put/get options but I'll be working on that.
