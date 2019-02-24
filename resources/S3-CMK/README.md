# JAVA S3 Client-Side Encryption Example

Its horrible java, controlled via ENV vars

You'll also need bouncycastle set up, then you can run `gradle run`

## KMS Encryption

AUTHENTICATED_CRYPTO=1;S3_KEY=test-kms-cse

* CRYPTO_TYPE=kms - Use KMS crypto
* S3_BUCKET_NAME - Bucket name
* S3_KEY - path to create file in bucket
* REGION - KMS Region
* KMS_ID - KMS key id or `alias/blah`
* AUTHENTICATED_CRYPTO=1 - if you want AES-GCM crypto, make sure this env var is present


## Symmetric Encryption

* CRYPTO_TYPE=symmetric - Use KMS crypto
* S3_BUCKET_NAME - Bucket name
* S3_KEY - path to create file in bucket
* REGION - KMS Region
* KEY_DIR - Directory to store key

## Asymmetric Encryption

* CRYPTO_TYPE=asymmetric - Use KMS crypto
* S3_BUCKET_NAME - Bucket name
* S3_KEY - path to create file in bucket
* REGION - KMS Region
* KEY_DIR - Directory to store key
