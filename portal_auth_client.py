from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import padding as symmetric_padding
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding as asymmetric_padding
from cryptography.hazmat.primitives.ciphers import Cipher, modes

try:
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
except ImportError:  # cryptography < 43
    from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES

from attendance_auth_client import AttendanceAuthClient, AuthError, SessionData
from network_utils import direct_urlopen
from runtime_paths import APP_ROOT

PORTAL_API_URL = os.getenv(
    "ATTENDANCE_PORTAL_API_URL",
    "http://111.48.251.187:8003/zsyw/code",
).strip()
PORTAL_AREA = os.getenv("ATTENDANCE_PORTAL_AREA", "湖北").strip()
PORTAL_APP_ID = os.getenv("ATTENDANCE_PORTAL_APP_ID", "834786").strip()
PORTAL_DEVICE_VERSION = os.getenv("ATTENDANCE_PORTAL_DEVICE_VERSION", "33").strip()
PORTAL_DEVICE_MODEL = os.getenv("ATTENDANCE_PORTAL_DEVICE_MODEL", "AttendanceRebuild").strip()
PORTAL_VERSION_CODE = os.getenv("ATTENDANCE_PORTAL_VERSION_CODE", "3").strip()
PORTAL_LOGIN_STRATEGY = "LoginServiceWithLocalImpl"
PORTAL_DEVICE_PATH = APP_ROOT / ".attendance_auth" / "portal_device.json"
PORTAL_CHALLENGE_TTL_SECONDS = 10 * 60
PORTAL_SMS_RETRY_SECONDS = 60

_PORTAL_3DES_KEY = b"YWJj1ZSyw2hpamtsbW5vcHFyc3R1dnd4"[:24]
_PORTAL_3DES_IV = b"25439768"
_DEFAULT_ATTENDANCE_APP_PUBLIC_KEY = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCYLKxkLI2TwnLConEBXUaNbiaDmsOtarZ2RpLDCjqaQQpgjzbd8P9"
    "nd1KPwwO45Ilg1+xvychxeD9z6LJZ18b9roHVCc8HxuLzrbhRQ+80MJXrtKpmRLwoeK6KcL5zPi5/cNmNiGbxM8o8s"
    "ug9Vif+h2Isa2jU2tDuSf3ebf/n1QIDAQAB"
)
ATTENDANCE_APP_PUBLIC_KEY = os.getenv(
    "ATTENDANCE_PORTAL_APP_PUBLIC_KEY",
    _DEFAULT_ATTENDANCE_APP_PUBLIC_KEY,
).strip()


class PortalAuthError(AuthError):
    """Raised when portal login or attendance SSO exchange fails."""


@dataclass(frozen=True)
class PortalSmsTicket:
    tick_token: str
    message: str


@dataclass(frozen=True)
class PortalSession:
    token: str
    ticket: str
    username: str
    user_id: str
    area: str
    user_info: dict[str, Any]


@dataclass(frozen=True)
class PortalAppConfig:
    app_id: str
    public_key: str
    start_url: str


@dataclass(frozen=True)
class _PendingPortalChallenge:
    user_account: str
    tick_token: str
    expires_at: int


class PortalDeviceStore:
    def __init__(self, path: Path = PORTAL_DEVICE_PATH) -> None:
        self.path = path
        self._lock = threading.Lock()

    def get_or_create(self) -> str:
        with self._lock:
            if self.path.exists():
                try:
                    payload = json.loads(self.path.read_text(encoding="utf-8"))
                    device_id = str(payload.get("deviceId") or "").strip()
                    if device_id:
                        return device_id
                except (OSError, json.JSONDecodeError, AttributeError):
                    pass

            device_id = uuid.uuid4().hex[:16]
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(".tmp")
            temp_path.write_text(
                json.dumps({"deviceId": device_id}, ensure_ascii=True, indent=2),
                encoding="utf-8",
            )
            temp_path.replace(self.path)
            return device_id


class PortalAuthClient:
    def __init__(
        self,
        base_api_url: str = PORTAL_API_URL,
        *,
        timeout_seconds: int = 20,
        device_store: PortalDeviceStore | None = None,
    ) -> None:
        self.base_api_url = base_api_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.device_store = device_store or PortalDeviceStore()

    def request_sms_code(self, user_account: str, password: str) -> PortalSmsTicket:
        payload = self._request_encrypted_json(
            "/clientLogin/rest/client/login/verifycode",
            {"username": user_account, "password": password},
        )
        if not self._is_truthy(payload.get("success")):
            raise PortalAuthError(self._message_from(payload, "门户短信验证码发送失败"))

        data = self._as_object(payload.get("data"), "门户短信验证码返回数据异常")
        if str(data.get("code") or "") != "1":
            raise PortalAuthError(self._message_from(data, "门户短信验证码发送失败"))

        tick_token = str(data.get("token") or "").strip()
        if not tick_token:
            raise PortalAuthError("门户短信验证码响应缺少验证票据")
        return PortalSmsTicket(
            tick_token=tick_token,
            message=self._message_from(data, "验证码已发送"),
        )

    def login(
        self,
        user_account: str,
        password: str,
        sms_code: str,
        tick_token: str,
    ) -> PortalSession:
        device_id = self.device_store.get_or_create()
        payload = self._request_encrypted_json(
            "/clientLogin/rest/client/loginwithencrypt",
            {
                "area": PORTAL_AREA,
                "account": user_account,
                "deviceid": device_id,
                "imsi": self._encrypt_text(device_id),
                "deviceVersion": PORTAL_DEVICE_VERSION,
                "deviceModel": PORTAL_DEVICE_MODEL,
                "version": PORTAL_VERSION_CODE,
                "smscode": sms_code,
                "pwd": password,
                "ticktoken": tick_token,
                "loginStrategy": PORTAL_LOGIN_STRATEGY,
            },
        )
        if str(payload.get("code") or "") != "1000":
            raise PortalAuthError(self._message_from(payload, "门户登录失败"))

        data = self._as_object(payload.get("data"), "门户登录返回数据异常")
        token = str(data.get("token") or "").strip()
        if not token:
            raise PortalAuthError("门户登录响应缺少 token")

        raw_user_info = data.get("userinfo") or data.get("userInfo") or {}
        user_info = self._as_object(raw_user_info, "", allow_empty=True)
        return PortalSession(
            token=token,
            ticket=str(data.get("ticket") or ""),
            username=str(data.get("username") or user_account),
            user_id=str(data.get("userId") or ""),
            area=str(data.get("area") or PORTAL_AREA),
            user_info=user_info,
        )

    def exchange_attendance_session(
        self,
        portal_session: PortalSession,
        attendance_client: AttendanceAuthClient,
        *,
        selected_user_account: str,
    ) -> SessionData:
        app_config = self.resolve_attendance_app_config(portal_session)
        encrypted_token = self._encrypt_portal_token(portal_session.token, app_config.public_key)

        token_payload = attendance_client.call_api(
            "/adUser/user/getToken",
            method="POST",
            body={"token": encrypted_token},
        )
        exchange_token = str(token_payload.get("retContent") or "").strip()
        if str(token_payload.get("retCode") or "") != "200" or not exchange_token:
            raise PortalAuthError(self._message_from(token_payload, "门户 token 换票失败"))

        account_payload = attendance_client.call_api(
            "/adUser/user/getWlyyUser",
            method="POST",
            body={"token": exchange_token},
        )
        login_credential = self._extract_attendance_login_credential(account_payload.get("data"))
        if str(account_payload.get("code") or "") != "1000" or not login_credential:
            raise PortalAuthError(self._message_from(account_payload, "无法取得对应的考勤账号"))

        # getWlyyUser returns an opaque, encrypted login credential rather than
        # the plaintext attendance account. The next endpoint resolves it.
        login_payload = attendance_client.call_api(
            "/adUser/user/tologinNewV1ByAccount",
            method="POST",
            body={
                "userAccount": login_credential,
                "currentTime": str(int(time.time() * 1000)),
            },
        )
        content = login_payload.get("retContent")
        attendance_token = str(content.get("token") or "").strip() if isinstance(content, dict) else ""
        if not attendance_token:
            raise PortalAuthError(self._message_from(login_payload, "门户单点登录考勤失败"))

        user_info_payload = attendance_client.get_user_info(attendance_token)
        session = attendance_client.build_session(attendance_token, user_info_payload)
        if not session.user_account:
            raise PortalAuthError(f"门户账号 {selected_user_account} 已登录，但考勤用户信息缺少账号")
        if session.user_account.casefold() != selected_user_account.strip().casefold():
            raise PortalAuthError(
                f"门户登录后的考勤账号 {session.user_account}，"
                f"与当前选择账号 {selected_user_account} 不一致"
            )
        return session

    def resolve_attendance_app_config(self, portal_session: PortalSession) -> PortalAppConfig:
        fallback = PortalAppConfig(
            app_id=PORTAL_APP_ID,
            public_key=ATTENDANCE_APP_PUBLIC_KEY,
            start_url="https://111.48.251.180:20002/ad/#/home",
        )
        try:
            payload = self._request_form_json(
                "/clientApp/rest/client/app/info2",
                {
                    "area": portal_session.area or PORTAL_AREA,
                    "token": portal_session.token,
                    "appID": PORTAL_APP_ID,
                },
                headers={
                    "Authorization": portal_session.token,
                    "token": portal_session.token,
                },
            )
        except PortalAuthError:
            return fallback

        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        normalized = {str(key).casefold(): value for key, value in data.items()}
        public_key = str(normalized.get("publickey") or "").strip()
        start_url = str(normalized.get("startinfo") or "").strip()
        app_id = str(normalized.get("app_id") or normalized.get("appid") or PORTAL_APP_ID).strip()
        if not public_key:
            return fallback
        return PortalAppConfig(
            app_id=app_id,
            public_key=public_key,
            start_url=start_url or fallback.start_url,
        )

    def _request_encrypted_json(self, path: str, body: dict[str, str]) -> dict[str, Any]:
        request = urllib.request.Request(
            url=f"{self.base_api_url}{path}",
            data=self._encrypt_json(body).encode("ascii"),
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "text/plain; charset=UTF-8",
            },
            method="POST",
        )
        raw = self._open_text(request)
        try:
            decrypted = self._decrypt_text(raw)
            payload = json.loads(decrypted)
        except (ValueError, json.JSONDecodeError) as exc:
            raise PortalAuthError("门户接口返回无法解密的数据") from exc
        if not isinstance(payload, dict):
            raise PortalAuthError("门户接口返回格式异常")
        return payload

    def _request_form_json(
        self,
        path: str,
        body: dict[str, str],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        request_headers.update(headers or {})
        request = urllib.request.Request(
            url=f"{self.base_api_url}{path}",
            data=urllib.parse.urlencode(body).encode("utf-8"),
            headers=request_headers,
            method="POST",
        )
        raw = self._open_text(request)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PortalAuthError("门户应用信息接口未返回 JSON") from exc
        if not isinstance(payload, dict):
            raise PortalAuthError("门户应用信息接口返回格式异常")
        return payload

    def _open_text(self, request: urllib.request.Request) -> str:
        try:
            with direct_urlopen(request, timeout=self.timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="strict")
        except urllib.error.HTTPError as exc:
            raise PortalAuthError(f"门户接口 HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, UnicodeError) as exc:
            raise PortalAuthError(f"门户网络请求失败: {exc}") from exc

    @staticmethod
    def _encrypt_portal_token(token: str, public_key_base64: str) -> str:
        try:
            key_der = base64.b64decode(public_key_base64)
            public_key = serialization.load_der_public_key(key_der)
            encrypted = public_key.encrypt(token.encode("utf-8"), asymmetric_padding.PKCS1v15())
            return base64.b64encode(encrypted).decode("ascii")
        except (ValueError, TypeError) as exc:
            raise PortalAuthError("考勤应用单点登录公钥无效") from exc

    @staticmethod
    def _encrypt_bytes(data: bytes) -> bytes:
        padder = symmetric_padding.PKCS7(64).padder()
        padded = padder.update(data) + padder.finalize()
        encryptor = Cipher(TripleDES(_PORTAL_3DES_KEY), modes.CBC(_PORTAL_3DES_IV)).encryptor()
        return encryptor.update(padded) + encryptor.finalize()

    @classmethod
    def _encrypt_text(cls, value: str) -> str:
        return base64.b64encode(cls._encrypt_bytes(value.encode("utf-8"))).decode("ascii")

    @classmethod
    def _encrypt_json(cls, payload: dict[str, str]) -> str:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return base64.b64encode(cls._encrypt_bytes(raw)).decode("ascii")

    @staticmethod
    def _decrypt_text(value: str) -> str:
        ciphertext = base64.b64decode(value.strip())
        decryptor = Cipher(TripleDES(_PORTAL_3DES_KEY), modes.CBC(_PORTAL_3DES_IV)).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = symmetric_padding.PKCS7(64).unpadder()
        return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")

    @staticmethod
    def _as_object(value: Any, error_message: str, *, allow_empty: bool = False) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                if allow_empty:
                    return {}
                raise PortalAuthError(error_message) from exc
            if isinstance(parsed, dict):
                return parsed
        if allow_empty:
            return {}
        raise PortalAuthError(error_message)

    @staticmethod
    def _is_truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"1", "true", "yes"}

    @staticmethod
    def _message_from(payload: dict[str, Any], fallback: str) -> str:
        return str(payload.get("message") or payload.get("retMsg") or payload.get("msg") or fallback)

    @staticmethod
    def _extract_attendance_login_credential(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return str(value.get("userAccount") or value.get("account") or "").strip()
        return ""


class PortalAuthCoordinator:
    def __init__(
        self,
        client: PortalAuthClient | None = None,
        *,
        challenge_ttl_seconds: int = PORTAL_CHALLENGE_TTL_SECONDS,
    ) -> None:
        self.client = client or PortalAuthClient()
        self.challenge_ttl_seconds = challenge_ttl_seconds
        self._challenges: dict[str, _PendingPortalChallenge] = {}
        self._last_sms_requested_at: dict[str, int] = {}
        self._lock = threading.Lock()

    def request_sms_code(self, user_account: str, password: str) -> dict[str, Any]:
        now = int(time.time())
        account_key = user_account.casefold()
        with self._lock:
            self._prune_locked(now)
            last_requested_at = self._last_sms_requested_at.get(account_key, 0)
            retry_after = PORTAL_SMS_RETRY_SECONDS - (now - last_requested_at)
            if retry_after > 0:
                raise PortalAuthError(f"请等待 {retry_after} 秒后再重新发送短信验证码")
            self._last_sms_requested_at[account_key] = now

        try:
            ticket = self.client.request_sms_code(user_account, password)
        except Exception:
            with self._lock:
                if self._last_sms_requested_at.get(account_key) == now:
                    self._last_sms_requested_at.pop(account_key, None)
            raise

        challenge_id = uuid.uuid4().hex
        challenge = _PendingPortalChallenge(
            user_account=user_account,
            tick_token=ticket.tick_token,
            expires_at=now + self.challenge_ttl_seconds,
        )
        with self._lock:
            self._prune_locked(now)
            self._challenges = {
                key: value
                for key, value in self._challenges.items()
                if value.user_account.casefold() != account_key
            }
            self._challenges[challenge_id] = challenge
        return {
            "sent": True,
            "challengeId": challenge_id,
            "expiresAt": challenge.expires_at,
            "expiresInSeconds": self.challenge_ttl_seconds,
            "retryAfterSeconds": PORTAL_SMS_RETRY_SECONDS,
            "message": ticket.message,
        }

    def complete_login(
        self,
        *,
        challenge_id: str,
        user_account: str,
        password: str,
        sms_code: str,
        attendance_client: AttendanceAuthClient,
    ) -> SessionData:
        now = int(time.time())
        with self._lock:
            self._prune_locked(now)
            challenge = self._challenges.get(challenge_id)
        if challenge is None or challenge.user_account.casefold() != user_account.casefold():
            raise PortalAuthError("短信验证已失效，请重新发送验证码")

        portal_session = self.client.login(
            user_account=user_account,
            password=password,
            sms_code=sms_code,
            tick_token=challenge.tick_token,
        )
        session = self.client.exchange_attendance_session(
            portal_session,
            attendance_client,
            selected_user_account=user_account,
        )
        attendance_client.session_store.save(session)
        with self._lock:
            self._challenges.pop(challenge_id, None)
        return session

    def _prune_locked(self, now: int) -> None:
        self._challenges = {
            key: value
            for key, value in self._challenges.items()
            if value.expires_at > now
        }
