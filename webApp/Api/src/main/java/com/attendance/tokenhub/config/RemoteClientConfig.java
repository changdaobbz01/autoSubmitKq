package com.attendance.tokenhub.config;

import com.attendance.tokenhub.remote.JsonHttpClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

@Configuration
public class RemoteClientConfig {
    @Bean
    JsonHttpClient jsonHttpClient(ObjectMapper objectMapper) {
        return new JsonHttpClient(objectMapper);
    }
}
