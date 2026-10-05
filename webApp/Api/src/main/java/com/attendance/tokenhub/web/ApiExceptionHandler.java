package com.attendance.tokenhub.web;

import com.attendance.tokenhub.remote.RemoteCallException;
import java.time.Instant;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    private static final Logger LOGGER = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiError> validation(MethodArgumentNotValidException exception) {
        String message = exception.getBindingResult().getFieldErrors().stream()
                .map(error -> error.getField() + " " + error.getDefaultMessage())
                .distinct()
                .collect(Collectors.joining("；"));
        return ResponseEntity.badRequest().body(new ApiError(message, Instant.now()));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiError> malformedRequest(HttpMessageNotReadableException exception) {
        return ResponseEntity.badRequest().body(new ApiError("请求参数格式无效", Instant.now()));
    }

    @ExceptionHandler({RemoteCallException.class, IllegalArgumentException.class, IllegalStateException.class})
    ResponseEntity<ApiError> badRequest(RuntimeException exception) {
        return ResponseEntity.badRequest().body(new ApiError(exception.getMessage(), Instant.now()));
    }

    @ExceptionHandler(Exception.class)
    ResponseEntity<ApiError> unexpected(Exception exception) {
        LOGGER.error("Unhandled API exception", exception);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ApiError("服务暂时不可用", Instant.now()));
    }

    public record ApiError(String error, Instant timestamp) {}
}
