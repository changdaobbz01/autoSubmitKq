from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import random
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from runtime_paths import APP_ROOT

BASE_PAGE_URL = "https://ad-pro.xyang.xin:20002/ad/#/login?redirectTo=%2Fhome"
BASE_API_URL = "https://ad-pro.xyang.xin:20002/iflow/plugins/attendance"
PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDkU/q+WCysfHBkIjzySfr/YoJSV/S
vgGI6kgk+maamO9EQYCWGpeBAuz1b9X0SeDqeOByM7ntPvgg3aOVNnhK5mkZXgSkkof
S14HxZc63owBWSt26YtG96WpCoaSRArCYqr3zWFXKD5s7iAjYWJbjyBx2OU4D4OK6ec
I7yO35F6QIDAQAB
-----END PUBLIC KEY-----"""
REQUEST_ID_CHARS = string.ascii_letters + string.digits + "-_"
DEFAULT_SKEW_SECONDS = 300
DEFAULT_TIMEOUT_SECONDS = 20
PROJECT_DIR = APP_ROOT
DEFAULT_SESSION_PATH = PROJECT_DIR / ".attendance_auth" / "session.json"
DEFAULT_CAPTCHA_PATH = PROJECT_DIR / ".attendance_auth" / "captcha.png"


class AuthError(RuntimeError):
    """Base error for auth failures."""


class ApiError(AuthError):
    def __init__(self, ret_code: Optional[str], ret_msg: str, payload: Any | None = None) -> None:
        self.ret_code = ret_code
        self.ret_msg = ret_msg or "接口返回异常"
        self.payload = payload
        super().__init__(f"{self.ret_code or 'UNKNOWN'}: {self.ret_msg}")


@dataclass
class CaptchaChallenge:
    request_id: str
    image_base64: str

    @property
    def data_url(self) -> str:
        return f"data:image/png;base64,{self.image_base64}"


@dataclass
class SessionData:
    token: str
    token_exp: Optional[int]
    user_account: str
    user_name: str
    real_name: str
    department: str
    saved_at: int
    user_info: dict[str, Any]


class SessionStore:
    def __init__(self, path: Path = DEFAULT_SESSION_PATH) -> None:
        self.path = path

    def load(self) -> Optional[SessionData]:
        if not self.path.exists():
            return None
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return SessionData(**raw)

    def save(self, session: SessionData) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(asdict(session), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class AttendanceAuthClient:
    def __init__(
        self,
        base_api_url: str = BASE_API_URL,
        session_store: Optional[SessionStore] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        skew_seconds: int = DEFAULT_SKEW_SECONDS,
    ) -> None:
        self.base_api_url = base_api_url.rstrip("/")
        self.session_store = session_store or SessionStore()
        self.timeout_seconds = timeout_seconds
        self.skew_seconds = skew_seconds
        self._public_key = serialization.load_pem_public_key(PUBLIC_KEY_PEM)

    def generate_request_id(self, length: int = 21) -> str:
        return "".join(random.choice(REQUEST_ID_CHARS) for _ in range(length))

    def write_captcha_png(self, challenge: CaptchaChallenge, output_path: Path = DEFAULT_CAPTCHA_PATH) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(challenge.image_base64))
        return output_path

    def encrypt_password(self, password: str) -> str:
        encrypted = self._public_key.encrypt(password.encode("utf-8"), padding.PKCS1v15())
        return base64.b64encode(encrypted).decode("ascii")

    def fetch_captcha(self, request_id: Optional[str] = None) -> CaptchaChallenge:
        request_id = request_id or self.generate_request_id()
        payload = self._request_json(
            path=f"/adUser/user/getVerificationCode?requestId={request_id}",
            method="GET",
        )
        if payload.get("retCode") != "200" or not payload.get("retContent"):
            raise ApiError(payload.get("retCode"), payload.get("retMsg", "获取验证码失败"), payload)
        return CaptchaChallenge(request_id=request_id, image_base64=payload["retContent"])

    def login(
        self,
        user_account: str,
        password: str,
        verification_code: str,
        request_id: str,
    ) -> dict[str, Any]:
        body = {
            "userAccount": user_account,
            "pwd": self.encrypt_password(password),
            "requestId": request_id,
            "verificationCode": verification_code,
        }
        payload = self._request_json(
            path="/adUser/user/tologinNewV1",
            method="POST",
            body=body,
        )
        token = None
        if isinstance(payload.get("retContent"), dict):
            token = payload["retContent"].get("token")
        if payload.get("retCode") != "200" or not token:
            raise ApiError(payload.get("retCode"), payload.get("retMsg", "登录失败"), payload)
        return payload

    def get_user_info(self, token: str) -> dict[str, Any]:
        payload = self._request_json(
            path="/adUser/user/getUserInfo",
            method="GET",
            headers={"Access-Token": token},
        )
        if payload.get("retCode") != "200" or not payload.get("retContent"):
            raise ApiError(payload.get("retCode"), payload.get("retMsg", "获取用户信息失败"), payload)
        return payload

    def logout(self, token: str) -> dict[str, Any]:
        return self._request_json(
            path="/adUser/user/loginOut",
            method="POST",
            headers={"Access-Token": token},
        )

    def call_api(
        self,
        path: str,
        method: str = "GET",
        token: Optional[str] = None,
        params: Optional[dict[str, Any]] = None,
        body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if params:
            query = urllib.parse.urlencode(params, doseq=True)
            separator = "&" if "?" in path else "?"
            path = f"{path}{separator}{query}"

        headers: dict[str, str] = {}
        if token:
            headers["Access-Token"] = token

        return self._request_json(
            path=path,
            method=method,
            body=body,
            headers=headers or None,
        )

    def upload_file(
        self,
        path: str,
        file_path: Path,
        token: str,
        field_name: str = "fileData",
        filename: Optional[str] = None,
        content_type: Optional[str] = None,
        extra_fields: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        if not file_path.exists():
            raise AuthError(f"文件不存在: {file_path}")

        boundary = f"----CodexBoundary{int(time.time() * 1000)}"
        upload_name = filename or file_path.name
        upload_type = content_type or mimetypes.guess_type(upload_name)[0] or "application/octet-stream"
        body_bytes = self._build_multipart_body(
            boundary=boundary,
            field_name=field_name,
            filename=upload_name,
            file_bytes=file_path.read_bytes(),
            content_type=upload_type,
            extra_fields=extra_fields,
        )
        return self._request_json(
            path=path,
            method="POST",
            headers={
                "Access-Token": token,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            body_bytes=body_bytes,
        )

    def decode_jwt_payload(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise AuthError("token 不是合法 JWT")
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))

    def build_session(self, token: str, user_info_payload: dict[str, Any]) -> SessionData:
        jwt_payload = self.decode_jwt_payload(token)
        user_info = user_info_payload.get("retContent", {})
        return SessionData(
            token=token,
            token_exp=jwt_payload.get("exp"),
            user_account=str(user_info.get("userAccount") or jwt_payload.get("userAccount") or ""),
            user_name=str(user_info.get("userName") or jwt_payload.get("userName") or ""),
            real_name=str(user_info.get("realName") or jwt_payload.get("realName") or ""),
            department=str(user_info.get("department") or ""),
            saved_at=int(time.time()),
            user_info=user_info,
        )

    def is_session_reusable(self, session: SessionData, now: Optional[int] = None) -> bool:
        now = now or int(time.time())
        if not session.token:
            return False
        if session.token_exp is None:
            return True
        return session.token_exp - self.skew_seconds > now

    def get_cached_session(self, validate_with_server: bool = False) -> Optional[SessionData]:
        session = self.session_store.load()
        if session is None:
            return None
        if not self.is_session_reusable(session):
            self.session_store.clear()
            return None
        if not validate_with_server:
            return session
        try:
            user_info_payload = self.get_user_info(session.token)
        except ApiError:
            self.session_store.clear()
            return None
        refreshed = self.build_session(session.token, user_info_payload)
        self.session_store.save(refreshed)
        return refreshed

    def ensure_session(
        self,
        user_account: Optional[str] = None,
        password: Optional[str] = None,
        verification_code: Optional[str] = None,
        request_id: Optional[str] = None,
        validate_cached: bool = False,
        captcha_path: Path = DEFAULT_CAPTCHA_PATH,
    ) -> SessionData:
        cached = self.get_cached_session(validate_with_server=validate_cached)
        if cached is not None:
            return cached

        if not user_account or not password:
            raise AuthError("本地没有可复用 token，且未提供账号密码")

        if verification_code is None:
            challenge = self.fetch_captcha(request_id=request_id)
            self.write_captcha_png(challenge, captcha_path)
            print(f"验证码已保存到: {captcha_path}", file=sys.stderr)
            print(f"requestId: {challenge.request_id}", file=sys.stderr)
            verification_code = input("请输入验证码: ").strip()
            request_id = challenge.request_id
        elif request_id is None:
            raise AuthError("提供验证码时必须同时提供 requestId")

        login_payload = self.login(
            user_account=user_account,
            password=password,
            verification_code=verification_code,
            request_id=request_id,
        )
        token = login_payload["retContent"]["token"]
        user_info_payload = self.get_user_info(token)
        session = self.build_session(token, user_info_payload)
        self.session_store.save(session)
        return session

    def _build_multipart_body(
        self,
        boundary: str,
        field_name: str,
        filename: str,
        file_bytes: bytes,
        content_type: str,
        extra_fields: Optional[dict[str, Any]] = None,
    ) -> bytes:
        lines: list[bytes] = []
        for key, value in (extra_fields or {}).items():
            lines.extend(
                [
                    f"--{boundary}\r\n".encode("utf-8"),
                    f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"),
                    str(value).encode("utf-8"),
                    b"\r\n",
                ]
            )

        lines.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                file_bytes,
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        return b"".join(lines)

    def _request_json(
        self,
        path: str,
        method: str,
        body: Optional[dict[str, Any]] = None,
        body_bytes: Optional[bytes] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        url = f"{self.base_api_url}{path}"
        request_headers = {
            "Accept": "application/json, text/plain, */*",
        }
        if headers:
            request_headers.update(headers)

        data: bytes | None = None
        if body is not None and body_bytes is not None:
            raise AuthError("body 和 body_bytes 不能同时传入")
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request_headers["Content-Type"] = "application/json;charset=UTF-8"
        elif body_bytes is not None:
            data = body_bytes

        request = urllib.request.Request(url=url, data=data, headers=request_headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                raw = response.read().decode(charset, errors="ignore")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            raise AuthError(f"HTTP {exc.code}: {raw}") from exc
        except urllib.error.URLError as exc:
            raise AuthError(f"网络请求失败: {exc}") from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AuthError(f"接口未返回 JSON: {raw[:200]}") from exc


def _format_epoch(epoch: Optional[int]) -> Optional[str]:
    if epoch is None:
        return None
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))


def _print_json(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _session_to_json(session: SessionData, reused: bool) -> dict[str, Any]:
    return {
        "reused": reused,
        "userAccount": session.user_account,
        "userName": session.user_name,
        "realName": session.real_name,
        "department": session.department,
        "tokenExp": session.token_exp,
        "tokenExpText": _format_epoch(session.token_exp),
        "savedAt": session.saved_at,
        "savedAtText": _format_epoch(session.saved_at),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="掌上考勤登录参考客户端。默认优先复用本地 token，避免频繁触发登录接口。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="查看本地缓存 token 状态")

    captcha_parser = subparsers.add_parser("captcha", help="拉取一张新的验证码图片")
    captcha_parser.add_argument("--request-id", help="自定义 requestId，不传则自动生成")
    captcha_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_CAPTCHA_PATH,
        help="验证码输出路径",
    )

    clear_parser = subparsers.add_parser("clear", help="清理本地 session 缓存")
    clear_parser.add_argument("--logout", action="store_true", help="清缓存前尝试调用服务端登出")

    ensure_parser = subparsers.add_parser("ensure", help="优先复用 token；失效时再走登录")
    ensure_parser.add_argument("--username", help="登录账号")
    ensure_parser.add_argument("--password", help="登录密码")
    ensure_parser.add_argument("--code", help="验证码。传了就不会交互提示")
    ensure_parser.add_argument("--request-id", help="与验证码配套的 requestId")
    ensure_parser.add_argument(
        "--captcha-path",
        type=Path,
        default=DEFAULT_CAPTCHA_PATH,
        help="交互登录时验证码图片输出路径",
    )
    ensure_parser.add_argument(
        "--validate-cached",
        action="store_true",
        help="复用本地 token 前，先请求 getUserInfo 做服务端校验",
    )

    userinfo_parser = subparsers.add_parser("userinfo", help="用本地缓存 token 获取用户信息")
    userinfo_parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="成功后回写本地缓存中的 userInfo",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    client = AttendanceAuthClient()

    try:
        if args.command == "status":
            session = client.session_store.load()
            if session is None:
                _print_json({"cached": False, "basePageUrl": BASE_PAGE_URL, "baseApiUrl": BASE_API_URL})
                return 0
            _print_json(
                {
                    "cached": True,
                    "reusable": client.is_session_reusable(session),
                    "basePageUrl": BASE_PAGE_URL,
                    "baseApiUrl": BASE_API_URL,
                    **_session_to_json(session, reused=True),
                }
            )
            return 0

        if args.command == "captcha":
            challenge = client.fetch_captcha(request_id=args.request_id)
            path = client.write_captcha_png(challenge, args.output)
            _print_json(
                {
                    "requestId": challenge.request_id,
                    "output": str(path),
                    "base64Length": len(challenge.image_base64),
                }
            )
            return 0

        if args.command == "clear":
            session = client.session_store.load()
            logout_attempted = False
            logout_result: Any = None
            if args.logout and session and client.is_session_reusable(session):
                logout_attempted = True
                try:
                    logout_result = client.logout(session.token)
                except AuthError as exc:
                    logout_result = {"error": str(exc)}
            client.session_store.clear()
            _print_json({"cleared": True, "logoutAttempted": logout_attempted, "logoutResult": logout_result})
            return 0

        if args.command == "ensure":
            had_cached = client.session_store.load() is not None
            session = client.ensure_session(
                user_account=args.username,
                password=args.password,
                verification_code=args.code,
                request_id=args.request_id,
                validate_cached=args.validate_cached,
                captcha_path=args.captcha_path,
            )
            reused = had_cached and client.is_session_reusable(session)
            _print_json(_session_to_json(session, reused=reused))
            return 0

        if args.command == "userinfo":
            session = client.get_cached_session(validate_with_server=False)
            if session is None:
                raise AuthError("本地没有可复用 token，请先执行 ensure")
            payload = client.get_user_info(session.token)
            if args.refresh_cache:
                refreshed = client.build_session(session.token, payload)
                client.session_store.save(refreshed)
            _print_json(payload)
            return 0

    except AuthError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
