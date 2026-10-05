package com.attendance.tokenhub.service;

import com.attendance.tokenhub.auth.AttendanceGateway;
import com.attendance.tokenhub.auth.AuthenticatedSession;
import com.attendance.tokenhub.auth.PortalChallengeService;
import com.attendance.tokenhub.auth.PortalGateway;
import org.springframework.stereotype.Service;

@Service
public class MobileAuthService {
    private final PortalChallengeService challenges;
    private final PortalGateway portalGateway;
    private final AttendanceGateway attendanceGateway;
    private final CredentialService credentialService;

    public MobileAuthService(
            PortalChallengeService challenges,
            PortalGateway portalGateway,
            AttendanceGateway attendanceGateway,
            CredentialService credentialService) {
        this.challenges = challenges;
        this.portalGateway = portalGateway;
        this.attendanceGateway = attendanceGateway;
        this.credentialService = credentialService;
    }

    public PortalChallengeService.SmsChallenge requestSmsCode(String userAccount, String password) {
        return challenges.request(userAccount.strip(), password);
    }

    public CredentialService.MobileAccount completeLogin(
            String challengeId,
            String userAccount,
            String password,
            String smsCode,
            boolean savePassword) {
        PortalChallengeService.PendingChallenge challenge = challenges.require(challengeId, userAccount);
        PortalGateway.PortalSession portalSession = portalGateway.login(
                userAccount.strip(),
                password,
                smsCode.strip(),
                challenge.privateTicket());
        PortalGateway.AttendanceAppConfig appConfig = portalGateway.resolveAttendanceAppConfig(portalSession);
        AuthenticatedSession attendanceSession = attendanceGateway.exchangePortalSession(
                portalSession,
                appConfig,
                userAccount.strip());
        CredentialService.MobileAccount saved = credentialService.store(
                attendanceSession,
                password,
                savePassword,
                "portal-sms");
        challenges.complete(challengeId);
        return saved;
    }
}
