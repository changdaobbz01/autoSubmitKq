package com.attendance.tokenhub.security;

import com.attendance.tokenhub.config.TokenHubProperties;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class ApiKeyFilter extends OncePerRequestFilter {
    public static final String MOBILE_HEADER = "X-Mobile-Access-Key";
    public static final String DESKTOP_HEADER = "X-Desktop-Key";

    private final byte[] mobileKey;
    private final byte[] desktopKey;

    public ApiKeyFilter(TokenHubProperties properties) {
        this.mobileKey = properties.security().mobileAccessKey().getBytes(StandardCharsets.UTF_8);
        this.desktopKey = properties.security().desktopApiKey().getBytes(StandardCharsets.UTF_8);
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain) throws ServletException, IOException {
        String path = request.getRequestURI();
        if (path.startsWith("/api/mobile/")
                && !matches(request.getHeader(MOBILE_HEADER), mobileKey)) {
            unauthorized(response);
            return;
        }
        if (path.startsWith("/api/desktop/")
                && !matches(request.getHeader(DESKTOP_HEADER), desktopKey)) {
            unauthorized(response);
            return;
        }
        filterChain.doFilter(request, response);
    }

    private static boolean matches(String provided, byte[] expected) {
        if (provided == null) {
            return false;
        }
        return MessageDigest.isEqual(provided.getBytes(StandardCharsets.UTF_8), expected);
    }

    private static void unauthorized(HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.getWriter().write("{\"error\":\"访问密钥无效\"}");
    }
}
