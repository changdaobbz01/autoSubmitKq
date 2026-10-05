package com.attendance.tokenhub.web;

import static org.mockito.Mockito.mock;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.attendance.tokenhub.service.CredentialService;
import com.attendance.tokenhub.service.MobileAuthService;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class ApiExceptionHandlerTest {
    private final MockMvc mockMvc = MockMvcBuilders
            .standaloneSetup(new MobileAuthController(
                    mock(MobileAuthService.class),
                    mock(CredentialService.class)))
            .setControllerAdvice(new ApiExceptionHandler())
            .build();

    @Test
    void malformedCompleteLoginRequestReturnsBadRequest() throws Exception {
        mockMvc.perform(post("/api/mobile/auth/complete")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error").value("请求参数格式无效"));
    }
}
