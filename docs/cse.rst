=============================
AWS S3 Client-side Encryption
=============================

How it works (KMS Managed Keys)
-------------------------------

Overall the entire procedure isn't incredibly complex, just not very well documented (unless my google skills are failing me).
And I may be wrong, but the Java SDK decrypts files made with this and the library can decrypt the Java made files.

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
the bytestring, the padding is a fixed value (less than 256) which is the same number as how many bytes to remove (lookup PKCS5Padding).

If GCM was used, during the decryption a tag appened to the plaintext is also verified for some added protection.

Encryption
++++++++++

Simply enough, you do the majority of the above... backwards.

Call the ``generate_data_key`` KMS API (with the encryption context) to get both an encrypted AES key and decypted AES key.
Generete IV's. Encrypt your data. Assemble all the required metadata (use the KMS provided encrypted AES key for ``x-amz-key-v2``), then push to S3.


How it works (Symmetric Keys)
-----------------------------

The method is pretty similar. The encryption key is stored in ``x-amz-key``, its encrypted with AES/ECB/PKCS5Padding :/
Then the object's data is always encrypted with AES/CBC/PKCS5Padding which means no range downloads.


How it works (Asymmetric Keys)
------------------------------

Once again its pretty similar, but this time the encryption key is encrypted/decrypted with RSA/ECB/PKCS1Padding


CryptoContext Class
-------------------

This class performs 2 main functions. It converts the objects encrypted key metadata into a decryption key and it will generate an
encryption key with corresponding encrypted encryption key that's base64 encoded.

For example when decrypting a file using KMS managed client side encryption. It would pass the encrypted key to ``KMS.decrypt`` along
with the "material description" (``x-amz-matdesc`` metadata header) and KMS will return the original AES key.

Similar for encrypting a file, it will call KMS to generate a data key, it will then return an AES key, appropiate material description
metadata and a base64'd encrypted form of the AES key.

+---------------------------------------------------+-------------------------------------------+
| CryptoContext Class                               | Description                               |
+===================================================+===========================================+
| :class:`aioboto3.s3.cse.KMSCryptoContext`         | Performs CSE using KMS managed keys       |
+---------------------------------------------------+-------------------------------------------+
| :class:`aioboto3.s3.cse.AsymmetricCryptoContext`  | Performs CSE using public / private keys  |
+---------------------------------------------------+-------------------------------------------+
| :class:`aioboto3.s3.cse.SymmetricCryptoContext`   | Performs CSE using a single symmetric key |
+---------------------------------------------------+-------------------------------------------+


Example
-------

.. code-block:: python

    import asyncio
    import aioboto3
    from aioboto3.s3.cse import S3CSE, KMSCryptoContext

    async def main():
        ctx = KMSCryptoContext(keyid='alias/someKey', kms_client_args={'region_name': 'eu-central-1'})

        some_data = b'Some sensitive data for S3'

        async with S3CSE(crypto_context=ctx, s3_client_args={'region_name': 'eu-central-1'}) as s3_cse:
            # Upload some binary data
            await s3_cse.put_object(
                Body=some_data,
                Bucket='some-bucket',
                Key='encrypted_file',
            )

            response = await s3_cse.get_object(
                Bucket='some-bucket',
                Key='encrypted_file'
            )
            data = await response['Body'].read()
            print(data)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

    # Outputs:
    #  b'Some sensitive data for S3'
