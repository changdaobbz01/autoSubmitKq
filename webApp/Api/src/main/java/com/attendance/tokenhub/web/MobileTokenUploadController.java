package com.attendance.tokenhub.web;

import com.attendance.tokenhub.service.ClientTokenUploadService;
import com.attendance.tokenhub.service.CredentialService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/mobile/v1/tokens")
public class MobileTokenUploadController {
    private final ClientTokenUploadService uploadService;

    public MobileTokenUploadController(ClientTokenUploadService uploadService) {
        this.uploadService = uploadService;
    }

    @PostMapping
    public UploadResponse upload(@Valid @RequestBody UploadRequest request) {
        CredentialService.MobileAccount account = uploadService.store(
                request.token(),
                request.userAccount(),
                request.realName(),
                request.department());
        return new UploadResponse(true, account);
    }

    public record UploadRequest(
            @NotBlank @Size(max = 8192) String token,
            @NotBlank @Size(max = 128) String userAccount,
            @Size(max = 200) String realName,
            @Size(max = 300) String department) {}

    public record UploadResponse(boolean uploaded, CredentialService.MobileAccount account) {}
}
