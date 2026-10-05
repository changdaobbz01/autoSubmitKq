package com.attendance.tokenhub.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "token-hub")
public record TokenHubProperties(
        @Valid SecuritySettings security,
        @Valid AttendanceSettings attendance,
        @Valid PortalSettings portal) {

    public record SecuritySettings(
            @NotBlank String masterKey,
            @NotBlank @Size(min = 16) String mobileAccessKey,
            @NotBlank @Size(min = 16) String desktopApiKey) {}

    public record AttendanceSettings(
            @NotBlank String baseUrl,
            @Min(0) long clockSkewSeconds) {

        public URI baseUri() {
            return URI.create(baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl);
        }
    }

    public record PortalSettings(
            @NotBlank String baseUrl,
            @NotBlank String area,
            @NotBlank String appId,
            @NotBlank String deviceVersion,
            @NotBlank String deviceModel,
            @NotBlank String versionCode,
            @Min(60) long challengeTtlSeconds,
            @Min(10) long smsRetrySeconds) {

        public URI baseUri() {
            return URI.create(baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl);
        }
    }
}
