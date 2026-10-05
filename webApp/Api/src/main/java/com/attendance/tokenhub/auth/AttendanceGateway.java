package com.attendance.tokenhub.auth;

import com.attendance.tokenhub.config.TokenHubProperties;
import com.attendance.tokenhub.remote.JsonHttpClient;
import com.attendance.tokenhub.remote.RemoteCallException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import java.util.Map;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Component
public class AttendanceGateway {
    private final TokenHubProperties.AttendanceSettings settings;
    private final PortalCrypto crypto;
    private final JsonHttpClient http;
    private final ObjectMapper objectMapper;

    public AttendanceGateway(
            TokenHubProperties properties,
            PortalCrypto crypto,
            JsonHttpClient http,
            ObjectMapper objectMapper) {
        this.settings = properties.attendance();
        this.crypto = crypto;
        this.http = http;
        this.objectMapper = objectMapper;
    }

    public AuthenticatedSession exchangePortalSession(
            PortalGateway.PortalSession portalSession,
            PortalGateway.AttendanceAppConfig appConfig,
            String selectedUserAccount) {
        String encryptedPortalToken = crypto.encryptPortalToken(portalSession.token(), appConfig.publicKey());

        JsonNode tokenPayload = post("/adUser/user/getToken", Map.of("token", encryptedPortalToken));
        String exchangeToken = text(tokenPayload, "retContent");
        requireCode(tokenPayload, "200", !exchangeToken.isBlank(), "门户 token 换票失败");

        JsonNode accountPayload = post("/adUser/user/getWlyyUser", Map.of("token", exchangeToken));
        String loginCredential = extractLoginCredential(accountPayload.get("data"));
        requireCode(accountPayload, "1000", !loginCredential.isBlank(), "无法取得对应的考勤账号");

        JsonNode loginPayload = post(
                "/adUser/user/tologinNewV1ByAccount",
                Map.of(
                        "userAccount", loginCredential,
                        "currentTime", Long.toString(System.currentTimeMillis())));
        JsonNode loginContent = loginPayload.get("retContent");
        String attendanceToken = loginContent != null && loginContent.isObject()
                ? text(loginContent, "token")
                : "";
        requireCode(loginPayload, "200", !attendanceToken.isBlank(), "门户单点登录考勤失败");

        AuthenticatedSession session = getSession(attendanceToken);
        if (session.userAccount().isBlank()) {
            throw new RemoteCallException("门户登录成功，但考勤用户信息缺少账号");
        }
        if (!session.userAccount().equalsIgnoreCase(selectedUserAccount.strip())) {
            throw new RemoteCallException(
                    "门户登录后的考勤账号 " + session.userAccount()
                            + "，与当前输入账号 " + selectedUserAccount + " 不一致");
        }
        return session;
    }

    private AuthenticatedSession getSession(String token) {
        JsonNode userPayload = http.getJson(
                uri("/adUser/user/getUserInfo"),
                Map.of("Access-Token", token));
        JsonNode userInfo = userPayload.get("retContent");
        requireCode(userPayload, "200", userInfo != null && userInfo.isObject(), "获取考勤用户信息失败");

        JsonNode jwt = decodeJwtPayload(token);
        String account = firstText(userInfo, "userAccount", text(jwt, "userAccount"));
        String realName = firstText(userInfo, "realName", firstText(userInfo, "userName", text(jwt, "userName")));
        String department = text(userInfo, "department");
        Instant expiresAt = null;
        JsonNode exp = jwt.get("exp");
        if (exp != null && exp.canConvertToLong()) {
            expiresAt = Instant.ofEpochSecond(exp.asLong());
        }
        return new AuthenticatedSession(token, expiresAt, account, realName, department);
    }

    private JsonNode decodeJwtPayload(String token) {
        String[] parts = token.split("\\.");
        if (parts.length != 3) {
            throw new RemoteCallException("考勤 token 不是合法 JWT");
        }
        try {
            byte[] decoded = Base64.getUrlDecoder().decode(parts[1]);
            return objectMapper.readTree(new String(decoded, StandardCharsets.UTF_8));
        } catch (RuntimeException exception) {
            throw new RemoteCallException("考勤 token 载荷无法解析", exception);
        }
    }

    private JsonNode post(String path, Object body) {
        return http.postJson(uri(path), body, Map.of());
    }

    private URI uri(String path) {
        return URI.create(settings.baseUri().toString() + path);
    }

    private static void requireCode(JsonNode payload, String expected, boolean contentValid, String fallback) {
        String actual = text(payload, expected.equals("1000") ? "code" : "retCode");
        if (!expected.equals(actual) || !contentValid) {
            throw new RemoteCallException(message(payload, fallback));
        }
    }

    private static String extractLoginCredential(JsonNode value) {
        if (value == null || value.isNull()) {
            return "";
        }
        if (value.isTextual()) {
            return value.asText("").strip();
        }
        if (value.isObject()) {
            return firstText(value, "userAccount", text(value, "account"));
        }
        return "";
    }

    private static String message(JsonNode payload, String fallback) {
        return firstText(payload, "message", firstText(payload, "retMsg", firstText(payload, "msg", fallback)));
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
