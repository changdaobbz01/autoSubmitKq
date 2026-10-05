from __future__ import annotations

import base64
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from account_registry import AccountRegistry
from attendance_auth_client import SessionData, SessionStore
from cloud_token_sync import CloudTokenSyncManager
from rebuild_login.server import ClockDryRunScheduler


def _encode_segment(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _jwt(user_account: str, exp: int, **claims: str) -> str:
    return ".".join(
        [
            _encode_segment({"alg": "none", "typ": "JWT"}),
            _encode_segment({"userAccount": user_account, "exp": exp, **claims}),
            "signature",
        ]
    )


class _FakeCloudClient:
    def __init__(self, snapshot: dict) -> None:
        self.snapshot = snapshot

    def fetch_all(self) -> dict:
        return self.snapshot


class _FakeAutoSyncManager:
    def __init__(self) -> None:
        self.called = threading.Event()
        self.calls: list[tuple[str, str]] = []

    def get_due_auto_sync(self, _next_slot: dict, _next_run_at: int, _now_epoch: int) -> dict | None:
        if self.called.is_set():
            return None
        return {"slotKey": "slot-1:test"}

    def run_sync(self, trigger: str, auto_slot_key: str) -> dict:
        self.calls.append((trigger, auto_slot_key))
        self.called.set()
        return {"ok": True}


class CloudTokenSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.registry = AccountRegistry(
            registry_path=root / "accounts_registry.json",
            accounts_dir=root / "accounts",
        )
        self.config_path = root / "cloud_sync.json"
        self.local_account = {
            "userAccount": "testuser01",
            "password": "local-password",
            "realName": "本地姓名",
            "department": "本地部门",
            "enabled": True,
            "note": "本地备注",
            "photoPath": r"D:\photos\testuser01.jpg",
            "clockAddress": "本地打卡地址",
            "latitude": "30.123",
            "longitude": "114.456",
            "createdAt": 1,
            "updatedAt": 1,
        }
        self.registry.save({"accounts": [dict(self.local_account)], "updatedAt": 1})

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _manager(self, snapshot: dict) -> CloudTokenSyncManager:
        manager = CloudTokenSyncManager(
            self.registry,
            config_path=self.config_path,
            client_factory=lambda _base_url, _api_key: _FakeCloudClient(snapshot),
        )
        manager.save_config(
            {
                "baseUrl": "http://cloud.invalid",
                "desktopApiKey": "desktop-secret",
                "leadMinutes": 10,
            }
        )
        return manager

    def test_sync_updates_only_session_and_preserves_local_profile(self) -> None:
        exp = int(time.time()) + 3600
        token = _jwt("testuser01", exp, userName="云端姓名")
        snapshot = {
            "latestRevision": 2,
            "serverTime": "2026-10-05T04:00:00Z",
            "items": [
                {
                    "userAccount": "TESTUSER01",
                    "realName": "云端姓名",
                    "department": "云端部门",
                    "status": "active",
                    "token": token,
                    "tokenExpiresAt": datetime.fromtimestamp(exp, timezone.utc).isoformat(),
                    "revision": 2,
                    "updatedAt": "2026-10-05T03:59:00Z",
                },
                {
                    "userAccount": "cloud-only",
                    "realName": "仅云端账号",
                    "department": "云端部门",
                    "status": "active",
                    "token": _jwt("cloud-only", exp),
                    "tokenExpiresAt": datetime.fromtimestamp(exp, timezone.utc).isoformat(),
                    "revision": 1,
                    "updatedAt": "2026-10-05T03:58:00Z",
                },
            ],
        }
        before = self.registry.load()

        report = self._manager(snapshot).run_sync()

        self.assertEqual(before, self.registry.load())
        self.assertEqual(1, report["updatedCount"])
        self.assertEqual(["testuser01"], report["updatedAccounts"])
        self.assertIn("已更新本地 Token：testuser01", report["summary"])
        self.assertEqual(["cloud-only"], report["unmatchedCloudAccounts"])
        session = SessionStore(self.registry.get_session_path("testuser01")).load()
        self.assertIsNotNone(session)
        self.assertEqual(token, session.token)
        self.assertEqual("testuser01", session.user_account)
        self.assertEqual(exp, session.token_exp)

    def test_sync_reports_account_when_token_is_unchanged(self) -> None:
        exp = int(time.time()) + 3600
        token = _jwt("testuser01", exp)
        store = SessionStore(self.registry.get_session_path("testuser01"))
        store.save(
            SessionData(
                token=token,
                token_exp=exp,
                user_account="testuser01",
                user_name="本地姓名",
                real_name="本地姓名",
                department="本地部门",
                saved_at=int(time.time()),
                user_info={},
            )
        )
        snapshot = {
            "latestRevision": 1,
            "items": [
                {
                    "userAccount": "testuser01",
                    "status": "active",
                    "token": token,
                    "tokenExpiresAt": datetime.fromtimestamp(exp, timezone.utc).isoformat(),
                    "revision": 1,
                }
            ],
        }

        report = self._manager(snapshot).run_sync()

        self.assertEqual(0, report["updatedCount"])
        self.assertEqual(["testuser01"], report["unchangedAccounts"])
        self.assertIn("Token 未变化：testuser01", report["summary"])

    def test_sync_rejects_jwt_account_mismatch(self) -> None:
        exp = int(time.time()) + 3600
        snapshot = {
            "latestRevision": 1,
            "items": [
                {
                    "userAccount": "testuser01",
                    "status": "active",
                    "token": _jwt("another-account", exp),
                    "tokenExpiresAt": datetime.fromtimestamp(exp, timezone.utc).isoformat(),
                    "revision": 1,
                }
            ],
        }

        report = self._manager(snapshot).run_sync()

        self.assertEqual(0, report["updatedCount"])
        self.assertEqual(1, report["conflictCount"])
        self.assertFalse(self.registry.get_session_path("testuser01").exists())

    def test_expired_cloud_record_does_not_overwrite_local_session(self) -> None:
        exp = int(time.time()) + 7200
        store = SessionStore(self.registry.get_session_path("testuser01"))
        store.save(
            SessionData(
                token=_jwt("testuser01", exp),
                token_exp=exp,
                user_account="testuser01",
                user_name="本地姓名",
                real_name="本地姓名",
                department="本地部门",
                saved_at=int(time.time()),
                user_info={},
            )
        )
        original = store.load()
        snapshot = {
            "latestRevision": 3,
            "items": [
                {
                    "userAccount": "testuser01",
                    "status": "expired",
                    "token": None,
                    "tokenExpiresAt": "2026-01-01T00:00:00Z",
                    "revision": 3,
                }
            ],
        }

        report = self._manager(snapshot).run_sync()

        self.assertEqual(1, report["expiredCloudCount"])
        self.assertEqual(original.token, store.load().token)

    def test_completed_auto_slot_is_not_requested_twice(self) -> None:
        exp = int(time.time()) + 3600
        snapshot = {
            "latestRevision": 1,
            "items": [
                {
                    "userAccount": "testuser01",
                    "status": "active",
                    "token": _jwt("testuser01", exp),
                    "tokenExpiresAt": datetime.fromtimestamp(exp, timezone.utc).isoformat(),
                    "revision": 1,
                }
            ],
        }
        manager = self._manager(snapshot)
        manager.save_config({"autoSyncEnabled": True})
        now = int(time.time())
        next_slot = {
            "key": "slot-1",
            "name": "打卡时点 1",
            "baseAt": now + 120,
            "scheduledAt": now + 180,
        }

        due = manager.get_due_auto_sync(next_slot, now + 180, now)
        self.assertIsNotNone(due)
        manager.run_sync(trigger="auto", auto_slot_key=due["slotKey"])

        self.assertIsNone(manager.get_due_auto_sync(next_slot, now + 180, now + 1))

    def test_polling_thread_runs_due_cloud_sync(self) -> None:
        root = Path(self.temp_dir.name)
        auto_sync = _FakeAutoSyncManager()
        scheduler = ClockDryRunScheduler(
            self.registry,
            cloud_token_sync=auto_sync,
            state_path=root / "polling_state.json",
        )
        try:
            scheduler.start()
            self.assertTrue(auto_sync.called.wait(3), "轮询线程没有触发到期的云端同步")
        finally:
            scheduler.shutdown()

        self.assertEqual([("auto", "slot-1:test")], auto_sync.calls)


if __name__ == "__main__":
    unittest.main()
