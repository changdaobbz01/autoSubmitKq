from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import uuid
from datetime import datetime, time as dt_time, timedelta
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from runtime_paths import APP_ROOT, BUNDLE_ROOT, IS_FROZEN

ROOT_DIR = (BUNDLE_ROOT / "rebuild_login") if IS_FROZEN else Path(__file__).resolve().parent
PARENT_DIR = APP_ROOT
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))

from attendance_auth_client import (
    AttendanceAuthClient,
    AuthError,
    BASE_API_URL,
    BASE_PAGE_URL,
    DEFAULT_CAPTCHA_PATH,
    SessionData,
)
from account_registry import AccountRegistry
from normal_clock_debug import DEFAULT_LATITUDE, DEFAULT_LONGITUDE, run_normal_clock_check
from wecom_bot_notifier import WeComBotNotifier

WEB_DIR = ROOT_DIR / "web"
POLLING_STATE_PATH = PARENT_DIR / ".attendance_auth" / "clock_polling_state.json"
DEFAULT_POLLING_SLOTS = [
    {
        "key": "slot-1",
        "name": "打卡时点 1",
        "hour": 8,
        "minute": 0,
    },
    {
        "key": "slot-2",
        "name": "打卡时点 2",
        "hour": 18,
        "minute": 30,
    },
]
DEFAULT_POLLING_EXECUTION_MODE = "dry-run"
POLLING_EXECUTION_MODE_VALUES = {DEFAULT_POLLING_EXECUTION_MODE, "submit"}
LEGACY_POLLING_SLOT_LABELS = {
    "weekday-morning": "工作日上午 08:00 dry-run",
    "weekday-evening": "工作日下午 18:30 dry-run",
}

HOME_MENU_GROUPS = [
    {
        "id": "attendance",
        "title": "考勤服务",
        "children": [
            {
                "id": "clock",
                "title": "正常打卡",
                "route": "/clock",
                "iconLabel": "01",
                "apiHints": [
                    "POST /moSignRecord/createSignRecord",
                    "GET /moSignRecord/getSignCord",
                    "POST /adPhoneSignrecordDic/getSignAddress",
                ],
            },
            {
                "id": "field-clock",
                "title": "外场打卡",
                "route": "/field-clock",
                "iconLabel": "02",
                "apiHints": [
                    "POST /moSignRecord/createOutOffice",
                    "POST /attendanceImage/searchModel",
                ],
            },
            {
                "id": "resign-apply",
                "title": "补签申请",
                "route": "/resign-apply",
                "iconLabel": "03",
                "apiHints": [
                    "POST /moRequest/createRecoverSign",
                    "GET /moRequest/getMyErrorAttend",
                ],
            },
            {
                "id": "day-off",
                "title": "请假申请",
                "route": "/day-off",
                "iconLabel": "04",
                "apiHints": [
                    "POST /moRequest/createAfkr",
                    "GET /moRequest/getRequestUsers",
                ],
            },
            {
                "id": "attendance-calendar",
                "title": "考勤日历",
                "route": "/attendance-calendar",
                "iconLabel": "05",
                "apiHints": [
                    "POST /adAttendStat/getAdAttendStatDetail",
                    "POST /adAttendStat/getAdStatisticsByTimeQuantumNew",
                ],
            },
            {
                "id": "my-apply",
                "title": "我的发起",
                "route": "/my-apply",
                "iconLabel": "06",
                "apiHints": [
                    "GET /moRequest/getMyRequest",
                ],
            },
        ],
    },
    {
        "id": "manage",
        "title": "管理服务",
        "children": [
            {
                "id": "approval",
                "title": "申请审批",
                "route": "/approval",
                "iconLabel": "07",
                "badgeKey": "unapprovedCount",
                "apiHints": [
                    "GET /moRequest/getRequestUsers",
                    "GET /moRequest/getMyApprove",
                    "POST /moRequest/updateApprove",
                ],
            },
            {
                "id": "attendance-statistics",
                "title": "考勤统计",
                "route": "/attendance-statistics",
                "iconLabel": "09",
                "apiHints": [
                    "POST /adAttendStat/getAdStatisticsByTimeQuantum",
                    "POST /adAttendStat/getAdStatisticsByTimeQuantumNew",
                ],
            },
            {
                "id": "privacy-policy",
                "title": "隐私政策",
                "route": "/privacy-policy",
                "iconLabel": "12",
                "apiHints": [
                    "静态页面 /privacy-policy",
                ],
            },
            {
                "id": "change-pwd",
                "title": "修改密码",
                "route": "/change-pwd",
                "iconLabel": "10",
                "apiHints": [
                    "POST /adUser/user/resetPasswordNewV1",
                ],
            },
            {
                "id": "logout",
                "title": "退出登录",
                "action": "logout",
                "iconLabel": "11",
                "apiHints": [
                    "POST /adUser/user/loginOut",
                ],
            },
        ],
    },
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="掌上考勤重建版本地代理")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def format_timestamp(epoch: int | None) -> str:
    if not epoch:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))


def build_session_payload(session: SessionData) -> dict[str, Any]:
    return {
        "cached": True,
        "reusable": True,
        "userAccount": session.user_account,
        "userName": session.user_name,
        "realName": session.real_name,
        "department": session.department,
        "tokenExp": session.token_exp,
        "tokenExpText": format_timestamp(session.token_exp),
        "savedAt": session.saved_at,
        "savedAtText": format_timestamp(session.saved_at),
        "userInfo": session.user_info,
    }


def parse_list_payload(payload: dict[str, Any], empty_codes: set[str] | None = None) -> tuple[list[Any], str]:
    empty_codes = empty_codes or set()
    ret_code = str(payload.get("retCode") or "")
    ret_msg = str(payload.get("retMsg") or "")
    ret_content = payload.get("retContent")
    if ret_code == "200" and isinstance(ret_content, list):
        return ret_content, ret_msg
    if ret_code in empty_codes:
        return [], ret_msg
    return [], ret_msg or "接口返回异常"


def build_polling_days_text(allow_weekends: bool) -> str:
    return "周一至周日" if allow_weekends else "周一至周五"


def normalize_polling_execution_mode(value: Any) -> str:
    return "submit" if str(value or "").strip().lower() == "submit" else DEFAULT_POLLING_EXECUTION_MODE


def validate_polling_execution_mode(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw not in POLLING_EXECUTION_MODE_VALUES:
        raise ValueError("轮询模式只能是 dry-run 或 submit。")
    return raw


def build_polling_execution_mode_label(execution_mode: str) -> str:
    return "真实提交" if normalize_polling_execution_mode(execution_mode) == "submit" else "仅调测"


def build_polling_slot_label(
    slot: dict[str, Any],
    execution_mode: str = DEFAULT_POLLING_EXECUTION_MODE,
) -> str:
    mode_suffix = "真实提交" if normalize_polling_execution_mode(execution_mode) == "submit" else "dry-run"
    return f"{slot['name']} {slot['hour']:02d}:{slot['minute']:02d} {mode_suffix}"


def _clone_default_polling_slots() -> list[dict[str, Any]]:
    return [dict(slot) for slot in DEFAULT_POLLING_SLOTS]


def parse_polling_time_text(value: str) -> tuple[int, int] | None:
    raw = str(value or "").strip()
    if not raw or ":" not in raw:
        return None
    hour_text, minute_text = raw.split(":", 1)
    if not hour_text.isdigit() or not minute_text.isdigit():
        return None
    hour = int(hour_text)
    minute = int(minute_text)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def normalize_polling_slots(raw_slots: Any) -> list[dict[str, Any]]:
    candidates: list[tuple[int, int]] = []
    if isinstance(raw_slots, list):
        for item in raw_slots[:2]:
            hour: int | None = None
            minute: int | None = None
            if isinstance(item, dict):
                if isinstance(item.get("hour"), int) and isinstance(item.get("minute"), int):
                    hour = int(item["hour"])
                    minute = int(item["minute"])
                elif isinstance(item.get("time"), str):
                    parsed = parse_polling_time_text(item["time"])
                    if parsed:
                        hour, minute = parsed
            elif isinstance(item, str):
                parsed = parse_polling_time_text(item)
                if parsed:
                    hour, minute = parsed
            if hour is None or minute is None or not (0 <= hour <= 23 and 0 <= minute <= 59):
                return _clone_default_polling_slots()
            candidates.append((hour, minute))
    if len(candidates) != 2:
        return _clone_default_polling_slots()
    unique_candidates = sorted(set(candidates))
    if len(unique_candidates) != 2:
        return _clone_default_polling_slots()
    return [
        {
            "key": f"slot-{index + 1}",
            "name": f"打卡时点 {index + 1}",
            "hour": hour,
            "minute": minute,
        }
        for index, (hour, minute) in enumerate(unique_candidates)
    ]


def build_polling_schedule_text(allow_weekends: bool, slots: list[dict[str, Any]]) -> str:
    times_text = " / ".join(f"{slot['hour']:02d}:{slot['minute']:02d}" for slot in slots)
    return f"{build_polling_days_text(allow_weekends)} {times_text}"


def compute_next_polling_slot(
    now: datetime | None = None,
    *,
    allow_weekends: bool = False,
    slots: list[dict[str, Any]] | None = None,
    execution_mode: str = DEFAULT_POLLING_EXECUTION_MODE,
) -> tuple[int, dict[str, Any]]:
    now = now or datetime.now()
    slots = normalize_polling_slots(slots)
    for day_offset in range(14):
        day = now.date() + timedelta(days=day_offset)
        day_dt = datetime.combine(day, dt_time(0, 0))
        if not allow_weekends and day_dt.weekday() > 4:
            continue
        for slot in slots:
            candidate = datetime.combine(day, dt_time(slot["hour"], slot["minute"]))
            if candidate > now:
                slot_payload = dict(slot)
                slot_payload["label"] = build_polling_slot_label(slot_payload, execution_mode)
                return int(candidate.timestamp()), slot_payload

    fallback_slot = dict(slots[0])
    fallback_day = now.date() + timedelta(days=1)
    while not allow_weekends and datetime.combine(fallback_day, dt_time(0, 0)).weekday() > 4:
        fallback_day += timedelta(days=1)
    fallback = datetime.combine(fallback_day, dt_time(fallback_slot["hour"], fallback_slot["minute"]))
    fallback_slot["label"] = build_polling_slot_label(fallback_slot, execution_mode)
    return int(fallback.timestamp()), fallback_slot


def build_scheduler_session_payload(session: SessionData | None) -> dict[str, Any]:
    if session is None:
        return {
            "cached": False,
            "reusable": False,
            "userAccount": "",
            "tokenExp": None,
            "tokenExpText": "",
        }
    return {
        "cached": True,
        "reusable": True,
        "userAccount": session.user_account,
        "tokenExp": session.token_exp,
        "tokenExpText": format_timestamp(session.token_exp),
    }


def shrink_clock_check_payload(result: dict[str, Any]) -> dict[str, Any]:
    today_records = result.get("todayRecords", {}).get("retContent")
    record_list = today_records if isinstance(today_records, list) else []
    first_records = [
        {
            "signtime": item.get("signtime"),
            "signtype": item.get("signtype"),
            "signaddress": item.get("signaddress"),
        }
        for item in record_list[:3]
        if isinstance(item, dict)
    ]
    face_content = result.get("faceModel", {}).get("response", {}).get("retContent")
    face_image_path = face_content.get("imagePath") if isinstance(face_content, dict) else ""
    configured_photo = result.get("configuredPhoto") if isinstance(result.get("configuredPhoto"), dict) else {}
    return {
        "mode": result.get("mode"),
        "h5Gate": result.get("h5Gate"),
        "location": {
            "longitude": result.get("location", {}).get("longitude"),
            "latitude": result.get("location", {}).get("latitude"),
            "rangeAddress": result.get("location", {}).get("rangeAddress"),
            "inRange": result.get("location", {}).get("inRange"),
        },
        "faceModel": {
            "configured": result.get("faceModel", {}).get("configured"),
            "imagePath": face_image_path,
        },
        "todayRecordCount": len(record_list),
        "todayRecordPreview": first_records,
        "configuredPhoto": {
            "status": configured_photo.get("status"),
            "statusText": configured_photo.get("statusText"),
            "path": configured_photo.get("path"),
        },
        "wouldSubmit": result.get("wouldSubmit"),
    }


def summarize_clock_check(result: dict[str, Any]) -> str:
    in_range = bool(result.get("location", {}).get("inRange"))
    face_ready = bool(result.get("faceModel", {}).get("configured"))
    today_records = result.get("todayRecords", {}).get("retContent")
    record_count = len(today_records) if isinstance(today_records, list) else 0
    range_address = result.get("location", {}).get("rangeAddress") or "未解析到标准地址"
    configured_photo = result.get("configuredPhoto") if isinstance(result.get("configuredPhoto"), dict) else {}
    parts = [
        configured_photo.get("statusText") or "未配置照片",
        "已录入脸模" if face_ready else "未录入脸模",
        "位于考勤范围内" if in_range else "不在考勤范围内",
        f"今日记录 {record_count} 条",
        range_address,
    ]
    return " / ".join(parts)


def is_clock_submit_success(result: dict[str, Any]) -> bool:
    submit_response = result.get("submitResponse") if isinstance(result.get("submitResponse"), dict) else {}
    return bool(submit_response.get("isSuccess")) and str(submit_response.get("retCode") or "") == "200"


def summarize_clock_submit(result: dict[str, Any]) -> str:
    submit_response = result.get("submitResponse") if isinstance(result.get("submitResponse"), dict) else {}
    ret_code = str(submit_response.get("retCode") or "-")
    ret_msg = str(submit_response.get("retMsg") or "-")
    range_address = result.get("location", {}).get("rangeAddress") or "未解析到标准地址"
    if is_clock_submit_success(result):
        return f"真实打卡成功 / {range_address} / {ret_msg}"
    return f"真实打卡失败 / {ret_code} / {ret_msg} / {range_address}"


def try_recover_gbk_mojibake(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    try:
        repaired = value.encode("gbk").decode("utf-8")
    except UnicodeError:
        return value
    return repaired or value


def build_polling_run_summary(details: dict[str, Any]) -> str:
    total_count = int(details.get("totalCount") or 0)
    success_count = int(details.get("successCount") or 0)
    skipped_count = int(details.get("skippedCount") or 0)
    failed_count = int(details.get("failedCount") or 0)
    return f"账号 {total_count} 个 / 成功 {success_count} / 跳过 {skipped_count} / 失败 {failed_count}"


def normalize_persisted_run_record(run: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(run)
    execution_mode = normalize_polling_execution_mode(normalized.get("executionMode"))
    normalized["executionMode"] = execution_mode
    normalized["executionModeLabel"] = build_polling_execution_mode_label(execution_mode)
    slot_key = str(normalized.get("slotKey") or "")
    if slot_key == "manual-test":
        normalized["slotLabel"] = "手动测试 dry-run"
    elif slot_key in LEGACY_POLLING_SLOT_LABELS:
        normalized["slotLabel"] = LEGACY_POLLING_SLOT_LABELS[slot_key]
    elif isinstance(normalized.get("slotLabel"), str):
        normalized["slotLabel"] = try_recover_gbk_mojibake(normalized.get("slotLabel"))

    details = normalized.get("details")
    if isinstance(details, dict) and any(
        key in details for key in ("totalCount", "successCount", "skippedCount", "failedCount")
    ):
        normalized["summary"] = build_polling_run_summary(details)
    elif isinstance(normalized.get("summary"), str):
        normalized["summary"] = try_recover_gbk_mojibake(normalized.get("summary"))

    notification = normalized.get("notification")
    if isinstance(notification, dict):
        fixed_notification = dict(notification)
        if isinstance(fixed_notification.get("statusText"), str):
            fixed_notification["statusText"] = try_recover_gbk_mojibake(fixed_notification.get("statusText"))
        normalized["notification"] = fixed_notification

    return normalized


class ClockDryRunScheduler:
    def __init__(
        self,
        account_registry: AccountRegistry,
        notifier: WeComBotNotifier | None = None,
        state_path: Path = POLLING_STATE_PATH,
    ) -> None:
        self.account_registry = account_registry
        self.notifier = notifier
        self.state_path = state_path
        self._lock = threading.Lock()
        self._wake_event = threading.Event()
        self._stop_event = threading.Event()

        saved = self._load_state()
        self._enabled = bool(saved.get("enabled", False))
        self._allow_weekends = bool(saved.get("allowWeekends", False))
        self._slots = normalize_polling_slots(saved.get("slots"))
        self._execution_mode = normalize_polling_execution_mode(saved.get("executionMode"))
        raw_last_run = saved.get("lastRun") if isinstance(saved.get("lastRun"), dict) else None
        self._last_run = normalize_persisted_run_record(raw_last_run) if raw_last_run else None
        raw_recent = saved.get("recentRuns")
        saved_recent_runs = raw_recent[:8] if isinstance(raw_recent, list) else []
        self._recent_runs = [
            normalize_persisted_run_record(item) for item in saved_recent_runs if isinstance(item, dict)
        ]
        self._active_run: dict[str, Any] | None = None
        self._next_run_at: int | None = None
        self._next_slot: dict[str, Any] | None = None

        if self._enabled:
            self._set_next_run_locked()

        if (
            self._last_run != raw_last_run
            or self._recent_runs != saved_recent_runs
            or saved.get("slots") != self._slots
            or saved.get("executionMode") != self._execution_mode
        ):
            self._persist_locked()

        self._thread = threading.Thread(
            target=self._run_loop,
            name="ClockDryRunScheduler",
            daemon=True,
        )
        self._thread.start()

    def start(self) -> dict[str, Any]:
        with self._lock:
            self._enabled = True
            self._set_next_run_locked()
            self._persist_locked()
        self._wake_event.set()
        return self.get_status_payload()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._enabled = False
            self._next_run_at = None
            self._next_slot = None
            self._persist_locked()
        self._wake_event.set()
        return self.get_status_payload()

    def set_allow_weekends(self, allow_weekends: bool) -> dict[str, Any]:
        with self._lock:
            self._allow_weekends = bool(allow_weekends)
            if self._enabled:
                self._set_next_run_locked()
            self._persist_locked()
        self._wake_event.set()
        return self.get_status_payload()

    def set_time_slots(self, raw_slots: list[Any]) -> dict[str, Any]:
        if len(raw_slots) != 2:
            raise ValueError("请输入两个有效的打卡时间，格式为 HH:MM。")
        parsed_times: list[tuple[int, int]] = []
        for item in raw_slots:
            parsed = parse_polling_time_text(str(item))
            if parsed is None:
                raise ValueError("请输入两个有效的打卡时间，格式为 HH:MM。")
            parsed_times.append(parsed)
        if len(set(parsed_times)) != 2:
            raise ValueError("两个打卡时间不能相同。")
        slots = normalize_polling_slots([f"{hour:02d}:{minute:02d}" for hour, minute in parsed_times])
        if len(slots) != 2:
            raise ValueError("请输入两个有效的打卡时间，格式为 HH:MM。")
        with self._lock:
            self._slots = slots
            if self._enabled:
                self._set_next_run_locked()
            self._persist_locked()
        self._wake_event.set()
        return self.get_status_payload()

    def set_execution_mode(self, execution_mode: str) -> dict[str, Any]:
        mode = validate_polling_execution_mode(execution_mode)
        with self._lock:
            self._execution_mode = mode
            if self._enabled:
                self._set_next_run_locked()
            self._persist_locked()
        self._wake_event.set()
        return self.get_status_payload()

    def trigger_test(self) -> dict[str, Any]:
        worker: threading.Thread | None = None
        with self._lock:
            if self._active_run is None:
                worker = self._activate_run_locked(
                    self._build_run_payload(
                        "manual-test",
                        "手动测试 dry-run",
                        trigger="manual",
                        execution_mode=DEFAULT_POLLING_EXECUTION_MODE,
                    )
                )
        if worker is not None:
            worker.start()
        return self.get_status_payload()

    def shutdown(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        self._thread.join(timeout=5)

    def get_status_payload(self) -> dict[str, Any]:
        with self._lock:
            allow_weekends = self._allow_weekends
            slots = [dict(slot) for slot in self._slots]
            execution_mode = self._execution_mode
            preview_run_at, preview_slot = compute_next_polling_slot(
                allow_weekends=allow_weekends,
                slots=slots,
                execution_mode=execution_mode,
            )
            next_run_at = self._next_run_at if self._enabled else preview_run_at
            next_slot = self._next_slot if self._enabled and self._next_slot else preview_slot
            active_run = dict(self._active_run) if self._active_run else None
            last_run = dict(self._last_run) if self._last_run else None
            recent_runs = [dict(item) for item in self._recent_runs[:5]]
            enabled = self._enabled

        registry_summary = self.account_registry.summarize_registry()
        return {
            "enabled": enabled,
            "allowWeekends": allow_weekends,
            "executionMode": execution_mode,
            "executionModeLabel": build_polling_execution_mode_label(execution_mode),
            "running": active_run is not None,
            "scheduleText": build_polling_schedule_text(allow_weekends, slots),
            "slots": [
                {
                    "key": slot["key"],
                    "name": slot["name"],
                    "label": build_polling_slot_label(slot, execution_mode),
                    "time": f"{slot['hour']:02d}:{slot['minute']:02d}",
                    "weekdays": build_polling_days_text(allow_weekends),
                }
                for slot in slots
            ],
            "mode": "armed" if enabled else "preview",
            "nextRunAt": next_run_at,
            "nextRunAtText": format_timestamp(next_run_at),
            "nextRunLabel": next_slot["label"] if next_slot else "",
            "activeRun": active_run,
            "lastRun": last_run,
            "recentRuns": recent_runs,
            "locationProfile": {
                "longitude": DEFAULT_LONGITUDE,
                "latitude": DEFAULT_LATITUDE,
                "expectedAddress": "武汉-航天花园302栋2单元801室",
            },
            "accountsOverview": {
                "totalCount": registry_summary["totalCount"],
                "enabledCount": registry_summary["enabledCount"],
                "reusableCount": registry_summary["reusableCount"],
                "needsCaptchaLoginCount": registry_summary["needsCaptchaLoginCount"],
                "expiredCount": registry_summary["expiredCount"],
                "missingTokenCount": registry_summary["missingTokenCount"],
                "photoReadyCount": registry_summary["photoReadyCount"],
                "photoProblemCount": registry_summary["photoProblemCount"],
            },
            "accounts": registry_summary["accounts"],
        }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            worker: threading.Thread | None = None
            with self._lock:
                if self._enabled and self._active_run is None:
                    if self._next_run_at is None or self._next_slot is None:
                        self._set_next_run_locked()
                        self._persist_locked()
                    now_epoch = int(time.time())
                    if self._next_run_at and now_epoch >= self._next_run_at and self._next_slot:
                        worker = self._activate_run_locked(
                            self._build_run_payload(
                                self._next_slot["key"],
                                self._next_slot["label"],
                                trigger="schedule",
                                execution_mode=self._execution_mode,
                            )
                        )

            if worker is not None:
                worker.start()
                continue

            self._wake_event.wait(5)
            self._wake_event.clear()

    def _build_run_payload(
        self,
        slot_key: str,
        slot_label: str,
        *,
        trigger: str,
        execution_mode: str = DEFAULT_POLLING_EXECUTION_MODE,
    ) -> dict[str, Any]:
        started_at = int(time.time())
        normalized_mode = normalize_polling_execution_mode(execution_mode)
        return {
            "slotKey": slot_key,
            "slotLabel": slot_label,
            "trigger": trigger,
            "executionMode": normalized_mode,
            "executionModeLabel": build_polling_execution_mode_label(normalized_mode),
            "startedAt": started_at,
            "startedAtText": format_timestamp(started_at),
        }

    def _activate_run_locked(self, due_run: dict[str, Any]) -> threading.Thread:
        self._active_run = dict(due_run)
        self._persist_locked()
        return threading.Thread(
            target=self._execute_run,
            args=(dict(due_run),),
            name=f"ClockDryRun-{due_run['slotKey']}",
            daemon=True,
        )

    def _execute_run(self, due_run: dict[str, Any]) -> None:
        started_at = int(due_run["startedAt"])
        started_monotonic = time.monotonic()
        execution_mode = normalize_polling_execution_mode(due_run.get("executionMode"))
        ok = True
        account_runs: list[dict[str, Any]] = []
        success_count = 0
        skipped_count = 0
        failed_count = 0
        skipped_expired_count = 0
        skipped_missing_count = 0
        skipped_photo_count = 0

        for account in self.account_registry.get_enabled_accounts(include_sensitive=True):
            user_account = account["userAccount"]
            client = self.account_registry.build_auth_client(account)
            session_state = account.get("session") or {}
            photo_state = account.get("photo") if isinstance(account.get("photo"), dict) else {}
            try:
                if not session_state.get("reusable"):
                    skipped_count += 1
                    if session_state.get("status") == "expired":
                        skipped_expired_count += 1
                        summary = "token 已过期，已跳过本次轮询"
                        skip_reason = "expired"
                    else:
                        skipped_missing_count += 1
                        summary = "没有可复用 token，已跳过本次轮询"
                        skip_reason = "missing"
                    account_run = {
                        "userAccount": user_account,
                        "realName": account.get("realName") or "",
                        "ok": False,
                        "skipped": True,
                        "skipReason": skip_reason,
                        "summary": summary,
                        "details": {"mode": execution_mode, "photo": photo_state},
                    }
                elif not photo_state.get("exists"):
                    skipped_count += 1
                    skipped_photo_count += 1
                    account_run = {
                        "userAccount": user_account,
                        "realName": account.get("realName") or "",
                        "ok": False,
                        "skipped": True,
                        "skipReason": "photo",
                        "summary": f'{photo_state.get("statusText") or "未配置照片"}，已跳过本次轮询',
                        "details": {"mode": execution_mode, "photo": photo_state},
                    }
                else:
                    submit_mode = execution_mode == "submit"
                    image_path = (
                        Path(str(photo_state.get("path") or account.get("photoPath") or "")).expanduser()
                        if submit_mode
                        else None
                    )
                    result = run_normal_clock_check(
                        client,
                        longitude=DEFAULT_LONGITUDE,
                        latitude=DEFAULT_LATITUDE,
                        image=image_path,
                        submit=submit_mode,
                    )
                    result["configuredPhoto"] = photo_state
                    if submit_mode:
                        submit_ok = is_clock_submit_success(result)
                        account_details = shrink_clock_check_payload(result)
                        account_details.update(
                            {
                                "mode": execution_mode,
                                "submitResponse": result.get("submitResponse"),
                                "productionWritePerformed": bool(result.get("productionWritePerformed")),
                                "photo": photo_state,
                            }
                        )

                        notification_payload: dict[str, Any] | None = None
                        if self.notifier is not None:
                            try:
                                notification_payload = self.notifier.notify_submit(
                                    user_account=user_account,
                                    real_name=str(account.get("realName") or ""),
                                    result=result,
                                    photo_state=photo_state,
                                    image_source="account-photo",
                                )
                            except Exception as exc:  # noqa: BLE001
                                notification_payload = {
                                    "attempted": True,
                                    "sent": False,
                                    "purpose": "submit",
                                    "statusText": f"企业微信群通知发送失败：{exc}",
                                    "error": str(exc),
                                }
                        if notification_payload is not None:
                            account_details["notification"] = notification_payload

                        if submit_ok:
                            success_count += 1
                        else:
                            ok = False
                            failed_count += 1

                        account_run = {
                            "userAccount": user_account,
                            "realName": account.get("realName") or "",
                            "ok": submit_ok,
                            "skipped": False,
                            "summary": summarize_clock_submit(result),
                            "details": account_details,
                        }
                    else:
                        success_count += 1
                        account_details = shrink_clock_check_payload(result)
                        account_details["mode"] = execution_mode
                        account_details["photo"] = photo_state
                        account_run = {
                            "userAccount": user_account,
                            "realName": account.get("realName") or "",
                            "ok": True,
                            "skipped": False,
                            "summary": summarize_clock_check(result),
                            "details": account_details,
                        }
            except Exception as exc:  # noqa: BLE001
                ok = False
                failed_count += 1
                account_run = {
                    "userAccount": user_account,
                    "realName": account.get("realName") or "",
                    "ok": False,
                    "skipped": False,
                    "summary": str(exc) or "dry-run 执行失败",
                    "details": {"mode": execution_mode, "photo": photo_state},
                    "error": str(exc),
                }
            self.account_registry.update_last_run(user_account, account_run)
            account_runs.append(account_run)

        finished_at = int(time.time())
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        total_count = len(account_runs)
        summary = build_polling_run_summary(
            {
                "totalCount": total_count,
                "successCount": success_count,
                "skippedCount": skipped_count,
                "failedCount": failed_count,
            }
        )
        run_record: dict[str, Any] = {
            "slotKey": due_run["slotKey"],
            "slotLabel": due_run["slotLabel"],
            "trigger": due_run.get("trigger") or "schedule",
            "executionMode": execution_mode,
            "executionModeLabel": build_polling_execution_mode_label(execution_mode),
            "startedAt": started_at,
            "startedAtText": format_timestamp(started_at),
            "finishedAt": finished_at,
            "finishedAtText": format_timestamp(finished_at),
            "durationMs": duration_ms,
            "ok": ok,
            "summary": summary,
            "details": {
                "mode": execution_mode,
                "totalCount": total_count,
                "successCount": success_count,
                "skippedCount": skipped_count,
                "failedCount": failed_count,
                "skippedExpiredCount": skipped_expired_count,
                "skippedMissingTokenCount": skipped_missing_count,
                "skippedPhotoCount": skipped_photo_count,
                "accounts": account_runs,
            },
        }

        if self.notifier is not None:
            try:
                run_record["notification"] = self.notifier.notify_polling_run(run_record)
            except Exception as exc:  # noqa: BLE001
                run_record["notification"] = {
                    "attempted": True,
                    "sent": False,
                    "purpose": "polling",
                    "statusText": f"企业微信群通知发送失败：{exc}",
                    "error": str(exc),
                }

        with self._lock:
            self._last_run = run_record
            self._recent_runs = [run_record, *self._recent_runs][:8]
            self._active_run = None
            if self._enabled:
                self._set_next_run_locked(datetime.fromtimestamp(finished_at) + timedelta(seconds=1))
            else:
                self._next_run_at = None
                self._next_slot = None
            self._persist_locked()

        self._wake_event.set()

    def _set_next_run_locked(self, now: datetime | None = None) -> None:
        next_run_at, next_slot = compute_next_polling_slot(
            now,
            allow_weekends=self._allow_weekends,
            slots=self._slots,
            execution_mode=self._execution_mode,
        )
        self._next_run_at = next_run_at
        self._next_slot = dict(next_slot)

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _persist_locked(self) -> None:
        payload = {
            "enabled": self._enabled,
            "allowWeekends": self._allow_weekends,
            "executionMode": self._execution_mode,
            "slots": self._slots,
            "lastRun": self._last_run,
            "recentRuns": self._recent_runs,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)


class RebuildLoginHandler(SimpleHTTPRequestHandler):
    server_version = "AttendanceRebuild/3.0"

    def __init__(self, *args: Any, directory: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    @property
    def auth_client(self) -> AttendanceAuthClient:
        return self.server.auth_client  # type: ignore[attr-defined]

    @property
    def polling_scheduler(self) -> ClockDryRunScheduler:
        return self.server.polling_scheduler  # type: ignore[attr-defined]

    @property
    def account_registry(self) -> AccountRegistry:
        return self.server.account_registry  # type: ignore[attr-defined]

    @property
    def notifier(self) -> WeComBotNotifier:
        return self.server.notifier  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/config":
            self._write_json(
                {
                    "basePageUrl": BASE_PAGE_URL,
                    "baseApiUrl": BASE_API_URL,
                    "sessionPath": str(self.auth_client.session_store.path),
                    "notifyConfigPath": str(self.notifier.path),
                    "homeMenuGroups": HOME_MENU_GROUPS,
                }
            )
            return
        if parsed.path == "/api/notify-config":
            self._write_json(self.notifier.get_public_config())
            return
        if parsed.path == "/api/session":
            self._handle_get_session(parsed.query)
            return
        if parsed.path == "/api/captcha":
            self._handle_get_captcha()
            return
        if parsed.path == "/api/userinfo":
            self._handle_get_userinfo()
            return
        if parsed.path == "/api/dashboard":
            self._handle_get_dashboard()
            return
        if parsed.path == "/api/accounts":
            self._write_json(self.account_registry.summarize_registry())
            return
        if parsed.path == "/api/accounts/captcha":
            self._handle_get_account_captcha(parsed.query)
            return
        if parsed.path == "/api/clock-polling/status":
            self._write_json(self.polling_scheduler.get_status_payload())
            return
        if parsed.path in {"/", "/index.html"}:
            self.path = "/index.html"
        elif not (WEB_DIR / parsed.path.lstrip("/")).exists():
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/login":
            self._handle_post_login()
            return
        if parsed.path == "/api/logout":
            self._handle_post_logout()
            return
        if parsed.path == "/api/accounts/import":
            self._handle_post_accounts_import()
            return
        if parsed.path == "/api/accounts/login":
            self._handle_post_account_login()
            return
        if parsed.path == "/api/accounts/toggle":
            self._handle_post_accounts_toggle()
            return
        if parsed.path == "/api/accounts/remove":
            self._handle_post_accounts_remove()
            return
        if parsed.path == "/api/accounts/clear-tokens":
            self._handle_post_accounts_clear_tokens()
            return
        if parsed.path == "/api/notify-config":
            self._handle_post_notify_config()
            return
        if parsed.path == "/api/notify-test":
            self._handle_post_notify_test()
            return
        if parsed.path == "/api/clock-polling/start":
            self._write_json(self.polling_scheduler.start())
            return
        if parsed.path == "/api/clock-polling/weekends":
            self._handle_post_clock_weekends()
            return
        if parsed.path == "/api/clock-polling/mode":
            self._handle_post_clock_mode()
            return
        if parsed.path == "/api/clock-polling/times":
            self._handle_post_clock_times()
            return
        if parsed.path == "/api/clock-polling/test":
            self._write_json(self.polling_scheduler.trigger_test())
            return
        if parsed.path == "/api/clock-polling/submit":
            self._handle_post_clock_submit()
            return
        if parsed.path == "/api/clock-polling/stop":
            self._write_json(self.polling_scheduler.stop())
            return
        self._write_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle_get_session(self, query: str) -> None:
        params = parse_qs(query)
        validate = params.get("validate", ["0"])[0] == "1"
        session = self.auth_client.get_cached_session(validate_with_server=validate)
        if session is None:
            self._write_json({"cached": False, "reusable": False})
            return
        self._write_json(build_session_payload(session))

    def _handle_get_captcha(self) -> None:
        challenge = self.auth_client.fetch_captcha()
        self.auth_client.write_captcha_png(challenge, DEFAULT_CAPTCHA_PATH)
        self._write_json(
            {
                "requestId": challenge.request_id,
                "imageDataUrl": challenge.data_url,
                "savedPath": str(DEFAULT_CAPTCHA_PATH),
            }
        )

    def _handle_get_account_captcha(self, query: str) -> None:
        params = parse_qs(query)
        user_account = str(params.get("userAccount", [""])[0]).strip()
        if not user_account:
            self._write_json({"error": "userAccount 为必填"}, status=HTTPStatus.BAD_REQUEST)
            return
        try:
            account = self.account_registry.get_account(user_account, include_sensitive=True)
            client = self.account_registry.build_auth_client(account)
            challenge = client.fetch_captcha()
        except ValueError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except AuthError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self._write_json(
            {
                "userAccount": user_account,
                "requestId": challenge.request_id,
                "imageDataUrl": challenge.data_url,
                "hasStoredPassword": bool(account.get("password")),
                "passwordMasked": account.get("passwordMasked") or "",
            }
        )

    def _handle_get_userinfo(self) -> None:
        session = self.auth_client.get_cached_session(validate_with_server=False)
        if session is None:
            self._write_json({"error": "No reusable session"}, status=HTTPStatus.UNAUTHORIZED)
            return
        try:
            payload = self.auth_client.get_user_info(session.token)
        except AuthError as exc:
            self.auth_client.session_store.clear()
            self._write_json({"error": str(exc)}, status=HTTPStatus.UNAUTHORIZED)
            return
        refreshed = self.auth_client.build_session(session.token, payload)
        self.auth_client.session_store.save(refreshed)
        self._write_json(payload)

    def _handle_get_dashboard(self) -> None:
        session = self.auth_client.get_cached_session(validate_with_server=False)
        if session is None:
            self._write_json({"error": "No reusable session"}, status=HTTPStatus.UNAUTHORIZED)
            return
        try:
            payload = self._build_dashboard_payload(session)
        except AuthError as exc:
            self.auth_client.session_store.clear()
            self._write_json({"error": str(exc)}, status=HTTPStatus.UNAUTHORIZED)
            return
        self._write_json(payload)

    def _handle_post_login(self) -> None:
        body = self._read_json()
        user_account = str(body.get("userAccount", "")).strip()
        password = str(body.get("password", "")).strip()
        verification_code = str(body.get("verificationCode", "")).strip()
        request_id = str(body.get("requestId", "")).strip()
        if not user_account or not password or not verification_code or not request_id:
            self._write_json(
                {"error": "userAccount、password、verificationCode、requestId 均为必填"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return
        try:
            login_payload = self.auth_client.login(
                user_account=user_account,
                password=password,
                verification_code=verification_code,
                request_id=request_id,
            )
            token = login_payload["retContent"]["token"]
            user_info_payload = self.auth_client.get_user_info(token)
            session = self.auth_client.build_session(token, user_info_payload)
            self.auth_client.session_store.save(session)
        except AuthError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._write_json({"loggedIn": True, **build_session_payload(session)})

    def _handle_post_logout(self) -> None:
        session = self.auth_client.get_cached_session(validate_with_server=False)
        logout_result: Any = None
        if session is not None and self.auth_client.is_session_reusable(session):
            try:
                logout_result = self.auth_client.logout(session.token)
            except AuthError as exc:
                logout_result = {"error": str(exc)}
        self.auth_client.session_store.clear()
        self._write_json({"cleared": True, "logoutResult": logout_result})

    def _handle_post_accounts_import(self) -> None:
        try:
            file_bytes = self._read_uploaded_file()
            payload = self.account_registry.import_xlsx(file_bytes)
        except ValueError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:  # noqa: BLE001
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._write_json({"importSummary": payload, "registry": self.account_registry.summarize_registry()})

    def _handle_post_account_login(self) -> None:
        body = self._read_json()
        user_account = str(body.get("userAccount", "")).strip()
        verification_code = str(body.get("verificationCode", "")).strip()
        request_id = str(body.get("requestId", "")).strip()
        password_override = str(body.get("password", "")).strip()

        if not user_account or not verification_code or not request_id:
            self._write_json(
                {"error": "userAccount、verificationCode、requestId 均为必填"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        try:
            account = self.account_registry.get_account(user_account, include_sensitive=True)
        except ValueError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        password = password_override or str(account.get("password") or "")
        if not password:
            self._write_json({"error": "该账号没有可用密码，请手动输入"}, status=HTTPStatus.BAD_REQUEST)
            return

        client = self.account_registry.build_auth_client(account)
        try:
            login_payload = client.login(
                user_account=user_account,
                password=password,
                verification_code=verification_code,
                request_id=request_id,
            )
            token = login_payload["retContent"]["token"]
            user_info_payload = client.get_user_info(token)
            session = client.build_session(token, user_info_payload)
            client.session_store.save(session)
            if password_override:
                self.account_registry.set_password(user_account, password_override)
        except AuthError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self._write_json(
            {
                "loggedIn": True,
                "userAccount": user_account,
                "session": build_session_payload(session),
                "account": self.account_registry.get_account(user_account),
                "registry": self.account_registry.summarize_registry(),
            }
        )

    def _handle_post_accounts_toggle(self) -> None:
        body = self._read_json()
        user_account = str(body.get("userAccount", "")).strip()
        enabled = bool(body.get("enabled", True))
        if not user_account:
            self._write_json({"error": "userAccount 为必填"}, status=HTTPStatus.BAD_REQUEST)
            return
        try:
            account = self.account_registry.set_enabled(user_account, enabled)
        except ValueError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._write_json({"updated": True, "account": account, "registry": self.account_registry.summarize_registry()})

    def _handle_post_accounts_remove(self) -> None:
        body = self._read_json()
        user_account = str(body.get("userAccount", "")).strip()
        if not user_account:
            self._write_json({"error": "userAccount 为必填"}, status=HTTPStatus.BAD_REQUEST)
            return
        self._write_json(self.account_registry.remove(user_account))

    def _handle_post_accounts_clear_tokens(self) -> None:
        result = self.account_registry.clear_all_tokens()
        self.auth_client.session_store.clear()
        self._write_json(result)

    def _handle_post_notify_config(self) -> None:
        body = self._read_json()
        try:
            payload = self.notifier.save_config(body)
        except ValueError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._write_json(payload)

    def _handle_post_notify_test(self) -> None:
        payload = self.notifier.send_test_message()
        self._write_json(payload)

    def _handle_post_clock_weekends(self) -> None:
        body = self._read_json()
        raw_allow_weekends = body.get("allowWeekends", False)
        if isinstance(raw_allow_weekends, str):
            allow_weekends = raw_allow_weekends.strip().lower() in {"1", "true", "yes", "on"}
        else:
            allow_weekends = bool(raw_allow_weekends)
        self._write_json(self.polling_scheduler.set_allow_weekends(allow_weekends))

    def _handle_post_clock_mode(self) -> None:
        body = self._read_json()
        raw_execution_mode = body.get("executionMode", body.get("mode", ""))
        try:
            payload = self.polling_scheduler.set_execution_mode(str(raw_execution_mode or ""))
        except ValueError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._write_json(payload)

    def _handle_post_clock_times(self) -> None:
        body = self._read_json()
        raw_times = body.get("times")
        if not isinstance(raw_times, list):
            self._write_json({"error": "times 必须是包含两个时间的数组。"}, status=HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = self.polling_scheduler.set_time_slots(raw_times)
        except ValueError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self._write_json(payload)

    def _handle_post_clock_submit(self) -> None:
        content_type = str(self.headers.get("Content-Type") or "")
        fields: dict[str, str] = {}
        files: dict[str, dict[str, Any]] = {}

        if "multipart/form-data" in content_type:
            try:
                fields, files = self._read_uploaded_form()
            except ValueError as exc:
                self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            user_account = str(fields.get("userAccount") or "").strip()
        else:
            body = self._read_json()
            user_account = str(body.get("userAccount", "")).strip()

        if not user_account:
            self._write_json({"error": "userAccount 不能为空"}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            account = self.account_registry.get_account(user_account, include_sensitive=True)
        except ValueError as exc:
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        session_state = account.get("session") or {}
        if not session_state.get("reusable"):
            self._write_json(
                {"error": f"{user_account} 当前没有可复用 token，请先刷新该账号的 token"},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        photo_state = account.get("photo") if isinstance(account.get("photo"), dict) else {}
        temp_image_path: Path | None = None
        image_path: Path | None = None
        image_source = "account-photo"

        if "image" in files:
            image_file = files["image"]
            original_name = str(image_file.get("filename") or "clock-image.png")
            suffix = Path(original_name).suffix or ".png"
            safe_suffix = suffix if len(suffix) <= 10 else ".png"
            upload_dir = PARENT_DIR / ".attendance_auth" / "temp_uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            temp_image_path = upload_dir / f"clock-submit-{uuid.uuid4().hex}{safe_suffix}"
            temp_image_path.write_bytes(image_file.get("content") or b"")
            image_path = temp_image_path
            image_source = "uploaded-file"
        else:
            if not photo_state.get("exists"):
                self._write_json(
                    {"error": f"{user_account} {photo_state.get('statusText') or '未配置照片'}"},
                    status=HTTPStatus.BAD_REQUEST,
                )
                return
            image_path = Path(str(photo_state.get("path") or account.get("photoPath") or "")).expanduser()

        client = self.account_registry.build_auth_client(account)
        try:
            result = run_normal_clock_check(
                client,
                longitude=DEFAULT_LONGITUDE,
                latitude=DEFAULT_LATITUDE,
                image=image_path,
                submit=True,
            )
            result["configuredPhoto"] = photo_state
        except (AuthError, Exception) as exc:  # noqa: BLE001
            self._write_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        finally:
            if temp_image_path is not None:
                try:
                    temp_image_path.unlink(missing_ok=True)
                except OSError:
                    pass

        submit_record = {
            "userAccount": user_account,
            "realName": account.get("realName") or "",
            "ok": bool(result.get("productionWritePerformed")),
            "skipped": False,
            "summary": "已触发真实打卡" if result.get("productionWritePerformed") else "真实打卡未成功提交",
            "details": {
                "mode": "submit",
                "productionWritePerformed": bool(result.get("productionWritePerformed")),
                "submitResponse": result.get("submitResponse"),
                "photo": photo_state,
                "imageSource": image_source,
            },
        }
        notification_payload: dict[str, Any] | None = None
        try:
            notification_payload = self.notifier.notify_submit(
                user_account=user_account,
                real_name=str(account.get("realName") or ""),
                result=result,
                photo_state=photo_state,
                image_source=image_source,
            )
        except Exception as exc:  # noqa: BLE001
            notification_payload = {
                "attempted": True,
                "sent": False,
                "purpose": "submit",
                "statusText": f"企业微信群通知发送失败：{exc}",
                "error": str(exc),
            }
        if notification_payload is not None:
            submit_record["notification"] = notification_payload
        self.account_registry.update_last_run(user_account, submit_record)

        self._write_json(
            {
                "submitted": True,
                "userAccount": user_account,
                "mode": "submit",
                "imageSource": image_source,
                "photo": photo_state,
                "productionWritePerformed": bool(result.get("productionWritePerformed")),
                "notification": notification_payload,
                "result": result,
            }
        )

    def _build_dashboard_payload(self, session: SessionData) -> dict[str, Any]:
        user_info_payload = self.auth_client.get_user_info(session.token)
        refreshed_session = self.auth_client.build_session(session.token, user_info_payload)
        self.auth_client.session_store.save(refreshed_session)

        pending_approval_payload = self.auth_client.call_api(
            path="/moRequest/getRequestUsers",
            method="GET",
            token=session.token,
        )
        pending_approvals, pending_message = parse_list_payload(
            pending_approval_payload,
            empty_codes={"510"},
        )

        waiting_approve_payload = self.auth_client.call_api(
            path="/moRequest/getMyApprove",
            method="GET",
            token=session.token,
            params={"requestType": 0, "startNum": 1, "queryNum": 20},
        )
        waiting_approve_list, waiting_approve_message = parse_list_payload(waiting_approve_payload)

        done_approve_payload = self.auth_client.call_api(
            path="/moRequest/getMyApprove",
            method="GET",
            token=session.token,
            params={"requestType": 1, "startNum": 1, "queryNum": 20},
        )
        done_approve_list, done_approve_message = parse_list_payload(done_approve_payload)

        my_request_payload = self.auth_client.call_api(
            path="/moRequest/getMyRequest",
            method="GET",
            token=session.token,
            params={"requestType": 0, "startNum": 1, "queryNum": 20},
        )
        my_request_list, my_request_message = parse_list_payload(my_request_payload)

        recover_payload = self.auth_client.call_api(
            path="/moRequest/getMyErrorAttend",
            method="GET",
            token=session.token,
            params={"startNum": 1, "queryNum": 20},
        )
        recover_list, recover_message = parse_list_payload(
            recover_payload,
            empty_codes={"10045"},
        )

        face_model_payload = self.auth_client.call_api(
            path="/attendanceImage/searchModel",
            method="POST",
            token=session.token,
            body={},
        )
        face_model_content = face_model_payload.get("retContent")
        face_model_configured = (
            str(face_model_payload.get("retCode") or "") == "200"
            and isinstance(face_model_content, dict)
            and bool(face_model_content.get("imagePath"))
        )

        picture_config_payload = self.auth_client.call_api(
            path="/adUserPictureConfig/getAdUserPictureConfig",
            method="GET",
            token=session.token,
        )
        picture_config = (
            picture_config_payload.get("retContent")
            if isinstance(picture_config_payload.get("retContent"), dict)
            else {}
        )

        unapproved_count = len(pending_approvals)
        return {
            "homeTitle": "掌上考勤",
            "generatedAt": int(time.time()),
            "generatedAtText": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "session": build_session_payload(refreshed_session),
            "user": {
                "userAccount": refreshed_session.user_account,
                "userName": refreshed_session.user_name,
                "realName": refreshed_session.real_name,
                "department": refreshed_session.department,
                "mobile": refreshed_session.user_info.get("mobile") or "",
                "email": refreshed_session.user_info.get("email") or "",
                "userType": refreshed_session.user_info.get("userType") or "",
                "orgId": refreshed_session.user_info.get("orgId") or "",
                "depId": refreshed_session.user_info.get("depId") or "",
            },
            "faceModel": {
                "configured": face_model_configured,
                "imagePath": face_model_content.get("imagePath") if isinstance(face_model_content, dict) else "",
                "allowUpload": bool(picture_config.get("allowUpload")),
                "raw": face_model_payload,
            },
            "approval": {
                "unapprovedCount": unapproved_count,
                "unapprovedList": pending_approvals,
                "unapprovedMessage": pending_message,
                "waitingCount": len(waiting_approve_list),
                "waitingList": waiting_approve_list,
                "waitingMessage": waiting_approve_message,
                "doneCount": len(done_approve_list),
                "doneList": done_approve_list,
                "doneMessage": done_approve_message,
            },
            "requests": {
                "myRequestCount": len(my_request_list),
                "myRequestList": my_request_list,
                "myRequestMessage": my_request_message,
                "needRecoverCount": len(recover_list),
                "needRecoverList": recover_list,
                "needRecoverMessage": recover_message,
            },
            "menuGroups": HOME_MENU_GROUPS,
            "quickStatus": [
                {
                    "key": "unapprovedCount",
                    "label": "待审批",
                    "value": unapproved_count,
                    "detail": pending_message or "审批角标对应 /moRequest/getRequestUsers",
                    "tone": "primary",
                },
                {
                    "key": "myRequestCount",
                    "label": "我的发起",
                    "value": len(my_request_list),
                    "detail": my_request_message or "对应 /moRequest/getMyRequest",
                    "tone": "secondary",
                },
                {
                    "key": "needRecoverCount",
                    "label": "待补签",
                    "value": len(recover_list),
                    "detail": recover_message or "对应 /moRequest/getMyErrorAttend",
                    "tone": "warning",
                },
                {
                    "key": "faceModel",
                    "label": "人脸模型",
                    "value": "已录入" if face_model_configured else "未录入",
                    "detail": (
                        "当前账号已检测到人脸模型"
                        if face_model_configured
                        else "当前账号尚未检测到人脸模型"
                    ),
                    "tone": "success" if face_model_configured else "muted",
                },
            ],
        }

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _read_uploaded_form(self) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
        content_type = self.headers.get("Content-Type", "")
        if "boundary=" not in content_type:
            raise ValueError("未检测到 multipart boundary")

        boundary = content_type.split("boundary=", 1)[1].strip().strip('"')
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length)
        parts = raw.split(f"--{boundary}".encode("utf-8"))
        fields: dict[str, str] = {}
        files: dict[str, dict[str, Any]] = {}

        for part in parts:
            part = part.strip()
            if not part or part == b"--":
                continue
            if part.startswith(b"\r\n"):
                part = part[2:]
            header_end = part.find(b"\r\n\r\n")
            if header_end < 0:
                continue
            header_blob = part[:header_end].decode("utf-8", errors="ignore")
            data = part[header_end + 4 :]
            if data.endswith(b"\r\n"):
                data = data[:-2]
            if data.endswith(b"--"):
                data = data[:-2]
            if data.endswith(b"\r\n"):
                data = data[:-2]

            name_match = re.search(r'name="([^"]+)"', header_blob)
            if not name_match:
                continue
            field_name = name_match.group(1)
            filename_match = re.search(r'filename="([^"]*)"', header_blob)
            if filename_match:
                files[field_name] = {
                    "filename": filename_match.group(1),
                    "content": data,
                }
            else:
                fields[field_name] = data.decode("utf-8", errors="ignore")

        return fields, files

    def _read_uploaded_file(self) -> bytes:
        _, files = self._read_uploaded_form()
        for item in files.values():
            data = item.get("content") or b""
            if data:
                return data
        raise ValueError("未找到上传文件")

    def _write_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    args = build_parser().parse_args()
    auth_client = AttendanceAuthClient()
    account_registry = AccountRegistry()
    notifier = WeComBotNotifier()
    polling_scheduler = ClockDryRunScheduler(account_registry, notifier=notifier)
    server = ThreadingHTTPServer((args.host, args.port), RebuildLoginHandler)
    server.auth_client = auth_client  # type: ignore[attr-defined]
    server.account_registry = account_registry  # type: ignore[attr-defined]
    server.polling_scheduler = polling_scheduler  # type: ignore[attr-defined]
    server.notifier = notifier  # type: ignore[attr-defined]
    print(f"Serving rebuilt login at http://{args.host}:{args.port}")
    print(f"Proxying remote page base: {BASE_PAGE_URL}")
    print(f"Caching session in: {auth_client.session_store.path}")
    print(
        "Clock polling schedule: "
        f"{build_polling_schedule_text(polling_scheduler._allow_weekends, polling_scheduler._slots)} / "
        f"{build_polling_execution_mode_label(polling_scheduler._execution_mode)}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        polling_scheduler.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
