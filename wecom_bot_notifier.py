from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from network_utils import direct_urlopen
from runtime_paths import APP_ROOT

PROJECT_DIR = APP_ROOT
DEFAULT_CONFIG_PATH = PROJECT_DIR / ".attendance_auth" / "wecom_bot.json"
WEBHOOK_PREFIX = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key="
DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "webhookUrl": "",
    "notifyOnSubmit": True,
    "notifyOnPolling": False,
    "mentionAllOnFailure": False,
    "updatedAt": 0,
    "lastTest": None,
    "lastDelivery": None,
}


def _format_timestamp(epoch: int | None) -> str:
    if not epoch:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch))


class WeComBotNotifier:
    def __init__(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        self.path = path

    def get_public_config(self) -> dict[str, Any]:
        return self._to_public(self._load())

    def save_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        config = self._load()
        webhook_input = str(updates.get("webhookUrl", "") or "").strip()
        if webhook_input:
            config["webhookUrl"] = self._normalize_webhook_url(webhook_input)

        for key in ("enabled", "notifyOnSubmit", "notifyOnPolling", "mentionAllOnFailure"):
            if key in updates:
                config[key] = bool(updates.get(key))

        config["updatedAt"] = int(time.time())
        self._write(config)
        public = self._to_public(config)
        public["webhookUpdated"] = bool(webhook_input)
        return public

    def send_test_message(self) -> dict[str, Any]:
        payload = self._send_text(
            purpose="test",
            content="\n".join(
                [
                    "[掌上考勤] 企业微信群通知测试",
                    f"时间：{_format_timestamp(int(time.time()))}",
                    "状态：企业微信群机器人 webhook 已联通",
                    "说明：这是一条手动发送的测试消息。",
                ]
            ),
            mention_all=False,
        )
        self._record_status("lastTest", payload)
        return payload

    def notify_submit(
        self,
        *,
        user_account: str,
        real_name: str,
        result: dict[str, Any],
        photo_state: dict[str, Any] | None = None,
        image_source: str = "account-photo",
    ) -> dict[str, Any]:
        submit_response = result.get("submitResponse") if isinstance(result.get("submitResponse"), dict) else {}
        ret_code = str(submit_response.get("retCode") or "")
        ret_msg = str(submit_response.get("retMsg") or "")
        is_success = bool(submit_response.get("isSuccess")) and ret_code == "200"
        photo_status = str((photo_state or {}).get("statusText") or "未配置")
        location = result.get("location") if isinstance(result.get("location"), dict) else {}
        address = str(location.get("rangeAddress") or "")
        content = "\n".join(
            [
                "[掌上考勤] 真实打卡结果",
                f"账号：{user_account}{f' / {real_name}' if real_name else ''}",
                f"时间：{_format_timestamp(int(time.time()))}",
                f"结果：{'成功' if is_success else '失败'}",
                f"接口返回：{ret_code or '-'} / {ret_msg or '-'}",
                f"地址：{address or '-'}",
                f"照片状态：{photo_status}",
                f"图片来源：{image_source}",
            ]
        )
        payload = self._send_text(
            purpose="submit",
            content=content,
            mention_all=self._load().get("mentionAllOnFailure", False) and not is_success,
        )
        self._record_status("lastDelivery", payload)
        return payload

    def notify_polling_run(self, run_record: dict[str, Any]) -> dict[str, Any]:
        details = run_record.get("details") if isinstance(run_record.get("details"), dict) else {}
        failed_count = int(details.get("failedCount") or 0)
        skipped_count = int(details.get("skippedCount") or 0)
        success_count = int(details.get("successCount") or 0)
        total_count = int(details.get("totalCount") or 0)
        accounts = details.get("accounts") if isinstance(details.get("accounts"), list) else []
        highlighted: list[str] = []
        for item in accounts:
            if not isinstance(item, dict):
                continue
            if item.get("ok") and not item.get("skipped"):
                continue
            user_account = str(item.get("userAccount") or "-")
            summary = str(item.get("summary") or "-")
            highlighted.append(f"- {user_account}: {summary}")
            if len(highlighted) >= 5:
                break

        lines = [
            "[掌上考勤] 轮询结果",
            f"时段：{run_record.get('slotLabel') or '-'}",
            f"触发：{run_record.get('trigger') or '-'}",
            f"模式：{run_record.get('executionModeLabel') or '-'}",
            f"完成时间：{run_record.get('finishedAtText') or run_record.get('startedAtText') or '-'}",
            f"汇总：账号 {total_count} 个 / 成功 {success_count} / 跳过 {skipped_count} / 失败 {failed_count}",
        ]
        if highlighted:
            lines.append("异常摘要：")
            lines.extend(highlighted)

        payload = self._send_text(
            purpose="polling",
            content="\n".join(lines),
            mention_all=self._load().get("mentionAllOnFailure", False) and failed_count > 0,
        )
        self._record_status("lastDelivery", payload)
        return payload

    def _send_text(self, *, purpose: str, content: str, mention_all: bool) -> dict[str, Any]:
        config = self._load()
        if purpose in {"submit", "polling"} and not config.get("enabled"):
            return self._skip_result(purpose, "企业微信群通知未启用。")
        if purpose == "submit" and not config.get("notifyOnSubmit"):
            return self._skip_result(purpose, "真实打卡通知未开启。")
        if purpose == "polling" and not config.get("notifyOnPolling"):
            return self._skip_result(purpose, "轮询通知未开启。")

        webhook_url = str(config.get("webhookUrl") or "").strip()
        if not webhook_url:
            return self._skip_result(purpose, "还没有配置企业微信群机器人 webhook。")

        payload: dict[str, Any] = {
            "msgtype": "text",
            "text": {
                "content": content,
            },
        }
        if mention_all:
            payload["text"]["mentioned_list"] = ["@all"]

        request = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            with direct_urlopen(request, timeout=10) as response:
                raw = response.read().decode("utf-8")
            body = json.loads(raw or "{}")
            errcode = int(body.get("errcode", -1))
            errmsg = str(body.get("errmsg") or "")
            sent = errcode == 0
            return {
                "attempted": True,
                "sent": sent,
                "purpose": purpose,
                "errcode": errcode,
                "errmsg": errmsg,
                "statusText": "企业微信群通知已发送。" if sent else f"企业微信群通知发送失败：{errmsg or errcode}",
                "sentAt": int(time.time()),
                "sentAtText": _format_timestamp(int(time.time())),
            }
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="ignore")
            return {
                "attempted": True,
                "sent": False,
                "purpose": purpose,
                "statusText": f"企业微信群通知发送失败：HTTP {exc.code}",
                "error": message or str(exc),
                "sentAt": int(time.time()),
                "sentAtText": _format_timestamp(int(time.time())),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "attempted": True,
                "sent": False,
                "purpose": purpose,
                "statusText": f"企业微信群通知发送失败：{exc}",
                "error": str(exc),
                "sentAt": int(time.time()),
                "sentAtText": _format_timestamp(int(time.time())),
            }

    def _record_status(self, key: str, payload: dict[str, Any]) -> None:
        config = self._load()
        config[key] = payload
        self._write(config)

    def _skip_result(self, purpose: str, status_text: str) -> dict[str, Any]:
        return {
            "attempted": False,
            "sent": False,
            "purpose": purpose,
            "statusText": status_text,
            "sentAt": int(time.time()),
            "sentAtText": _format_timestamp(int(time.time())),
        }

    def _normalize_webhook_url(self, webhook_url: str) -> str:
        webhook_url = webhook_url.strip()
        if not webhook_url.startswith(WEBHOOK_PREFIX):
            raise ValueError("Webhook URL 必须是企业微信群机器人地址。")
        return webhook_url

    def _mask_webhook_url(self, webhook_url: str) -> str:
        if not webhook_url:
            return ""
        if "key=" not in webhook_url:
            return webhook_url
        prefix, key = webhook_url.split("key=", 1)
        if len(key) <= 8:
            masked_key = "*" * len(key)
        else:
            masked_key = f"{key[:4]}***{key[-4:]}"
        return f"{prefix}key={masked_key}"

    def _to_public(self, config: dict[str, Any]) -> dict[str, Any]:
        webhook_url = str(config.get("webhookUrl") or "")
        updated_at = int(config.get("updatedAt") or 0)
        return {
            "enabled": bool(config.get("enabled")),
            "hasWebhook": bool(webhook_url),
            "webhookMasked": self._mask_webhook_url(webhook_url),
            "notifyOnSubmit": bool(config.get("notifyOnSubmit")),
            "notifyOnPolling": bool(config.get("notifyOnPolling")),
            "mentionAllOnFailure": bool(config.get("mentionAllOnFailure")),
            "updatedAt": updated_at,
            "updatedAtText": _format_timestamp(updated_at),
            "lastTest": config.get("lastTest"),
            "lastDelivery": config.get("lastDelivery"),
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_CONFIG)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_CONFIG)
        return {**DEFAULT_CONFIG, **raw}

    def _write(self, config: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)
