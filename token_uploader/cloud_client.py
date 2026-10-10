from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from attendance_auth_client import SessionData
from network_utils import direct_urlopen


DEFAULT_CLOUD_BASE_URL = os.getenv(
    "ATTENDANCE_TOKEN_CLOUD_URL",
    "https://windwindwind-alicia.cn/attendance-token/",
).strip()


class CloudUploadError(RuntimeError):
    """Raised when the cloud collector cannot validate or store a token."""


class CloudTokenClient:
    def __init__(self, base_url: str = DEFAULT_CLOUD_BASE_URL, *, timeout_seconds: int = 20) -> None:
        self.base_url = self.normalize_base_url(base_url)
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def normalize_base_url(value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise CloudUploadError("请输入云端服务地址")
        parsed = urllib.parse.urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise CloudUploadError("云端服务地址格式无效")
        if parsed.query or parsed.fragment:
            raise CloudUploadError("云端服务地址不能包含查询参数或片段")
        path = parsed.path.rstrip("/") + "/"
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    def validate_access(self, access_key: str) -> dict[str, Any]:
        payload = self._request_json(
            "api/mobile/accounts?limit=1",
            access_key=access_key,
            method="GET",
        )
        if not isinstance(payload, list):
            raise CloudUploadError("云端服务返回格式异常")
        return {"connected": True, "accountCount": len(payload)}

    def upload(self, session: SessionData, access_key: str) -> dict[str, Any]:
        payload = self._request_json(
            "api/mobile/v1/tokens",
            access_key=access_key,
            method="POST",
            body={
                "token": session.token,
                "userAccount": session.user_account,
                "realName": session.real_name,
                "department": session.department,
            },
        )
        if not isinstance(payload, dict) or not payload.get("uploaded"):
            raise CloudUploadError("云端未确认 Token 已保存")
        account = payload.get("account")
        if not isinstance(account, dict):
            raise CloudUploadError("云端保存结果格式异常")
        return account

    def _request_json(
        self,
        path: str,
        *,
        access_key: str,
        method: str,
        body: dict[str, Any] | None = None,
    ) -> Any:
        normalized_key = str(access_key or "").strip()
        if not normalized_key:
            raise CloudUploadError("请输入云端访问口令")

        url = urllib.parse.urljoin(self.base_url, path)
        headers = {
            "Accept": "application/json",
            "X-Mobile-Access-Key": normalized_key,
            "User-Agent": "AttendanceTokenCollector/1.0",
        }
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json;charset=UTF-8"

        request = urllib.request.Request(url=url, data=data, headers=headers, method=method)
        try:
            with direct_urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode(response.headers.get_content_charset() or "utf-8")
        except urllib.error.HTTPError as exception:
            raw = exception.read().decode("utf-8", errors="replace")
            message = self._error_message(raw)
            if exception.code == 401:
                raise CloudUploadError("云端访问口令无效") from exception
            raise CloudUploadError(message or f"云端请求失败（HTTP {exception.code}）") from exception
        except (urllib.error.URLError, TimeoutError, OSError) as exception:
            raise CloudUploadError("无法连接云端服务，请检查网络后重试") from exception

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exception:
            raise CloudUploadError("云端服务未返回有效数据") from exception

    @staticmethod
    def _error_message(raw: str) -> str:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        if not isinstance(payload, dict):
            return ""
        return str(payload.get("error") or payload.get("message") or "").strip()
