from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from attendance_auth_client import SessionData, SessionStore
from portal_auth_client import (
    PortalAppConfig,
    PortalAuthClient,
    PortalAuthCoordinator,
    PortalAuthError,
    PortalDeviceStore,
    PortalSession,
    PortalSmsTicket,
)


_TEST_PUBLIC_KEY_BASE64 = (
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCYLKxkLI2TwnLConEBXUaNbiaDmsOtarZ2RpLDCjqaQQpgjzbd8P9"
    "nd1KPwwO45Ilg1+xvychxeD9z6LJZ18b9roHVCc8HxuLzrbhRQ+80MJXrtKpmRLwoeK6KcL5zPi5/cNmNiGbxM8o8s"
    "ug9Vif+h2Isa2jU2tDuSf3ebf/n1QIDAQAB"
)


class _FixedPortalClient(PortalAuthClient):
    def __init__(self, payload: dict) -> None:
        super().__init__(base_api_url="http://portal.invalid")
        self.payload = payload

    def _request_encrypted_json(self, path: str, body: dict[str, str]) -> dict:
        return self.payload


class _CoordinatorPortalClient:
    def request_sms_code(self, user_account: str, password: str) -> PortalSmsTicket:
        return PortalSmsTicket(tick_token="private-ticket", message="验证码已发送")


class _FakeAttendanceClient:
    def __init__(self, path: Path) -> None:
        self.session_store = SessionStore(path)


class PortalCryptoTests(unittest.TestCase):
    def test_3des_round_trip_preserves_unicode_json(self) -> None:
        payload = {"username": "测试账号", "password": "p@ssword"}
        encrypted = PortalAuthClient._encrypt_json(payload)
        decrypted = PortalAuthClient._decrypt_text(encrypted)
        self.assertEqual(payload, json.loads(decrypted))

    def test_sms_response_keeps_ticket_private(self) -> None:
        client = _FixedPortalClient(
            {
                "success": True,
                "data": {"code": "1", "token": "tick-secret", "message": "验证码已发送"},
            }
        )
        ticket = client.request_sms_code("account", "password")
        self.assertEqual("tick-secret", ticket.tick_token)

    def test_device_id_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = PortalDeviceStore(Path(temp_dir) / "portal_device.json")
            first = store.get_or_create()
            second = store.get_or_create()
        self.assertEqual(first, second)
        self.assertEqual(16, len(first))

    def test_public_challenge_does_not_expose_tick_token(self) -> None:
        coordinator = PortalAuthCoordinator(client=_CoordinatorPortalClient())
        payload = coordinator.request_sms_code("account", "password")
        self.assertTrue(payload["sent"])
        self.assertNotIn("tickToken", payload)
        self.assertNotIn("private-ticket", json.dumps(payload))

    def test_sms_requests_are_rate_limited_per_account(self) -> None:
        coordinator = PortalAuthCoordinator(client=_CoordinatorPortalClient())
        coordinator.request_sms_code("account", "password")
        with self.assertRaisesRegex(PortalAuthError, "重新发送"):
            coordinator.request_sms_code("account", "password")


class PortalExchangeTests(unittest.TestCase):
    def test_exchange_passes_opaque_mapping_credential_to_attendance_login(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            attendance = _ExchangeAttendanceClient(Path(temp_dir) / "session.json")
            client = PortalAuthClient(base_api_url="http://portal.invalid")
            client.resolve_attendance_app_config = lambda session: PortalAppConfig(
                app_id="834786",
                public_key=_TEST_PUBLIC_KEY_BASE64,
                start_url="https://attendance.invalid",
            )
            session = client.exchange_attendance_session(
                PortalSession(
                    token="portal-token",
                    ticket="",
                    username="account",
                    user_id="1",
                    area="湖北",
                    user_info={},
                ),
                attendance,
                selected_user_account="attendance-account",
            )
        self.assertEqual("attendance-account", session.user_account)
        self.assertEqual(
            [
                "/adUser/user/getToken",
                "/adUser/user/getWlyyUser",
                "/adUser/user/tologinNewV1ByAccount",
            ],
            attendance.paths,
        )
        self.assertEqual(
            "encrypted-account-credential",
            attendance.request_bodies["/adUser/user/tologinNewV1ByAccount"]["userAccount"],
        )

    def test_exchange_rejects_resolved_attendance_account_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            attendance = _ExchangeAttendanceClient(Path(temp_dir) / "session.json")
            client = PortalAuthClient(base_api_url="http://portal.invalid")
            client.resolve_attendance_app_config = lambda _session: PortalAppConfig(
                app_id="attendance",
                public_key=_TEST_PUBLIC_KEY_BASE64,
                start_url="https://attendance.invalid/",
            )
            with self.assertRaisesRegex(
                PortalAuthError,
                "门户登录后的考勤账号 attendance-account，与当前选择账号 another-account 不一致",
            ):
                client.exchange_attendance_session(
                    PortalSession(
                        token="portal-token",
                        ticket="ticket",
                        username="another-account",
                        user_id="1",
                        area="",
                        user_info={},
                    ),
                    attendance,
                    selected_user_account="another-account",
                )


class _ExchangeAttendanceClient(_FakeAttendanceClient):
    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.paths: list[str] = []
        self.request_bodies: dict[str, dict] = {}

    def call_api(self, path: str, **kwargs):
        self.paths.append(path)
        self.request_bodies[path] = kwargs.get("body") or {}
        if path.endswith("/getToken"):
            return {"retCode": "200", "retContent": "exchange-token"}
        if path.endswith("/getWlyyUser"):
            return {"code": 1000, "data": "encrypted-account-credential"}
        return {"retCode": "200", "retContent": {"token": "attendance-token"}}

    def get_user_info(self, token: str):
        return {
            "retCode": "200",
            "retContent": {"userAccount": "attendance-account", "userName": "Tester"},
        }

    def build_session(self, token: str, user_info_payload: dict) -> SessionData:
        return SessionData(
            token=token,
            token_exp=None,
            user_account="attendance-account",
            user_name="Tester",
            real_name="",
            department="",
            saved_at=1,
            user_info=user_info_payload["retContent"],
        )


if __name__ == "__main__":
    unittest.main()
