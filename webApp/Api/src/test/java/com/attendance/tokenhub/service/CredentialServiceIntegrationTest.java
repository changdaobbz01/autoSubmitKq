package com.attendance.tokenhub.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.attendance.tokenhub.auth.AuthenticatedSession;
import com.attendance.tokenhub.domain.TokenCredential;
import com.attendance.tokenhub.domain.TokenCredentialRepository;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@Transactional
class CredentialServiceIntegrationTest {
    @Autowired
    private CredentialService service;

    @Autowired
    private TokenCredentialRepository repository;

    @Test
    void exposesEachAccountUpdateThroughIncrementalRevisionWithoutReturningPassword() {
        Instant expiresAt = Instant.now().plusSeconds(3600);
        CredentialService.MobileAccount first = service.store(
                new AuthenticatedSession("token-v1", expiresAt, "account01", "测试用户", "运维组"),
                "portal-password",
                true,
                "portal-sms");

        TokenCredential stored = repository.findById("account01").orElseThrow();
        assertThat(stored.getEncryptedToken()).startsWith("v1:").doesNotContain("token-v1");
        assertThat(stored.getEncryptedPassword()).startsWith("v1:").doesNotContain("portal-password");

        CredentialService.DesktopSyncPage initial = service.findChanges(0, 100);
        assertThat(initial.items()).singleElement().satisfies(item -> {
            assertThat(item.userAccount()).isEqualTo("account01");
            assertThat(item.token()).isEqualTo("token-v1");
            assertThat(item.status()).isEqualTo("active");
        });

        CredentialService.MobileAccount updated = service.store(
                new AuthenticatedSession("token-v2", expiresAt, "account01", "测试用户", "运维组"),
                "portal-password",
                false,
                "portal-sms");

        assertThat(updated.revision()).isGreaterThan(first.revision());
        assertThat(updated.passwordSaved()).isFalse();
        assertThat(repository.findById("account01").orElseThrow().getEncryptedPassword()).isNull();

        CredentialService.DesktopSyncPage delta = service.findChanges(first.revision(), 100);
        assertThat(delta.hasMore()).isFalse();
        assertThat(delta.nextRevision()).isEqualTo(updated.revision());
        assertThat(delta.items()).singleElement().satisfies(item -> {
            assertThat(item.userAccount()).isEqualTo("account01");
            assertThat(item.token()).isEqualTo("token-v2");
        });
    }
}
