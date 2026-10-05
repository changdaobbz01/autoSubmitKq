from __future__ import annotations

import base64
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from account_registry import AccountRegistry
from attendance_auth_client import SessionData, SessionStore
from runtime_paths import APP_ROOT


CLOUD_SYNC_CONFIG_PATH = APP_ROOT / ".attendance_auth" / "cloud_token_sync.json"
DEFAULT_CLOUD_BASE_URL = "http://127.0.0.1:8088"
DEFAULT_LEAD_MINUTES = 10
MIN_LEAD_MINUTES = 1
MAX_LEAD_MINUTES = 180
AUTO_RETRY_SECONDS = 60
TOKEN_SKEW_SECONDS = 300


class CloudSyncError(RuntimeError):
    """Cloud token sync failed without exposing credentials."""


def _normalize_account(value: Any) -> str:
    return str(value or "").strip().casefold()


def _format_epoch(epoch: int | None) -> str:
    if not epoch:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))


def _parse_iso_epoch(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CloudSyncError(f"云端 tokenExpiresAt 格式无效: {raw}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise CloudSyncError("云端返回的 token 不是合法 JWT")
    payload_text = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_text.encode("ascii")).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloudSyncError("云端返回的 JWT 载荷无法解析") from exc
    if not isinstance(payload, dict):
        raise CloudSyncError("云端返回的 JWT 载荷格式无效")
    return payload


def _validate_base_url(value: Any) -> str:
    raw = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("云端服务地址必须是有效的 http 或 https 地址。")
    if parsed.query or parsed.fragment:
        raise ValueError("云端服务地址不能包含查询参数或锚点。")
    return raw


def _mask_secret(value: str) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}{'*' * min(12, len(raw) - 8)}{raw[-4:]}"


class CloudTokenApiClient:
    def __init__(self, base_url: str, desktop_api_key: str, timeout_seconds: int = 20) -> None:
        self.base_url = _validate_base_url(base_url)
        self.desktop_api_key = str(desktop_api_key or "").strip()
        self.timeout_seconds = timeout_seconds

    def fetch_all(self) -> dict[str, Any]:
        since = 0
        items: list[dict[str, Any]] = []
        latest_revision = 0
        server_time = ""
        seen_cursors: set[int] = set()

        for _ in range(100):
            if since in seen_cursors:
                raise CloudSyncError("云端分页游标重复，已停止同步。")
            seen_cursors.add(since)
            page = self._fetch_page(since)
            raw_items = page.get("items")
            if not isinstance(raw_items, list):
                raise CloudSyncError("云端同步响应缺少 items 数组。")
            items.extend(item for item in raw_items if isinstance(item, dict))
            latest_revision = int(page.get("latestRevision") or latest_revision or 0)
            server_time = str(page.get("serverTime") or server_time or "")
            if not bool(page.get("hasMore")):
                return {
                    "items": items,
                    "latestRevision": latest_revision,
                    "serverTime": server_time,
                }
            next_revision = int(page.get("nextRevision") or 0)
            if next_revision <= since:
                raise CloudSyncError("云端分页游标没有前进，已停止同步。")
            since = next_revision

        raise CloudSyncError("云端账号分页超过安全上限，已停止同步。")

    def _fetch_page(self, since: int) -> dict[str, Any]:
        query = urllib.parse.urlencode({"since": max(0, since), "limit": 500})
        request = urllib.request.Request(
            f"{self.base_url}/api/desktop/v1/tokens?{query}",
            headers={
                "Accept": "application/json",
                "X-Desktop-Key": self.desktop_api_key,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in {401, 403}:
                raise CloudSyncError("云端访问口令不正确或无权访问桌面同步接口。") from exc
            raise CloudSyncError(f"云端同步接口返回 HTTP {exc.code}。") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise CloudSyncError(f"无法连接云端同步服务：{reason}") from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CloudSyncError("云端同步接口返回了无法解析的数据。") from exc
        if not isinstance(payload, dict):
            raise CloudSyncError("云端同步接口响应格式无效。")
        return payload


class CloudTokenSyncManager:
    def __init__(
        self,
        account_registry: AccountRegistry,
        config_path: Path = CLOUD_SYNC_CONFIG_PATH,
        client_factory: Callable[[str, str], CloudTokenApiClient] = CloudTokenApiClient,
    ) -> None:
        self.account_registry = account_registry
        self.config_path = config_path
        self.client_factory = client_factory
        self._config_lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._execution_lock = threading.Lock()
        self._syncing = False

    def load_config(self) -> dict[str, Any]:
        with self._config_lock:
            defaults = {
                "baseUrl": DEFAULT_CLOUD_BASE_URL,
                "desktopApiKey": "",
                "autoSyncEnabled": False,
                "leadMinutes": DEFAULT_LEAD_MINUTES,
            }
            if not self.config_path.exists():
                return defaults
            try:
                payload = json.loads(self.config_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return defaults
            if not isinstance(payload, dict):
                return defaults
            return {**defaults, **payload}

    def save_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._config_lock:
            config = self.load_config()
            if "baseUrl" in updates:
                config["baseUrl"] = _validate_base_url(updates.get("baseUrl"))

            supplied_key = str(updates.get("desktopApiKey") or "").strip()
            if supplied_key:
                config["desktopApiKey"] = supplied_key
            if bool(updates.get("clearDesktopApiKey", False)):
                config["desktopApiKey"] = ""

            if "autoSyncEnabled" in updates:
                raw_enabled = updates.get("autoSyncEnabled")
                config["autoSyncEnabled"] = (
                    raw_enabled.strip().lower() in {"1", "true", "yes", "on"}
                    if isinstance(raw_enabled, str)
                    else bool(raw_enabled)
                )

            if "leadMinutes" in updates:
                try:
                    lead_minutes = int(updates.get("leadMinutes"))
                except (TypeError, ValueError) as exc:
                    raise ValueError("自动同步提前分钟数必须是整数。") from exc
                if not MIN_LEAD_MINUTES <= lead_minutes <= MAX_LEAD_MINUTES:
                    raise ValueError(
                        f"自动同步提前分钟数必须在 {MIN_LEAD_MINUTES}-{MAX_LEAD_MINUTES} 之间。"
                    )
                config["leadMinutes"] = lead_minutes

            if config.get("autoSyncEnabled") and not str(config.get("desktopApiKey") or "").strip():
                raise ValueError("开启自动同步前，请先填写桌面 API 访问口令。")

            config["updatedAt"] = int(time.time())
            self._save_config(config)
            return config

    def get_public_status(self, polling_schedule: dict[str, Any] | None = None) -> dict[str, Any]:
        config = self.load_config()
        api_key = str(config.get("desktopApiKey") or "")
        base_url = str(config.get("baseUrl") or DEFAULT_CLOUD_BASE_URL)
        auto_enabled = bool(config.get("autoSyncEnabled", False))
        lead_minutes = int(config.get("leadMinutes") or DEFAULT_LEAD_MINUTES)
        polling_schedule = polling_schedule or {}
        polling_enabled = bool(polling_schedule.get("enabled", False))
        next_sync = self._compute_next_auto_sync(
            polling_schedule=polling_schedule,
            lead_minutes=lead_minutes,
            last_auto_slot_key=str(config.get("lastAutoSyncSlotKey") or ""),
        ) if auto_enabled and polling_enabled and api_key else None

        with self._state_lock:
            syncing = self._syncing

        last_sync = config.get("lastSync") if isinstance(config.get("lastSync"), dict) else None
        return {
            "baseUrl": base_url,
            "hasDesktopApiKey": bool(api_key),
            "desktopApiKeyMasked": _mask_secret(api_key),
            "autoSyncEnabled": auto_enabled,
            "leadMinutes": lead_minutes,
            "configured": bool(base_url and api_key),
            "pollingEnabled": polling_enabled,
            "syncing": syncing,
            "nextAutoSyncAt": next_sync.get("syncAt") if next_sync else None,
            "nextAutoSyncAtText": _format_epoch(next_sync.get("syncAt")) if next_sync else "",
            "nextAutoSyncSlotText": next_sync.get("slotText", "") if next_sync else "",
            "nextAutoSyncDue": bool(next_sync and next_sync.get("due")),
            "lastSync": last_sync,
            "updatedAt": config.get("updatedAt"),
            "configPath": str(self.config_path),
            "dataPolicy": {
                "cloudFields": ["userAccount", "token", "tokenExpiresAt", "realName", "department"],
                "localOnlyFields": [
                    "password",
                    "photoPath",
                    "clockAddress",
                    "latitude",
                    "longitude",
                    "enabled",
                    "note",
                ],
                "cloudOnlyAccountsCreated": False,
            },
        }

    def run_sync(self, trigger: str = "manual", auto_slot_key: str = "") -> dict[str, Any]:
        if not self._execution_lock.acquire(blocking=False):
            raise CloudSyncError("云端同步正在执行，请稍后再试。")

        started_at = int(time.time())
        with self._state_lock:
            self._syncing = True
        try:
            config = self.load_config()
            base_url = str(config.get("baseUrl") or "").strip()
            desktop_api_key = str(config.get("desktopApiKey") or "").strip()
            if not base_url or not desktop_api_key:
                raise CloudSyncError("请先保存云端服务地址和桌面 API 访问口令。")

            client = self.client_factory(base_url, desktop_api_key)
            snapshot = client.fetch_all()
            report = self._apply_snapshot(snapshot, trigger=trigger, started_at=started_at)
            with self._config_lock:
                config = self.load_config()
                config["lastSync"] = report
                if trigger == "auto" and auto_slot_key:
                    config["lastAutoSyncSlotKey"] = auto_slot_key
                config["lastAttemptAt"] = report["finishedAt"]
                config["lastAttemptOk"] = True
                config["lastAttemptTrigger"] = trigger
                config["lastAttemptSlotKey"] = auto_slot_key
                self._save_config(config)
            return report
        except Exception as exc:  # noqa: BLE001
            message = str(exc) or exc.__class__.__name__
            report = {
                "ok": False,
                "trigger": trigger,
                "startedAt": started_at,
                "startedAtText": _format_epoch(started_at),
                "finishedAt": int(time.time()),
                "finishedAtText": _format_epoch(int(time.time())),
                "summary": f"云端同步失败：{message}",
                "error": message,
            }
            with self._config_lock:
                config = self.load_config()
                config["lastSync"] = report
                config["lastAttemptAt"] = report["finishedAt"]
                config["lastAttemptOk"] = False
                config["lastAttemptTrigger"] = trigger
                config["lastAttemptSlotKey"] = auto_slot_key
                self._save_config(config)
            if isinstance(exc, CloudSyncError):
                raise
            raise CloudSyncError(message) from exc
        finally:
            with self._state_lock:
                self._syncing = False
            self._execution_lock.release()

    def get_due_auto_sync(
        self,
        next_slot: dict[str, Any] | None,
        next_run_at: int | None,
        now_epoch: int | None = None,
    ) -> dict[str, Any] | None:
        if not isinstance(next_slot, dict):
            return None
        config = self.load_config()
        if not bool(config.get("autoSyncEnabled")):
            return None
        if not str(config.get("desktopApiKey") or "").strip():
            return None

        now_epoch = int(now_epoch or time.time())
        base_at = self._slot_base_at(next_slot)
        if not base_at:
            return None
        lead_minutes = int(config.get("leadMinutes") or DEFAULT_LEAD_MINUTES)
        sync_at = base_at - lead_minutes * 60
        slot_key = f"{next_slot.get('key') or 'slot'}:{base_at}"
        if str(config.get("lastAutoSyncSlotKey") or "") == slot_key:
            return None

        last_attempt_at = int(config.get("lastAttemptAt") or 0)
        if (
            not bool(config.get("lastAttemptOk", True))
            and str(config.get("lastAttemptSlotKey") or "") == slot_key
            and now_epoch - last_attempt_at < AUTO_RETRY_SECONDS
        ):
            return None

        run_deadline = max(base_at, int(next_run_at or 0))
        if sync_at <= now_epoch < run_deadline:
            return {
                "slotKey": slot_key,
                "slotName": str(next_slot.get("name") or "打卡时点"),
                "baseAt": base_at,
                "baseAtText": _format_epoch(base_at),
                "syncAt": sync_at,
                "syncAtText": _format_epoch(sync_at),
            }
        return None

    def _apply_snapshot(
        self,
        snapshot: dict[str, Any],
        *,
        trigger: str,
        started_at: int,
    ) -> dict[str, Any]:
        raw_items = snapshot.get("items")
        if not isinstance(raw_items, list):
            raise CloudSyncError("云端同步响应缺少账号列表。")

        local_registry = self.account_registry.load()
        local_accounts = [item for item in local_registry.get("accounts", []) if isinstance(item, dict)]
        local_by_key: dict[str, list[dict[str, Any]]] = {}
        for account in local_accounts:
            key = _normalize_account(account.get("userAccount"))
            if key:
                local_by_key.setdefault(key, []).append(account)

        cloud_by_key: dict[str, dict[str, Any]] = {}
        malformed_cloud_items: list[str] = []
        for item in raw_items:
            if not isinstance(item, dict):
                malformed_cloud_items.append("云端存在非对象账号记录")
                continue
            cloud_account = str(item.get("userAccount") or "").strip()
            key = _normalize_account(cloud_account)
            if not key:
                malformed_cloud_items.append("云端存在缺少 userAccount 的记录")
                continue
            previous = cloud_by_key.get(key)
            if previous is None or int(item.get("revision") or 0) >= int(previous.get("revision") or 0):
                cloud_by_key[key] = item

        updated_accounts: list[str] = []
        unchanged_accounts: list[str] = []
        expired_cloud_accounts: list[str] = []
        unmatched_cloud_accounts: list[str] = []
        conflicts: list[dict[str, str]] = []
        identity_warnings: list[dict[str, str]] = []
        matched_keys: set[str] = set()
        now_epoch = int(time.time())

        for key, item in sorted(cloud_by_key.items()):
            cloud_account = str(item.get("userAccount") or "").strip()
            candidates = local_by_key.get(key, [])
            if not candidates:
                unmatched_cloud_accounts.append(cloud_account)
                continue
            if len(candidates) > 1:
                conflicts.append(
                    {
                        "userAccount": cloud_account,
                        "reason": "本地存在仅大小写不同的重复账号，无法安全匹配。",
                    }
                )
                continue

            local_account = candidates[0]
            local_user_account = str(local_account.get("userAccount") or "").strip()
            matched_keys.add(key)
            self._append_identity_warnings(identity_warnings, local_account, item)

            token = str(item.get("token") or "").strip()
            if str(item.get("status") or "").strip().lower() != "active" or not token:
                expired_cloud_accounts.append(local_user_account)
                continue

            try:
                jwt_payload = _decode_jwt_payload(token)
                jwt_account = str(jwt_payload.get("userAccount") or "").strip()
                if not jwt_account:
                    raise CloudSyncError("JWT 中缺少 userAccount")
                if _normalize_account(jwt_account) != key:
                    raise CloudSyncError(
                        f"API 账号 {cloud_account} 与 JWT 账号 {jwt_account} 不一致"
                    )
                if _normalize_account(local_user_account) != _normalize_account(jwt_account):
                    raise CloudSyncError(
                        f"本地账号 {local_user_account} 与 JWT 账号 {jwt_account} 不一致"
                    )

                jwt_exp = int(jwt_payload.get("exp")) if jwt_payload.get("exp") is not None else None
                api_exp = _parse_iso_epoch(item.get("tokenExpiresAt"))
                if jwt_exp and api_exp and abs(jwt_exp - api_exp) > 60:
                    raise CloudSyncError("JWT 到期时间与云端记录不一致")
                token_exp = jwt_exp or api_exp
                if token_exp is not None and token_exp - TOKEN_SKEW_SECONDS <= now_epoch:
                    expired_cloud_accounts.append(local_user_account)
                    continue
            except (CloudSyncError, TypeError, ValueError) as exc:
                conflicts.append({"userAccount": local_user_account, "reason": str(exc)})
                continue

            session_store = SessionStore(self.account_registry.get_session_path(local_user_account))
            try:
                existing_session = session_store.load()
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                existing_session = None

            cloud_real_name = str(item.get("realName") or jwt_payload.get("realName") or "").strip()
            cloud_department = str(item.get("department") or jwt_payload.get("department") or "").strip()
            session = SessionData(
                token=token,
                token_exp=token_exp,
                user_account=local_user_account,
                user_name=str(jwt_payload.get("userName") or cloud_real_name or "").strip(),
                real_name=cloud_real_name,
                department=cloud_department,
                saved_at=now_epoch,
                user_info={
                    "userAccount": local_user_account,
                    "userName": str(jwt_payload.get("userName") or cloud_real_name or "").strip(),
                    "realName": cloud_real_name,
                    "department": cloud_department,
                    "cloudRevision": int(item.get("revision") or 0),
                    "cloudUpdatedAt": str(item.get("updatedAt") or ""),
                },
            )
            if (
                existing_session is not None
                and existing_session.token == session.token
                and existing_session.token_exp == session.token_exp
                and _normalize_account(existing_session.user_account) == key
            ):
                unchanged_accounts.append(local_user_account)
                continue
            session_store.save(session)
            updated_accounts.append(local_user_account)

        local_without_cloud_accounts = sorted(
            str(items[0].get("userAccount") or "").strip()
            for key, items in local_by_key.items()
            if key not in cloud_by_key
        )
        duplicate_local_count = sum(1 for items in local_by_key.values() if len(items) > 1)
        finished_at = int(time.time())
        matched_count = len(matched_keys)
        summary = (
            f"云端读取 {len(cloud_by_key)} 个账号，本地匹配 {matched_count} 个，"
            f"更新 token {len(updated_accounts)} 个，保持不变 {len(unchanged_accounts)} 个。"
        )
        if updated_accounts:
            summary += f" 已更新本地 Token：{'、'.join(updated_accounts)}。"
        if unchanged_accounts:
            summary += f" Token 未变化：{'、'.join(unchanged_accounts)}。"
        report = {
            "ok": True,
            "trigger": trigger,
            "startedAt": started_at,
            "startedAtText": _format_epoch(started_at),
            "finishedAt": finished_at,
            "finishedAtText": _format_epoch(finished_at),
            "latestRevision": int(snapshot.get("latestRevision") or 0),
            "serverTime": str(snapshot.get("serverTime") or ""),
            "fetchedCount": len(cloud_by_key),
            "localCount": len(local_accounts),
            "matchedCount": matched_count,
            "updatedCount": len(updated_accounts),
            "unchangedCount": len(unchanged_accounts),
            "expiredCloudCount": len(expired_cloud_accounts),
            "unmatchedCloudCount": len(unmatched_cloud_accounts),
            "localWithoutCloudCount": len(local_without_cloud_accounts),
            "conflictCount": len(conflicts),
            "identityWarningCount": len(identity_warnings),
            "duplicateLocalAccountCount": duplicate_local_count,
            "malformedCloudItemCount": len(malformed_cloud_items),
            "updatedAccounts": updated_accounts,
            "unchangedAccounts": unchanged_accounts,
            "expiredCloudAccounts": expired_cloud_accounts,
            "unmatchedCloudAccounts": unmatched_cloud_accounts,
            "localWithoutCloudAccounts": local_without_cloud_accounts,
            "conflicts": conflicts,
            "identityWarnings": identity_warnings,
            "warnings": malformed_cloud_items,
            "summary": summary,
        }
        return report

    @staticmethod
    def _append_identity_warnings(
        warnings: list[dict[str, str]],
        local_account: dict[str, Any],
        cloud_item: dict[str, Any],
    ) -> None:
        user_account = str(local_account.get("userAccount") or "").strip()
        comparisons = [
            ("姓名", str(local_account.get("realName") or "").strip(), str(cloud_item.get("realName") or "").strip()),
            ("部门", str(local_account.get("department") or "").strip(), str(cloud_item.get("department") or "").strip()),
        ]
        for label, local_value, cloud_value in comparisons:
            if local_value and cloud_value and local_value.casefold() != cloud_value.casefold():
                warnings.append(
                    {
                        "userAccount": user_account,
                        "field": label,
                        "localValue": local_value,
                        "cloudValue": cloud_value,
                        "message": f"{label}不一致，已保留本地值。",
                    }
                )

    def _compute_next_auto_sync(
        self,
        *,
        polling_schedule: dict[str, Any],
        lead_minutes: int,
        last_auto_slot_key: str,
    ) -> dict[str, Any] | None:
        raw_slots = polling_schedule.get("slots")
        slots = [slot for slot in raw_slots or [] if isinstance(slot, dict)]
        if not slots:
            return None
        allow_weekends = bool(polling_schedule.get("allowWeekends", False))
        now = datetime.now()
        now_epoch = int(now.timestamp())

        for day_offset in range(15):
            day = now.date() + timedelta(days=day_offset)
            if not allow_weekends and datetime.combine(day, dt_time()).weekday() > 4:
                continue
            for slot in slots:
                try:
                    hour = int(slot.get("hour"))
                    minute = int(slot.get("minute"))
                except (TypeError, ValueError):
                    raw_time = str(slot.get("time") or "")
                    try:
                        hour, minute = (int(part) for part in raw_time.split(":", 1))
                    except (TypeError, ValueError):
                        continue
                base_at = int(datetime.combine(day, dt_time(hour, minute)).timestamp())
                if base_at <= now_epoch:
                    continue
                slot_key = f"{slot.get('key') or 'slot'}:{base_at}"
                if slot_key == last_auto_slot_key:
                    continue
                sync_at = base_at - lead_minutes * 60
                return {
                    "slotKey": slot_key,
                    "syncAt": max(sync_at, now_epoch) if sync_at <= now_epoch else sync_at,
                    "due": sync_at <= now_epoch,
                    "slotText": f"{day:%Y-%m-%d} {hour:02d}:{minute:02d}",
                }
        return None

    @staticmethod
    def _slot_base_at(slot: dict[str, Any]) -> int | None:
        raw_base_at = slot.get("baseAt")
        if isinstance(raw_base_at, (int, float)):
            return int(raw_base_at)
        scheduled_at = slot.get("scheduledAt")
        if isinstance(scheduled_at, (int, float)):
            return int(scheduled_at) - int(slot.get("offsetMinutes") or 0) * 60
        return None

    def _save_config(self, payload: dict[str, Any]) -> None:
        with self._config_lock:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.config_path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(self.config_path)
