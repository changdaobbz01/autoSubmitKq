package com.attendance.tokenhub.web;

import com.attendance.tokenhub.service.CredentialService;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@Validated
@RestController
@RequestMapping("/api/desktop/v1/tokens")
public class DesktopTokenController {
    private final CredentialService credentialService;

    public DesktopTokenController(CredentialService credentialService) {
        this.credentialService = credentialService;
    }

    @GetMapping
    public CredentialService.DesktopSyncPage changes(
            @RequestParam(defaultValue = "0") @Min(0) long since,
            @RequestParam(defaultValue = "100") @Min(1) @Max(500) int limit) {
        return credentialService.findChanges(since, limit);
    }
}
