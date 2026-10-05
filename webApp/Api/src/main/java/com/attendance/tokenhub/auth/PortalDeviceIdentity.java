package com.attendance.tokenhub.auth;

import com.attendance.tokenhub.domain.ServiceSetting;
import com.attendance.tokenhub.domain.ServiceSettingRepository;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PortalDeviceIdentity {
    private static final String SETTING_KEY = "portal_device_id";

    private final ServiceSettingRepository repository;
    private volatile String cachedDeviceId;

    public PortalDeviceIdentity(ServiceSettingRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public synchronized String getOrCreate() {
        if (cachedDeviceId != null) {
            return cachedDeviceId;
        }
        cachedDeviceId = repository.findById(SETTING_KEY)
                .map(ServiceSetting::getValue)
                .filter(value -> !value.isBlank())
                .orElseGet(() -> {
                    String generated = UUID.randomUUID().toString().replace("-", "").substring(0, 16);
                    repository.save(new ServiceSetting(SETTING_KEY, generated, Instant.now()));
                    return generated;
                });
        return cachedDeviceId;
    }
}
