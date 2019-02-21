# JAVA S3 Client-Side Encryption Example

It requires the following environment variables to be exported

* S3_BUCKET_NAME - Bucket name
* S3_KEY - path to create file in bucket
* KMS_REGION - KMS Region
* KMS_ID - KMS key id or `alias/blah`

You'll also need bouncycastle set up, then you can run `gradle run`
