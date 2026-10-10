from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from attendance_auth_client import AttendanceAuthClient, AuthError, SessionData
from portal_auth_client import (
    PORTAL_CHALLENGE_TTL_SECONDS,
    PORTAL_SMS_RETRY_SECONDS,
    PortalAuthClient,
    PortalAuthError,
)
from token_uploader import __version__
from token_uploader.cloud_client import CloudTokenClient, CloudUploadError, DEFAULT_CLOUD_BASE_URL


LOGGER = logging.getLogger(__name__)


@dataclass
class _Challenge:
    challenge_id: str
    user_account: str
    tick_token: str
    cloud_base_url: str
    expires_at: int
    pending_session: SessionData | None = None


class TokenCollectorBridge:
    def __init__(
        self,
        portal_client: PortalAuthClient | None = None,
        attendance_client: AttendanceAuthClient | None = None,
        cloud_client_factory: Callable[[str], CloudTokenClient] = CloudTokenClient,
    ) -> None:
        self.portal_client = portal_client or PortalAuthClient()
        self.attendance_client = attendance_client or AttendanceAuthClient()
        self.cloud_client_factory = cloud_client_factory
        self._challenge: _Challenge | None = None
        self._last_sms_at: dict[str, int] = {}
        self._state_lock = threading.Lock()
        self._operation_lock = threading.Lock()

    def get_defaults(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._ok(
            version=__version__,
            cloudBaseUrl=DEFAULT_CLOUD_BASE_URL,
            challengeTtlSeconds=PORTAL_CHALLENGE_TTL_SECONDS,
            smsRetrySeconds=PORTAL_SMS_RETRY_SECONDS,
        )

    def validate_cloud(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        return self._run(self._validate_cloud, payload or {})

    def request_sms(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        return self._run(self._request_sms, payload or {})

    def complete_login(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        return self._run(self._complete_login, payload or {})

    def cancel_challenge(self, _payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._state_lock:
            self._challenge = None
        return self._ok()

    def _validate_cloud(self, payload: dict[str, Any]) -> dict[str, Any]:
        client, access_key = self._cloud(payload)
        result = client.validate_access(access_key)
        return self._ok(cloudBaseUrl=client.base_url, **result)

    def _request_sms(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_account = self._required(payload, "userAccount", "请输入门户账号", 128)
        password = self._required(payload, "password", "请输入门户密码", 512)
        cloud_client, access_key = self._cloud(payload)
        cloud_client.validate_access(access_key)

        now = int(time.time())
        account_key = user_account.casefold()
        with self._state_lock:
            retry_after = PORTAL_SMS_RETRY_SECONDS - (now - self._last_sms_at.get(account_key, 0))
            if retry_after > 0:
                raise ValueError(f"请等待 {retry_after} 秒后再重新发送短信验证码")
            self._last_sms_at[account_key] = now

        try:
            ticket = self.portal_client.request_sms_code(user_account, password)
        except Exception:
            with self._state_lock:
                if self._last_sms_at.get(account_key) == now:
                    self._last_sms_at.pop(account_key, None)
            raise

        challenge = _Challenge(
            challenge_id=uuid.uuid4().hex,
            user_account=user_account,
            tick_token=ticket.tick_token,
            cloud_base_url=cloud_client.base_url,
            expires_at=now + PORTAL_CHALLENGE_TTL_SECONDS,
        )
        with self._state_lock:
            self._challenge = challenge
        return self._ok(
            sent=True,
            challengeId=challenge.challenge_id,
            expiresAt=challenge.expires_at,
            expiresInSeconds=PORTAL_CHALLENGE_TTL_SECONDS,
            retryAfterSeconds=PORTAL_SMS_RETRY_SECONDS,
            message=ticket.message,
        )

    def _complete_login(self, payload: dict[str, Any]) -> dict[str, Any]:
        challenge_id = self._required(payload, "challengeId", "请先发送短信验证码", 64)
        user_account = self._required(payload, "userAccount", "请输入门户账号", 128)
        password = self._required(payload, "password", "请输入门户密码", 512)
        sms_code = self._required(payload, "smsCode", "请输入短信验证码", 20)
        cloud_client, access_key = self._cloud(payload)

        with self._state_lock:
            challenge = self._challenge
        now = int(time.time())
        if challenge is None or challenge.challenge_id != challenge_id:
            raise ValueError("短信验证已失效，请重新发送验证码")
        if challenge.expires_at <= now:
            self.cancel_challenge()
            raise ValueError("短信验证码已超时，请重新发送")
        if challenge.user_account.casefold() != user_account.casefold():
            raise ValueError("门户账号已修改，请重新发送短信验证码")
        if challenge.cloud_base_url != cloud_client.base_url:
            raise ValueError("云端服务地址已修改，请重新发送短信验证码")

        session = challenge.pending_session
        if session is None:
            portal_session = self.portal_client.login(
                user_account=user_account,
                password=password,
                sms_code=sms_code,
                tick_token=challenge.tick_token,
            )
            session = self.portal_client.exchange_attendance_session(
                portal_session,
                self.attendance_client,
                selected_user_account=user_account,
            )
            with self._state_lock:
                if self._challenge is challenge:
                    challenge.pending_session = session

        try:
            account = cloud_client.upload(session, access_key)
        except CloudUploadError as exception:
            return self._error(
                f"Token 已在本机获取，但上传失败：{exception}",
                retryableUpload=True,
            )

        self.cancel_challenge()
        return self._ok(
            uploaded=True,
            message=f"{session.user_account} 的 Token 已上传云端",
            account=account,
        )

    def _cloud(self, payload: dict[str, Any]) -> tuple[CloudTokenClient, str]:
        base_url = self._required(payload, "cloudBaseUrl", "请输入云端服务地址", 512)
        access_key = self._required(payload, "accessKey", "请输入云端访问口令", 512)
        return self.cloud_client_factory(base_url), access_key

    def _run(self, operation: Callable[[dict[str, Any]], dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
        if not self._operation_lock.acquire(blocking=False):
            return self._error("当前操作尚未完成，请稍候")
        try:
            return operation(payload)
        except (PortalAuthError, AuthError, CloudUploadError, ValueError) as exception:
            return self._error(str(exception))
        except Exception:
            LOGGER.exception("Unexpected token collector failure")
            return self._error("操作失败，请查看程序日志或联系管理员")
        finally:
            self._operation_lock.release()

    @staticmethod
    def _required(payload: dict[str, Any], key: str, message: str, max_length: int) -> str:
        value = str(payload.get(key) or "").strip()
        if not value:
            raise ValueError(message)
        if len(value) > max_length:
            raise ValueError(f"{message}（内容过长）")
        return value

    @staticmethod
    def _ok(**values: Any) -> dict[str, Any]:
        return {"ok": True, **values}

    @staticmethod
    def _error(message: str, **values: Any) -> dict[str, Any]:
        return {"ok": False, "message": message, **values}
