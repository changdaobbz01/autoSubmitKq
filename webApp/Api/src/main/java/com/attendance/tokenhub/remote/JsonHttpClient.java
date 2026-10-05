package com.attendance.tokenhub.remote;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.stream.Collectors;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

public class JsonHttpClient {
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(20);

    private final HttpClient client;
    private final ObjectMapper objectMapper;

    public JsonHttpClient(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(15))
                .followRedirects(HttpClient.Redirect.NORMAL)
                .build();
    }

    public JsonNode getJson(URI uri, Map<String, String> headers) {
        HttpRequest.Builder builder = baseRequest(uri, headers).GET();
        return parseJson(send(builder.build()));
    }

    public JsonNode postJson(URI uri, Object body, Map<String, String> headers) {
        String serialized;
        try {
            serialized = objectMapper.writeValueAsString(body);
        } catch (JacksonException exception) {
            throw new RemoteCallException("请求数据序列化失败", exception);
        }
        HttpRequest.Builder builder = baseRequest(uri, headers)
                .header("Content-Type", "application/json;charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(serialized, StandardCharsets.UTF_8));
        return parseJson(send(builder.build()));
    }

    public String postText(URI uri, String body, Map<String, String> headers) {
        HttpRequest.Builder builder = baseRequest(uri, headers)
                .header("Content-Type", "text/plain; charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8));
        return send(builder.build());
    }

    public JsonNode postForm(URI uri, Map<String, String> form, Map<String, String> headers) {
        String encoded = form.entrySet().stream()
                .map(entry -> formEncode(entry.getKey()) + "=" + formEncode(entry.getValue()))
                .collect(Collectors.joining("&"));
        HttpRequest.Builder builder = baseRequest(uri, headers)
                .header("Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
                .POST(HttpRequest.BodyPublishers.ofString(encoded, StandardCharsets.UTF_8));
        return parseJson(send(builder.build()));
    }

    public JsonNode parseJson(String raw) {
        try {
            return objectMapper.readTree(raw);
        } catch (JacksonException exception) {
            throw new RemoteCallException("远程接口未返回有效 JSON", exception);
        }
    }

    private HttpRequest.Builder baseRequest(URI uri, Map<String, String> headers) {
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
                .timeout(REQUEST_TIMEOUT)
                .header("Accept", "application/json, text/plain, */*")
                .header("User-Agent", "AttendanceTokenHub/1.0");
        headers.forEach(builder::header);
        return builder;
    }

    private String send(HttpRequest request) {
        try {
            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new RemoteCallException("远程接口 HTTP " + response.statusCode());
            }
            return response.body();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new RemoteCallException("远程请求被中断", exception);
        } catch (IOException exception) {
            throw new RemoteCallException("远程网络请求失败", exception);
        }
    }

    private static String formEncode(String value) {
        return java.net.URLEncoder.encode(value, StandardCharsets.UTF_8);
    }
}
