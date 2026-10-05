package com.attendance.tokenhub.auth;

import com.attendance.tokenhub.config.TokenHubProperties;
import com.attendance.tokenhub.remote.JsonHttpClient;
import com.attendance.tokenhub.remote.RemoteCallException;
import java.net.URI;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;

@Component
public class PortalGateway {
    private static final String LOGIN_STRATEGY = "LoginServiceWithLocalImpl";
    private static final String DEFAULT_ATTENDANCE_PUBLIC_KEY =
            "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCYLKxkLI2TwnLConEBXUaNbiaDmsOtarZ2RpLDCjqaQQpgjzbd8P9"
                    + "nd1KPwwO45Ilg1+xvychxeD9z6LJZ18b9roHVCc8HxuLzrbhRQ+80MJXrtKpmRLwoeK6KcL5zPi5/cNmNiGbxM8o8s"
                    + "ug9Vif+h2Isa2jU2tDuSf3ebf/n1QIDAQAB";

    private final TokenHubProperties.PortalSettings settings;
    private final PortalDeviceIdentity deviceIdentity;
    private final PortalCrypto crypto;
    private final JsonHttpClient http;

    public PortalGateway(
            TokenHubProperties properties,
            PortalDeviceIdentity deviceIdentity,
            PortalCrypto crypto,
            JsonHttpClient http) {
        this.settings = properties.portal();
        this.deviceIdentity = deviceIdentity;
        this.crypto = crypto;
        this.http = http;
    }

    public SmsTicket requestSmsCode(String userAccount, String password) {
        JsonNode payload = postEncrypted(
                "/clientLogin/rest/client/login/verifycode",
                Map.of("username", userAccount, "password", password));
        if (!truthy(payload.get("success"))) {
            throw new RemoteCallException(message(payload, "门户短信验证码发送失败"));
        }
        JsonNode data = asObject(payload.get("data"), "门户短信验证码返回数据异常");
        if (!"1".equals(text(data, "code"))) {
            throw new RemoteCallException(message(data, "门户短信验证码发送失败"));
        }
        String ticket = text(data, "token");
        if (ticket.isBlank()) {
            throw new RemoteCallException("门户短信验证码响应缺少验证票据");
        }
        return new SmsTicket(ticket, message(data, "验证码已发送"));
    }

    public PortalSession login(String userAccount, String password, String smsCode, String ticket) {
        String deviceId = deviceIdentity.getOrCreate();
        Map<String, String> body = new LinkedHashMap<>();
        body.put("area", settings.area());
        body.put("account", userAccount);
        body.put("deviceid", deviceId);
        body.put("imsi", crypto.encryptText(deviceId));
        body.put("deviceVersion", settings.deviceVersion());
        body.put("deviceModel", settings.deviceModel());
        body.put("version", settings.versionCode());
        body.put("smscode", smsCode);
        body.put("pwd", password);
        body.put("ticktoken", ticket);
        body.put("loginStrategy", LOGIN_STRATEGY);

        JsonNode payload = postEncrypted("/clientLogin/rest/client/loginwithencrypt", body);
        if (!"1000".equals(text(payload, "code"))) {
            throw new RemoteCallException(message(payload, "门户登录失败"));
        }
        JsonNode data = asObject(payload.get("data"), "门户登录返回数据异常");
        String token = text(data, "token");
        if (token.isBlank()) {
            throw new RemoteCallException("门户登录响应缺少 token");
        }
        return new PortalSession(
                token,
                text(data, "ticket"),
                firstText(data, "username", userAccount),
                text(data, "userId"),
                firstText(data, "area", settings.area()));
    }

    public AttendanceAppConfig resolveAttendanceAppConfig(PortalSession session) {
        AttendanceAppConfig fallback = new AttendanceAppConfig(
                settings.appId(),
                DEFAULT_ATTENDANCE_PUBLIC_KEY,
                "https://111.48.251.180:20002/ad/#/home");
        try {
            JsonNode payload = http.postForm(
                    uri("/clientApp/rest/client/app/info2"),
                    Map.of(
                            "area", session.area(),
                            "token", session.token(),
                            "appID", settings.appId()),
                    Map.of(
                            "Authorization", session.token(),
                            "token", session.token()));
            JsonNode data = payload.get("data") != null && payload.get("data").isObject()
                    ? payload.get("data")
                    : payload;
            String publicKey = firstText(data, "publicKey", text(data, "publickey"));
            if (publicKey.isBlank()) {
                return fallback;
            }
            String appId = firstText(data, "app_id", firstText(data, "appId", firstText(data, "appid", settings.appId())));
            String startUrl = firstText(data, "startInfo", firstText(data, "startinfo", fallback.startUrl()));
            return new AttendanceAppConfig(appId, publicKey, startUrl);
        } catch (RuntimeException ignored) {
            return fallback;
        }
    }

    private JsonNode postEncrypted(String path, Map<String, String> body) {
        String raw = http.postText(uri(path), crypto.encryptJson(body), Map.of());
        return http.parseJson(crypto.decryptText(raw));
    }

    private URI uri(String path) {
        return URI.create(settings.baseUri().toString() + path);
    }

    private JsonNode asObject(JsonNode value, String message) {
        if (value != null && value.isObject()) {
            return value;
        }
        if (value != null && value.isTextual() && !value.asText().isBlank()) {
            JsonNode parsed = http.parseJson(value.asText());
            if (parsed.isObject()) {
                return parsed;
            }
        }
        throw new RemoteCallException(message);
    }

    private static boolean truthy(JsonNode value) {
        if (value == null || value.isNull()) {
            return false;
        }
        if (value.isBoolean()) {
            return value.asBoolean();
        }
        return switch (value.asText("").strip().toLowerCase()) {
            case "1", "true", "yes" -> true;
            default -> false;
        };
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

    public record SmsTicket(String privateTicket, String message) {}
    public record PortalSession(String token, String ticket, String username, String userId, String area) {}
    public record AttendanceAppConfig(String appId, String publicKey, String startUrl) {}
}
