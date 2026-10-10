package com.attendance.tokenhub.service;

import com.attendance.tokenhub.auth.AuthenticatedSession;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.DateTimeException;
import java.time.Instant;
import java.util.Base64;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Service
public class ClientTokenUploadService {
    private static final long MINIMUM_REMAINING_SECONDS = 30;

    private final CredentialService credentialService;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    @Autowired
    public ClientTokenUploadService(CredentialService credentialService, ObjectMapper objectMapper) {
        this(credentialService, objectMapper, Clock.systemUTC());
    }

    ClientTokenUploadService(CredentialService credentialService, ObjectMapper objectMapper, Clock clock) {
        this.credentialService = credentialService;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    public CredentialService.MobileAccount store(
            String token,
            String userAccount,
            String realName,
            String department) {
        String normalizedToken = required(token, "考勤 Token 不能为空");
        String normalizedAccount = required(userAccount, "考勤账号不能为空");
        JsonNode payload = decodePayload(normalizedToken);

        String tokenAccount = firstText(payload, "userAccount", text(payload, "account"));
        if (tokenAccount.isBlank()) {
            throw new IllegalArgumentException("考勤 Token 中缺少账号信息");
        }
        if (!tokenAccount.equalsIgnoreCase(normalizedAccount)) {
            throw new IllegalArgumentException(
                    "Token 中的考勤账号 " + tokenAccount + " 与上传账号 " + normalizedAccount + " 不一致");
        }

        Instant expiresAt = expiry(payload);
        if (!expiresAt.isAfter(clock.instant().plusSeconds(MINIMUM_REMAINING_SECONDS))) {
            throw new IllegalArgumentException("考勤 Token 已过期或即将过期，请重新登录获取");
        }

        String normalizedRealName = safe(realName);
        if (normalizedRealName.isBlank()) {
            normalizedRealName = firstText(payload, "realName", text(payload, "userName"));
        }

        AuthenticatedSession session = new AuthenticatedSession(
                normalizedToken,
                expiresAt,
                normalizedAccount,
                normalizedRealName,
                safe(department));
        return credentialService.store(session, "", false, "desktop-upload");
    }

    private JsonNode decodePayload(String token) {
        String[] parts = token.split("\\.", -1);
        if (parts.length != 3 || parts[1].isBlank()) {
            throw new IllegalArgumentException("考勤 Token 不是合法 JWT");
        }
        try {
            byte[] decoded = Base64.getUrlDecoder().decode(parts[1]);
            JsonNode payload = objectMapper.readTree(new String(decoded, StandardCharsets.UTF_8));
            if (payload == null || !payload.isObject()) {
                throw new IllegalArgumentException("考勤 Token 载荷格式无效");
            }
            return payload;
        } catch (JacksonException | IllegalArgumentException exception) {
            throw new IllegalArgumentException("考勤 Token 载荷无法解析", exception);
        }
    }

    private static Instant expiry(JsonNode payload) {
        JsonNode value = payload.get("exp");
        if (value == null || value.isNull()) {
            throw new IllegalArgumentException("考勤 Token 中缺少有效期");
        }
        try {
            long epochSeconds;
            if (value.isIntegralNumber() && value.canConvertToLong()) {
                epochSeconds = value.asLong();
            } else if (value.isTextual()) {
                epochSeconds = Long.parseLong(value.asText().strip());
            } else {
                throw new NumberFormatException("exp is not an integer");
            }
            return Instant.ofEpochSecond(epochSeconds);
        } catch (DateTimeException | NumberFormatException exception) {
            throw new IllegalArgumentException("考勤 Token 有效期格式无效", exception);
        }
    }

    private static String required(String value, String message) {
        String normalized = safe(value);
        if (normalized.isBlank()) {
            throw new IllegalArgumentException(message);
        }
        return normalized;
    }

    private static String safe(String value) {
        return value == null ? "" : value.strip();
    }

    private static String text(JsonNode node, String field) {
        if (node == null || node.get(field) == null || node.get(field).isNull()) {
            return "";
        }
        return node.get(field).asText("").strip();
    }

    private static String firstText(JsonNode node, String field, String fallback) {
        String value = text(node, field);
        return value.isBlank() ? fallback : value;
    }
}
