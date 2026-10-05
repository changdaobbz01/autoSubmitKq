package com.attendance.tokenhub.crypto;

import com.attendance.tokenhub.config.TokenHubProperties;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;

@Component
public class SecretCipher {
    private static final String PREFIX = "v1:";
    private static final int IV_LENGTH = 12;
    private static final int TAG_LENGTH_BITS = 128;

    private final SecretKeySpec key;
    private final SecureRandom secureRandom = new SecureRandom();

    public SecretCipher(TokenHubProperties properties) {
        byte[] decoded;
        try {
            decoded = Base64.getDecoder().decode(properties.security().masterKey());
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException("TOKEN_MASTER_KEY 必须是 Base64 编码的 32 字节密钥", exception);
        }
        if (decoded.length != 32) {
            throw new IllegalStateException("TOKEN_MASTER_KEY 解码后必须正好为 32 字节");
        }
        this.key = new SecretKeySpec(decoded, "AES");
    }

    public String encrypt(String plaintext, String context) {
        if (plaintext == null || plaintext.isBlank()) {
            throw new IllegalArgumentException("待加密内容不能为空");
        }
        byte[] iv = new byte[IV_LENGTH];
        secureRandom.nextBytes(iv);
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_LENGTH_BITS, iv));
            cipher.updateAAD(context.getBytes(StandardCharsets.UTF_8));
            byte[] encrypted = cipher.doFinal(plaintext.getBytes(StandardCharsets.UTF_8));
            byte[] payload = ByteBuffer.allocate(iv.length + encrypted.length)
                    .put(iv)
                    .put(encrypted)
                    .array();
            return PREFIX + Base64.getEncoder().encodeToString(payload);
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("敏感信息加密失败", exception);
        }
    }

    public String decrypt(String ciphertext, String context) {
        if (ciphertext == null || !ciphertext.startsWith(PREFIX)) {
            throw new IllegalStateException("不支持的密文格式");
        }
        byte[] payload;
        try {
            payload = Base64.getDecoder().decode(ciphertext.substring(PREFIX.length()));
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException("密文 Base64 格式无效", exception);
        }
        if (payload.length <= IV_LENGTH) {
            throw new IllegalStateException("密文长度无效");
        }
        byte[] iv = new byte[IV_LENGTH];
        byte[] encrypted = new byte[payload.length - IV_LENGTH];
        System.arraycopy(payload, 0, iv, 0, iv.length);
        System.arraycopy(payload, iv.length, encrypted, 0, encrypted.length);
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_LENGTH_BITS, iv));
            cipher.updateAAD(context.getBytes(StandardCharsets.UTF_8));
            return new String(cipher.doFinal(encrypted), StandardCharsets.UTF_8);
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("敏感信息解密失败，请检查主密钥是否正确", exception);
        }
    }
}
