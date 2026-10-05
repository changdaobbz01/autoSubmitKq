package com.attendance.tokenhub.crypto;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.attendance.tokenhub.config.TokenHubProperties;
import org.junit.jupiter.api.Test;

class SecretCipherTest {
    private final SecretCipher cipher = new SecretCipher(properties());

    @Test
    void encryptsWithRandomIvAndDecryptsWithMatchingContext() {
        String first = cipher.encrypt("敏感-token-value", "token:account-a");
        String second = cipher.encrypt("敏感-token-value", "token:account-a");

        assertThat(first).startsWith("v1:").isNotEqualTo(second);
        assertThat(cipher.decrypt(first, "token:account-a")).isEqualTo("敏感-token-value");
    }

    @Test
    void rejectsCiphertextFromAnotherAccountContext() {
        String encrypted = cipher.encrypt("secret", "token:account-a");

        assertThatThrownBy(() -> cipher.decrypt(encrypted, "token:account-b"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("解密失败");
    }

    private static TokenHubProperties properties() {
        return new TokenHubProperties(
                new TokenHubProperties.SecuritySettings(
                        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
                        "test-mobile-access-key",
                        "test-desktop-api-key"),
                new TokenHubProperties.AttendanceSettings("https://attendance.invalid", 300),
                new TokenHubProperties.PortalSettings(
                        "http://portal.invalid",
                        "湖北",
                        "834786",
                        "33",
                        "TokenHubTest",
                        "3",
                        600,
                        60));
    }
}
