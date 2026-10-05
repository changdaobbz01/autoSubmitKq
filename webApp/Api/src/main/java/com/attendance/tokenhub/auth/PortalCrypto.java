package com.attendance.tokenhub.auth;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import java.util.Base64;
import java.util.Map;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

@Component
public class PortalCrypto {
    private static final byte[] KEY = Arrays.copyOf(
            "YWJj1ZSyw2hpamtsbW5vcHFyc3R1dnd4".getBytes(StandardCharsets.UTF_8),
            24);
    private static final byte[] IV = "25439768".getBytes(StandardCharsets.UTF_8);

    private final ObjectMapper objectMapper;

    public PortalCrypto(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public String encryptJson(Map<String, String> payload) {
        try {
            return encryptText(objectMapper.writeValueAsString(payload));
        } catch (JacksonException exception) {
            throw new IllegalStateException("门户请求序列化失败", exception);
        }
    }

    public String encryptText(String value) {
        try {
            Cipher cipher = Cipher.getInstance("DESede/CBC/PKCS5Padding");
            cipher.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(KEY, "DESede"), new IvParameterSpec(IV));
            return Base64.getEncoder().encodeToString(cipher.doFinal(value.getBytes(StandardCharsets.UTF_8)));
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("门户数据加密失败", exception);
        }
    }

    public String decryptText(String value) {
        try {
            Cipher cipher = Cipher.getInstance("DESede/CBC/PKCS5Padding");
            cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(KEY, "DESede"), new IvParameterSpec(IV));
            byte[] decrypted = cipher.doFinal(Base64.getDecoder().decode(value.strip()));
            return new String(decrypted, StandardCharsets.UTF_8);
        } catch (GeneralSecurityException | IllegalArgumentException exception) {
            throw new IllegalStateException("门户响应解密失败", exception);
        }
    }

    public String encryptPortalToken(String token, String publicKeyBase64) {
        try {
            byte[] encoded = Base64.getDecoder().decode(publicKeyBase64);
            PublicKey publicKey = KeyFactory.getInstance("RSA").generatePublic(new X509EncodedKeySpec(encoded));
            Cipher cipher = Cipher.getInstance("RSA/ECB/PKCS1Padding");
            cipher.init(Cipher.ENCRYPT_MODE, publicKey);
            return Base64.getEncoder().encodeToString(cipher.doFinal(token.getBytes(StandardCharsets.UTF_8)));
        } catch (GeneralSecurityException | IllegalArgumentException exception) {
            throw new IllegalStateException("考勤应用单点登录公钥无效", exception);
        }
    }
}
