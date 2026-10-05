package com.attendance.tokenhub.web;

import com.attendance.tokenhub.auth.PortalChallengeService;
import com.attendance.tokenhub.service.CredentialService;
import com.attendance.tokenhub.service.MobileAuthService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/mobile")
public class MobileAuthController {
    private final MobileAuthService authService;
    private final CredentialService credentialService;

    public MobileAuthController(MobileAuthService authService, CredentialService credentialService) {
        this.authService = authService;
        this.credentialService = credentialService;
    }

    @PostMapping("/auth/sms")
    public PortalChallengeService.SmsChallenge requestSms(@Valid @RequestBody SendSmsRequest request) {
        return authService.requestSmsCode(request.userAccount(), request.password());
    }

    @PostMapping("/auth/complete")
    public LoginResponse complete(@Valid @RequestBody CompleteLoginRequest request) {
        CredentialService.MobileAccount account = authService.completeLogin(
                request.challengeId(),
                request.userAccount(),
                request.password(),
                request.smsCode(),
                request.savePassword());
        return new LoginResponse(true, account);
    }

    @GetMapping("/accounts")
    public List<CredentialService.MobileAccount> accounts(
            @RequestParam(defaultValue = "50") int limit) {
        return credentialService.listMobileAccounts(limit);
    }

    public record SendSmsRequest(
            @NotBlank @Size(max = 128) String userAccount,
            @NotBlank @Size(max = 512) String password) {}

    public record CompleteLoginRequest(
            @NotBlank @Size(max = 64) String challengeId,
            @NotBlank @Size(max = 128) String userAccount,
            @NotBlank @Size(max = 512) String password,
            @NotBlank @Size(max = 20) String smsCode,
            boolean savePassword) {}

    public record LoginResponse(boolean loggedIn, CredentialService.MobileAccount account) {}
}
