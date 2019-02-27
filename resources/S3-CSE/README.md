# JAVA S3 Client-Side Encryption Example

Its horrible java

You'll also need bouncycastle set up, then you can run `gradle fatJar`

## Options

This will output the options of the jar

```
java -jar build/libs/s3cse-1.0.jar -h
```

## KMS Encryption

```
java -jar build/libs/s3cse-1.0.jar --crypto-type kms --bucket-name bucket1 --key-name test-cse-kms \
                                   --region eu-west-1 --kms-key-id alias/someKey --authenticated-crypto
```


## Symmetric Encryption

```
java -jar build/libs/s3cse-1.0.jar --crypto-type symmetric --bucket-name bucket1 --key-name test-cse-symmetric \
                                   --region eu-west-1 --key-dir ./keys
```

## Asymmetric Encryption

```
java -jar build/libs/s3cse-1.0.jar --crypto-type asymmetric --bucket-name bucket1 --key-name test-cse-asymmetric \
                                   --region eu-west-1 --key-dir ./keys
```
