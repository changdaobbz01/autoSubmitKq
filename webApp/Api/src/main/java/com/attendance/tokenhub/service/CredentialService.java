package com.attendance.tokenhub.service;

import com.attendance.tokenhub.auth.AuthenticatedSession;
import com.attendance.tokenhub.config.TokenHubProperties;
import com.attendance.tokenhub.crypto.SecretCipher;
import com.attendance.tokenhub.domain.RevisionSequence;
import com.attendance.tokenhub.domain.TokenCredential;
import com.attendance.tokenhub.domain.TokenCredentialRepository;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CredentialService {
    private final TokenCredentialRepository repository;
    private final RevisionSequence revisionSequence;
    private final SecretCipher secretCipher;
    private final long clockSkewSeconds;
    private final Clock clock;

    @Autowired
    public CredentialService(
            TokenCredentialRepository repository,
            RevisionSequence revisionSequence,
            SecretCipher secretCipher,
            TokenHubProperties properties) {
        this(repository, revisionSequence, secretCipher, properties, Clock.systemUTC());
    }

    CredentialService(
            TokenCredentialRepository repository,
            RevisionSequence revisionSequence,
            SecretCipher secretCipher,
            TokenHubProperties properties,
            Clock clock) {
        this.repository = repository;
        this.revisionSequence = revisionSequence;
        this.secretCipher = secretCipher;
        this.clockSkewSeconds = properties.attendance().clockSkewSeconds();
        this.clock = clock;
    }

    @Transactional
    public MobileAccount store(
            AuthenticatedSession session,
            String password,
            boolean savePassword,
            String authMethod) {
        String userAccount = session.userAccount().strip();
        Instant now = clock.instant();
        TokenCredential credential = repository.findById(userAccount)
                .orElseGet(() -> {
                    TokenCredential created = new TokenCredential(userAccount);
                    created.setCreatedAt(now);
                    return created;
                });
        credential.setEncryptedToken(secretCipher.encrypt(session.token(), tokenContext(userAccount)));
        credential.setEncryptedPassword(savePassword
                ? secretCipher.encrypt(password, passwordContext(userAccount))
                : null);
        credential.setTokenExpiresAt(session.tokenExpiresAt());
        credential.setRealName(safe(session.realName()));
        credential.setDepartment(safe(session.department()));
        credential.setAuthMethod(authMethod);
        credential.setRevision(revisionSequence.next());
        credential.setUpdatedAt(now);
        return toMobileAccount(repository.save(credential), now);
    }

    @Transactional(readOnly = true)
    public List<MobileAccount> listMobileAccounts(int limit) {
        Instant now = clock.instant();
        return repository.findAllByOrderByUpdatedAtDesc(PageRequest.of(0, Math.min(Math.max(limit, 1), 200)))
                .stream()
                .map(item -> toMobileAccount(item, now))
                .toList();
    }

    @Transactional(readOnly = true)
    public DesktopSyncPage findChanges(long sinceRevision, int requestedLimit) {
        int limit = Math.min(Math.max(requestedLimit, 1), 500);
        List<TokenCredential> rows = repository.findByRevisionGreaterThanOrderByRevisionAsc(
                Math.max(sinceRevision, 0),
                PageRequest.of(0, limit + 1));
        boolean hasMore = rows.size() > limit;
        List<TokenCredential> selected = hasMore ? rows.subList(0, limit) : rows;
        Instant now = clock.instant();
        List<DesktopTokenItem> items = new ArrayList<>(selected.size());
        for (TokenCredential credential : selected) {
            boolean active = isActive(credential, now);
            items.add(new DesktopTokenItem(
                    credential.getUserAccount(),
                    credential.getRealName(),
                    credential.getDepartment(),
                    active ? "active" : "expired",
                    active
                            ? secretCipher.decrypt(credential.getEncryptedToken(), tokenContext(credential.getUserAccount()))
                            : null,
                    credential.getTokenExpiresAt(),
                    credential.getRevision(),
                    credential.getUpdatedAt()));
        }
        long nextRevision = items.isEmpty()
                ? Math.max(sinceRevision, 0)
                : items.get(items.size() - 1).revision();
        return new DesktopSyncPage(
                Math.max(sinceRevision, 0),
                nextRevision,
                repository.findLatestRevision(),
                hasMore,
                now,
                items);
    }

    private MobileAccount toMobileAccount(TokenCredential credential, Instant now) {
        return new MobileAccount(
                credential.getUserAccount(),
                credential.getRealName(),
                credential.getDepartment(),
                isActive(credential, now) ? "active" : "expired",
                credential.getTokenExpiresAt(),
                credential.getEncryptedPassword() != null,
                credential.getAuthMethod(),
                credential.getRevision(),
                credential.getUpdatedAt());
    }

    private boolean isActive(TokenCredential credential, Instant now) {
        Instant expiresAt = credential.getTokenExpiresAt();
        return expiresAt == null || expiresAt.minusSeconds(clockSkewSeconds).isAfter(now);
    }

    private static String tokenContext(String userAccount) {
        return "token:" + userAccount.toLowerCase();
    }

    private static String passwordContext(String userAccount) {
        return "password:" + userAccount.toLowerCase();
    }

    private static String safe(String value) {
        return value == null ? "" : value.strip();
    }

    public record MobileAccount(
            String userAccount,
            String realName,
            String department,
            String tokenStatus,
            Instant tokenExpiresAt,
            boolean passwordSaved,
            String authMethod,
            long revision,
            Instant updatedAt) {}

    public record DesktopTokenItem(
            String userAccount,
            String realName,
            String department,
            String status,
            String token,
            Instant tokenExpiresAt,
            long revision,
            Instant updatedAt) {}

    public record DesktopSyncPage(
            long sinceRevision,
            long nextRevision,
            long latestRevision,
            boolean hasMore,
            Instant serverTime,
            List<DesktopTokenItem> items) {}
}
