package com.attendance.tokenhub.auth;

import com.attendance.tokenhub.config.TokenHubProperties;
import java.time.Clock;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class PortalChallengeService {
    private final PortalGateway gateway;
    private final long challengeTtlSeconds;
    private final long smsRetrySeconds;
    private final Clock clock;
    private final Map<String, PendingChallenge> challenges = new HashMap<>();
    private final Map<String, Instant> lastSmsRequests = new HashMap<>();

    @Autowired
    public PortalChallengeService(PortalGateway gateway, TokenHubProperties properties) {
        this(gateway, properties, Clock.systemUTC());
    }

    PortalChallengeService(PortalGateway gateway, TokenHubProperties properties, Clock clock) {
        this.gateway = gateway;
        this.challengeTtlSeconds = properties.portal().challengeTtlSeconds();
        this.smsRetrySeconds = properties.portal().smsRetrySeconds();
        this.clock = clock;
    }

    public SmsChallenge request(String userAccount, String password) {
        Instant now = clock.instant();
        String accountKey = normalize(userAccount);
        synchronized (this) {
            prune(now);
            Instant lastRequestedAt = lastSmsRequests.get(accountKey);
            if (lastRequestedAt != null) {
                long elapsed = now.getEpochSecond() - lastRequestedAt.getEpochSecond();
                long retryAfter = smsRetrySeconds - elapsed;
                if (retryAfter > 0) {
                    throw new IllegalStateException("请等待 " + retryAfter + " 秒后再重新发送短信验证码");
                }
            }
            lastSmsRequests.put(accountKey, now);
        }

        PortalGateway.SmsTicket ticket;
        try {
            ticket = gateway.requestSmsCode(userAccount, password);
        } catch (RuntimeException exception) {
            synchronized (this) {
                if (now.equals(lastSmsRequests.get(accountKey))) {
                    lastSmsRequests.remove(accountKey);
                }
            }
            throw exception;
        }

        String challengeId = UUID.randomUUID().toString();
        Instant expiresAt = now.plusSeconds(challengeTtlSeconds);
        synchronized (this) {
            prune(now);
            challenges.entrySet().removeIf(entry -> normalize(entry.getValue().userAccount()).equals(accountKey));
            challenges.put(challengeId, new PendingChallenge(userAccount, ticket.privateTicket(), expiresAt));
        }
        return new SmsChallenge(
                challengeId,
                expiresAt,
                challengeTtlSeconds,
                smsRetrySeconds,
                ticket.message());
    }

    public synchronized PendingChallenge require(String challengeId, String userAccount) {
        Instant now = clock.instant();
        prune(now);
        PendingChallenge challenge = challenges.get(challengeId);
        if (challenge == null || !normalize(challenge.userAccount()).equals(normalize(userAccount))) {
            throw new IllegalStateException("短信验证已失效，请重新发送验证码");
        }
        return challenge;
    }

    public synchronized void complete(String challengeId) {
        challenges.remove(challengeId);
    }

    private void prune(Instant now) {
        challenges.entrySet().removeIf(entry -> !entry.getValue().expiresAt().isAfter(now));
        lastSmsRequests.entrySet().removeIf(entry -> entry.getValue().plusSeconds(smsRetrySeconds).isBefore(now));
    }

    private static String normalize(String value) {
        return value == null ? "" : value.strip().toLowerCase();
    }

    public record SmsChallenge(
            String challengeId,
            Instant expiresAt,
            long expiresInSeconds,
            long retryAfterSeconds,
            String message) {}

    public record PendingChallenge(String userAccount, String privateTicket, Instant expiresAt) {}
}
