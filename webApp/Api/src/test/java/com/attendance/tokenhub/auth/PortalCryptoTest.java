package com.attendance.tokenhub.auth;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class PortalCryptoTest {
    private final PortalCrypto crypto = new PortalCrypto(new ObjectMapper());

    @Test
    void roundTripsUtf8PortalPayload() {
        String payload = "{\"area\":\"湖北\",\"account\":\"测试账号\"}";

        String encrypted = crypto.encryptText(payload);

        assertThat(encrypted).doesNotContain("湖北");
        assertThat(crypto.decryptText(encrypted)).isEqualTo(payload);
    }
}
