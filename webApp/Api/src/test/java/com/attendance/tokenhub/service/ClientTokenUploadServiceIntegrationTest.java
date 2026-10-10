package com.attendance.tokenhub.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class ClientTokenUploadServiceIntegrationTest {
    @Autowired
    private ClientTokenUploadService uploadService;

    @Autowired
    private CredentialService credentialService;

    @Test
    void storesDeviceTokenForDesktopSyncWithoutPassword() {
        String token = token("account01", Instant.now().plusSeconds(3600).getEpochSecond());

        CredentialService.MobileAccount saved = uploadService.store(
                token,
                "account01",
                "测试用户",
                "运维组");

        assertThat(saved.userAccount()).isEqualTo("account01");
        assertThat(saved.authMethod()).isEqualTo("desktop-upload");
        assertThat(saved.passwordSaved()).isFalse();
        assertThat(credentialService.findChanges(0, 100).items())
                .singleElement()
                .satisfies(item -> assertThat(item.token()).isEqualTo(token));
    }

    @Test
    void rejectsAccountMismatchAndExpiredToken() {
        assertThatThrownBy(() -> uploadService.store(
                        token("another-account", Instant.now().plusSeconds(3600).getEpochSecond()),
                        "account01",
                        "",
                        ""))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("不一致");

        assertThatThrownBy(() -> uploadService.store(
                        token("account01", Instant.now().minusSeconds(1).getEpochSecond()),
                        "account01",
                        "",
                        ""))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("已过期");
    }

    @Test
    void rejectsTokenWithoutAccountOrExpiryClaims() {
        assertThatThrownBy(() -> uploadService.store(
                        tokenPayload("{\"exp\":" + Instant.now().plusSeconds(3600).getEpochSecond() + "}"),
                        "account01",
                        "",
                        ""))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("缺少账号");

        assertThatThrownBy(() -> uploadService.store(
                        tokenPayload("{\"userAccount\":\"account01\"}"),
                        "account01",
                        "",
                        ""))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("缺少有效期");
    }

    private static String token(String account, long expiresAt) {
        return tokenPayload("{\"userAccount\":\"" + account + "\",\"exp\":" + expiresAt + "}");
    }

    private static String tokenPayload(String payload) {
        String header = encode("{\"alg\":\"none\",\"typ\":\"JWT\"}");
        return header + "." + encode(payload) + ".test-signature";
    }

    private static String encode(String value) {
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(value.getBytes(StandardCharsets.UTF_8));
    }
}
