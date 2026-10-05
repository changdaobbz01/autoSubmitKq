package com.attendance.tokenhub.auth;

import java.time.Instant;

public record AuthenticatedSession(
        String token,
        Instant tokenExpiresAt,
        String userAccount,
        String realName,
        String department) {}
