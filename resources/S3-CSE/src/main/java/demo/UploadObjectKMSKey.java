package demo;
import java.io.*;
import java.security.*;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;

import com.amazonaws.AmazonServiceException;
import com.amazonaws.auth.profile.ProfileCredentialsProvider;
import com.amazonaws.regions.RegionUtils;
import com.amazonaws.services.s3.AmazonS3Encryption;
import com.amazonaws.services.s3.AmazonS3EncryptionClientBuilder;
import com.amazonaws.services.s3.model.*;

import org.apache.commons.cli.*;

import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;


public class UploadObjectKMSKey {
    private static void kmsCrypto(String clientRegion, String bucketName, String keyName, String kmsKeyId,
                                  boolean authenticatedCrypto, boolean getOnly, boolean putOnly) {
        System.out.println("KMS Key: " + kmsKeyId);
        System.out.println("Authenticated Encryption: " + authenticatedCrypto);

        try {
            // Create the encryption client.
            KMSEncryptionMaterialsProvider materialProvider = new KMSEncryptionMaterialsProvider(kmsKeyId);

            CryptoConfiguration cryptoConfig;

            if (authenticatedCrypto) {
                // This does AES/GCM/NoPadding
                cryptoConfig = new CryptoConfiguration(CryptoMode.AuthenticatedEncryption).withAwsKmsRegion(RegionUtils.getRegion(clientRegion));
            } else {
                // This does AES/CBC/PKCS5Padding
                cryptoConfig = new CryptoConfiguration().withAwsKmsRegion(RegionUtils.getRegion(clientRegion));
            }

            AmazonS3Encryption encryptionClient = AmazonS3EncryptionClientBuilder.standard()
                    .withCredentials(new ProfileCredentialsProvider())
                    .withEncryptionMaterials(materialProvider)
                    .withCryptoConfiguration(cryptoConfig)
                    .withRegion(clientRegion).build();

            // Upload an object using the encryption client.
            String origContent = "S3 Encrypted Object Using KMS-Managed Customer Master Key.";
            int origContentLength = origContent.length();

            if (putOnly || !getOnly) {
                encryptionClient.putObject(bucketName, keyName, origContent);
            }

            if (getOnly || !putOnly) {
                // Download the object. The downloaded object is still encrypted.
                S3Object downloadedObject = encryptionClient.getObject(bucketName, keyName);
                S3ObjectInputStream input = downloadedObject.getObjectContent();

                // Decrypt and read the object and close the input stream.
                byte[] readBuffer = new byte[4096];
                ByteArrayOutputStream baos = new ByteArrayOutputStream(4096);
                int bytesRead = 0;
                int decryptedContentLength = 0;

                while ((bytesRead = input.read(readBuffer)) != -1) {
                    baos.write(readBuffer, 0, bytesRead);
                    decryptedContentLength += bytesRead;
                }
                input.close();

                // Verify that the original and decrypted contents are the same size.

                System.out.println("Decrypted content length: " + decryptedContentLength);
            }
            System.out.println("Original content length: " + origContentLength);
        }
        catch(AmazonServiceException e) {
            // The call was transmitted successfully, but Amazon S3 couldn't process
            // it, so it returned an error response.
            e.printStackTrace();
        }
        catch(IOException e) {
            // The call was transmitted successfully, but Amazon S3 couldn't process
            // it, so it returned an error response.
            e.printStackTrace();
        }

    }

    private static void symmetricCrypto(String clientRegion, String bucketName, String keyName,
                                        String masterKeyDir, boolean getOnly, boolean putOnly) throws Exception {
        String masterKeyName = "secret.key";

        System.out.println("symmetric Encryption");

        KeyGenerator symKeyGenerator = KeyGenerator.getInstance("AES");
        symKeyGenerator.init(256);
        SecretKey symKey = symKeyGenerator.generateKey();

        // Only saves if key doesnt already exist
        saveSymmetricKey(masterKeyDir, masterKeyName, symKey);
        symKey = loadSymmetricAESKey(masterKeyDir, masterKeyName, "AES");

        try {
            EncryptionMaterials encryptionMaterials = new EncryptionMaterials(symKey);
            AmazonS3Encryption encryptionClient = AmazonS3EncryptionClientBuilder.standard()
                    .withCredentials(new ProfileCredentialsProvider())
                    .withEncryptionMaterials(new StaticEncryptionMaterialsProvider(encryptionMaterials))
                    .withRegion(clientRegion)
                    .build();

            // Upload an object using the encryption client.
            String origContent = "S3 Encrypted Object Using symmetric.";
            int origContentLength = origContent.length();
            if (putOnly || !getOnly) {
                encryptionClient.putObject(bucketName, keyName, origContent);
            }

            // Download the object. The downloaded object is still encrypted.
            if (getOnly || !putOnly) {
                S3Object downloadedObject = encryptionClient.getObject(bucketName, keyName);
                S3ObjectInputStream input = downloadedObject.getObjectContent();

                // Decrypt and read the object and close the input stream.
                byte[] readBuffer = new byte[4096];
                ByteArrayOutputStream baos = new ByteArrayOutputStream(4096);
                int bytesRead = 0;
                int decryptedContentLength = 0;

                while ((bytesRead = input.read(readBuffer)) != -1) {
                    baos.write(readBuffer, 0, bytesRead);
                    decryptedContentLength += bytesRead;
                }
                input.close();

                // Verify that the original and decrypted contents are the same size.

                System.out.println("Decrypted content length: " + decryptedContentLength);
            }
            System.out.println("Original content length: " + origContentLength);
        }
        catch(AmazonServiceException e) {
            // The call was transmitted successfully, but Amazon S3 couldn't process
            // it, so it returned an error response.
            e.printStackTrace();
        }
        catch(IOException e) {
            // The call was transmitted successfully, but Amazon S3 couldn't process
            // it, so it returned an error response.
            e.printStackTrace();
        }

    }

    private static void asymmetricCrypto(String clientRegion, String bucketName, String keyName,
                                         String masterKeyDir, boolean getOnly, boolean putOnly) throws Exception {
        String pubKeyName = "secret.pub";
        String privKeyName = "secret.priv";

        System.out.println("asymmetric Encryption");

        KeyPairGenerator keyGenerator = KeyPairGenerator.getInstance("RSA");
        keyGenerator.initialize(1024, new SecureRandom());
        KeyPair origKeyPair = keyGenerator.generateKeyPair();

        // To see how it works, save and load the key pair to and from the file system.
        saveKeyPair(masterKeyDir, pubKeyName, privKeyName, origKeyPair);
        KeyPair keyPair = loadKeyPair(masterKeyDir, pubKeyName, privKeyName, "RSA");

        try {
            EncryptionMaterials encryptionMaterials = new EncryptionMaterials(keyPair);
            AmazonS3Encryption encryptionClient = AmazonS3EncryptionClientBuilder.standard()
                    .withCredentials(new ProfileCredentialsProvider())
                    .withEncryptionMaterials(new StaticEncryptionMaterialsProvider(encryptionMaterials))
                    .withRegion(clientRegion)
                    .build();

            // Upload an object using the encryption client.
            String origContent = "S3 Encrypted Object Using asymmetric encryption.";
            int origContentLength = origContent.length();
            if (putOnly || !getOnly) {
                encryptionClient.putObject(bucketName, keyName, origContent);
            }
            // Download the object. The downloaded object is still encrypted.

            if (getOnly || !putOnly) {
                S3Object downloadedObject = encryptionClient.getObject(bucketName, keyName);
                S3ObjectInputStream input = downloadedObject.getObjectContent();

                // Decrypt and read the object and close the input stream.
                byte[] readBuffer = new byte[4096];
                ByteArrayOutputStream baos = new ByteArrayOutputStream(4096);
                int bytesRead = 0;
                int decryptedContentLength = 0;

                while ((bytesRead = input.read(readBuffer)) != -1) {
                    baos.write(readBuffer, 0, bytesRead);
                    decryptedContentLength += bytesRead;
                }
                input.close();

                // Verify that the original and decrypted contents are the same size.

                System.out.println("Decrypted content length: " + decryptedContentLength);
            }
            System.out.println("Original content length: " + origContentLength);
        }
        catch(AmazonServiceException e) {
            // The call was transmitted successfully, but Amazon S3 couldn't process
            // it, so it returned an error response.
            e.printStackTrace();
        }
        catch(IOException e) {
            // The call was transmitted successfully, but Amazon S3 couldn't process
            // it, so it returned an error response.
            e.printStackTrace();
        }

    }

    private static void saveSymmetricKey(String masterKeyDir, String masterKeyName, SecretKey secretKey) throws IOException {
        File outputFile = new File(masterKeyDir + File.separator + masterKeyName);

        if (!outputFile.exists()) {
            X509EncodedKeySpec x509EncodedKeySpec = new X509EncodedKeySpec(secretKey.getEncoded());
            FileOutputStream keyOutputStream = new FileOutputStream(masterKeyDir + File.separator + masterKeyName);
            keyOutputStream.write(x509EncodedKeySpec.getEncoded());
            keyOutputStream.close();
        }
    }

    private static SecretKey loadSymmetricAESKey(String masterKeyDir, String masterKeyName, String algorithm)
            throws IOException, NoSuchAlgorithmException, InvalidKeySpecException, InvalidKeyException {
        // Read the key from the specified file.
        File keyFile = new File(masterKeyDir + File.separator + masterKeyName);
        FileInputStream keyInputStream = new FileInputStream(keyFile);
        byte[] encodedPrivateKey = new byte[(int) keyFile.length()];
        keyInputStream.read(encodedPrivateKey);
        keyInputStream.close();

        // Reconstruct and return the master key.
        return new SecretKeySpec(encodedPrivateKey, "AES");
    }


    private static void saveKeyPair(String dir,
                                    String publicKeyName,
                                    String privateKeyName,
                                    KeyPair keyPair) throws IOException {
        File outputFile = new File(dir + File.separator + publicKeyName);

        if (!outputFile.exists()) {
            PrivateKey privateKey = keyPair.getPrivate();
            PublicKey publicKey = keyPair.getPublic();

            // Write the public key to the specified file.
            X509EncodedKeySpec x509EncodedKeySpec = new X509EncodedKeySpec(publicKey.getEncoded());
            FileOutputStream publicKeyOutputStream = new FileOutputStream(dir + File.separator + publicKeyName);
            publicKeyOutputStream.write(x509EncodedKeySpec.getEncoded());
            publicKeyOutputStream.close();

            // Write the private key to the specified file.
            PKCS8EncodedKeySpec pkcs8EncodedKeySpec = new PKCS8EncodedKeySpec(privateKey.getEncoded());
            FileOutputStream privateKeyOutputStream = new FileOutputStream(dir + File.separator + privateKeyName);
            privateKeyOutputStream.write(pkcs8EncodedKeySpec.getEncoded());
            privateKeyOutputStream.close();
        }
    }

    private static KeyPair loadKeyPair(String dir,
                                       String publicKeyName,
                                       String privateKeyName,
                                       String algorithm)
            throws IOException, NoSuchAlgorithmException, InvalidKeySpecException {
        // Read the public key from the specified file.
        File publicKeyFile = new File(dir + File.separator + publicKeyName);
        FileInputStream publicKeyInputStream = new FileInputStream(publicKeyFile);
        byte[] encodedPublicKey = new byte[(int) publicKeyFile.length()];
        publicKeyInputStream.read(encodedPublicKey);
        publicKeyInputStream.close();

        // Read the private key from the specified file.
        File privateKeyFile = new File(dir + File.separator + privateKeyName);
        FileInputStream privateKeyInputStream = new FileInputStream(privateKeyFile);
        byte[] encodedPrivateKey = new byte[(int) privateKeyFile.length()];
        privateKeyInputStream.read(encodedPrivateKey);
        privateKeyInputStream.close();

        // Convert the keys into a key pair.
        KeyFactory keyFactory = KeyFactory.getInstance(algorithm);
        X509EncodedKeySpec publicKeySpec = new X509EncodedKeySpec(encodedPublicKey);
        PublicKey publicKey = keyFactory.generatePublic(publicKeySpec);

        PKCS8EncodedKeySpec privateKeySpec = new PKCS8EncodedKeySpec(encodedPrivateKey);
        PrivateKey privateKey = keyFactory.generatePrivate(privateKeySpec);

        return new KeyPair(publicKey, privateKey);
    }


    public static void main(String[] args) throws IOException {
        Options options = new Options();
        Option bucketNameInput = new Option("b", "bucket-name", true, "S3 Bucket to use");
        bucketNameInput.setRequired(true);
        options.addOption(bucketNameInput);

        Option keyNameInput = new Option("k", "key-name", true, "S3 File name to use");
        keyNameInput.setRequired(true);
        options.addOption(keyNameInput);

        Option regionInput = new Option("r", "region", true, "AWS Region");
        regionInput.setRequired(true);
        options.addOption(regionInput);

        Option cryptoTypeInput = new Option("c", "crypto-type", true, "Which crypto type to use");
        cryptoTypeInput.setRequired(true);
        options.addOption(cryptoTypeInput);

        Option kmsKeyIdInput = new Option("a", "kms-key-id", true, "KMS Key ID or alias");
        options.addOption(kmsKeyIdInput);

        Option authenticatedCryptoInput = new Option("d", "authenticated-crypto", false, "Authenticated crypto");
        options.addOption(authenticatedCryptoInput);

        Option keyDirInput = new Option("e", "key-dir", true, "Symmetric or Asymmetric key directory");
        options.addOption(keyDirInput);

        Option putOnlyInput = new Option("p", "put-only", false, "Upload only");
        options.addOption(putOnlyInput);

        Option getOnlyInput = new Option("g", "get-only", false, "Download only");
        options.addOption(getOnlyInput);

        CommandLineParser parser = new DefaultParser();
        HelpFormatter formatter = new HelpFormatter();
        CommandLine cmd = null;

        try {
            cmd = parser.parse(options, args);
        } catch (ParseException e) {
            System.out.println(e.getMessage());
            formatter.printHelp("s3_cse_example", options);

            System.exit(1);
        }

        String bucketName = cmd.getOptionValue("bucket-name");
        String keyName = cmd.getOptionValue("key-name");
        String clientRegion = cmd.getOptionValue("region");
        String cryptoType = cmd.getOptionValue("crypto-type");
        boolean getOnly = cmd.hasOption("get-only");
        boolean putOnly = cmd.hasOption("put-only");

        System.out.println("S3: s3://" + bucketName + "/" + keyName);
        System.out.println("Region: " + clientRegion);

        try {
            switch (cryptoType) {
                case "kms":
                    String kmsKeyId = cmd.getOptionValue("kms-key-id");
                    boolean authenticatedCrypto = cmd.hasOption("authenticated-crypto");

                    UploadObjectKMSKey.kmsCrypto(clientRegion, bucketName, keyName, kmsKeyId, authenticatedCrypto, getOnly, putOnly);
                    break;
                case "asymmetric":
                    String keyDir = cmd.getOptionValue("key-dir");

                    UploadObjectKMSKey.asymmetricCrypto(clientRegion, bucketName, keyName, keyDir, getOnly, putOnly);
                    break;
                case "symmetric":
                    keyDir = cmd.getOptionValue("key-dir");

                    UploadObjectKMSKey.symmetricCrypto(clientRegion, bucketName, keyName, keyDir, getOnly, putOnly);
                    break;

                default:
                    System.out.println("Crypto type " + cryptoType + " unsupported");
            }
        } catch (Exception e) {
            e.printStackTrace();
        }


    }
}
