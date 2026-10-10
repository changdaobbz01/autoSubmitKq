from __future__ import annotations

import json
import unittest
from email.message import Message
from unittest.mock import patch

from attendance_auth_client import SessionData
from portal_auth_client import PortalSession, PortalSmsTicket
from token_uploader.bridge import TokenCollectorBridge
from token_uploader.cloud_client import CloudTokenClient, CloudUploadError


class _FakePortalClient:
    def __init__(self) -> None:
        self.login_count = 0

    def request_sms_code(self, user_account: str, password: str) -> PortalSmsTicket:
        return PortalSmsTicket(tick_token="private-ticket", message="验证码已发送")

    def login(self, user_account: str, password: str, sms_code: str, tick_token: str) -> PortalSession:
        self.login_count += 1
        if tick_token != "private-ticket":
            raise AssertionError("private ticket was not retained locally")
        return PortalSession("portal-token", "", user_account, "1", "湖北", {})

    def exchange_attendance_session(self, portal_session, attendance_client, *, selected_user_account):
        return SessionData(
            token="attendance-token",
            token_exp=2_000_000_000,
            user_account=selected_user_account,
            user_name="Tester",
            real_name="测试用户",
            department="运维组",
            saved_at=1,
            user_info={},
        )


class _FakeCloudClient:
    def __init__(self, base_url: str, *, fail_first_upload: bool = False) -> None:
        self.base_url = CloudTokenClient.normalize_base_url(base_url)
        self.fail_first_upload = fail_first_upload
        self.upload_count = 0
        self.received_session: SessionData | None = None

    def validate_access(self, access_key: str):
        if access_key != "cloud-key":
            raise CloudUploadError("云端访问口令无效")
        return {"connected": True, "accountCount": 0}

    def upload(self, session: SessionData, access_key: str):
        self.upload_count += 1
        self.received_session = session
        if self.fail_first_upload and self.upload_count == 1:
            raise CloudUploadError("temporary failure")
        return {
            "userAccount": session.user_account,
            "realName": session.real_name,
            "revision": 7,
        }


class _Response:
    def __init__(self, payload) -> None:
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.headers = Message()
        self.headers["Content-Type"] = "application/json; charset=utf-8"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return self._body


class TokenCollectorBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.portal = _FakePortalClient()
        self.cloud = _FakeCloudClient("https://cloud.example/collector/")
        self.bridge = TokenCollectorBridge(
            portal_client=self.portal,
            attendance_client=object(),
            cloud_client_factory=lambda _url: self.cloud,
        )
        self.base_payload = {
            "cloudBaseUrl": "https://cloud.example/collector/",
            "accessKey": "cloud-key",
            "userAccount": "account01",
            "password": "portal-password",
        }

    def test_challenge_keeps_private_ticket_out_of_ui_and_uploads_only_session(self) -> None:
        challenge = self.bridge.request_sms(self.base_payload)
        self.assertTrue(challenge["ok"])
        self.assertNotIn("private-ticket", json.dumps(challenge))

        result = self.bridge.complete_login(
            {
                **self.base_payload,
                "challengeId": challenge["challengeId"],
                "smsCode": "123456",
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual("attendance-token", self.cloud.received_session.token)
        self.assertNotIn("portal-password", json.dumps(result, ensure_ascii=False))

    def test_cloud_upload_can_retry_without_repeating_portal_login(self) -> None:
        self.cloud.fail_first_upload = True
        challenge = self.bridge.request_sms(self.base_payload)
        complete_payload = {
            **self.base_payload,
            "challengeId": challenge["challengeId"],
            "smsCode": "123456",
        }

        first = self.bridge.complete_login(complete_payload)
        second = self.bridge.complete_login(complete_payload)

        self.assertFalse(first["ok"])
        self.assertTrue(first["retryableUpload"])
        self.assertTrue(second["ok"])
        self.assertEqual(1, self.portal.login_count)
        self.assertEqual(2, self.cloud.upload_count)


class CloudTokenClientTests(unittest.TestCase):
    def test_preserves_deployment_prefix_when_building_api_url(self) -> None:
        captured = {}

        def open_request(request, timeout):
            captured["url"] = request.full_url
            captured["key"] = request.get_header("X-mobile-access-key")
            return _Response([])

        client = CloudTokenClient("https://cloud.example/attendance-token")
        with patch("token_uploader.cloud_client.direct_urlopen", side_effect=open_request):
            result = client.validate_access("cloud-key")

        self.assertTrue(result["connected"])
        self.assertEqual(
            "https://cloud.example/attendance-token/api/mobile/accounts?limit=1",
            captured["url"],
        )
        self.assertEqual("cloud-key", captured["key"])


if __name__ == "__main__":
    unittest.main()
