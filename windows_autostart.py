from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from runtime_paths import IS_FROZEN, SOURCE_ROOT, app_path


SHORTCUT_NAME = "AttendanceRebuild Backend.lnk"
BACKGROUND_LAUNCHER_NAME = "Launch-AttendanceRebuild-Background.vbs"


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA", "")
    return Path(appdata).expanduser() / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _shortcut_path() -> Path:
    return _startup_dir() / SHORTCUT_NAME


def _ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _run_powershell(script: str) -> str:
    command = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$OutputEncoding = [System.Text.Encoding]::UTF8; "
        + script
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "PowerShell failed").strip()
        raise RuntimeError(message)
    return completed.stdout.strip()


def _source_launcher_path() -> Path:
    return app_path(".attendance_auth", "autostart", BACKGROUND_LAUNCHER_NAME)


def _build_source_launcher() -> Path:
    launcher_path = _source_launcher_path()
    launcher_path.parent.mkdir(parents=True, exist_ok=True)
    python_exe = Path(sys.executable).resolve()
    server_path = (SOURCE_ROOT / "rebuild_login" / "server.py").resolve()
    current_dir = str(SOURCE_ROOT.resolve()).replace('"', '""')
    python_text = str(python_exe).replace('"', '""')
    server_text = str(server_path).replace('"', '""')
    launcher_text = (
        "Option Explicit\n\n"
        "Dim shell\n"
        "Set shell = CreateObject(\"WScript.Shell\")\n"
        f"shell.CurrentDirectory = \"{current_dir}\"\n"
        f"shell.Run \"\"\"{python_text}\"\" \"\"\"{server_text}\"\"\", 0, False\n"
    )
    launcher_path.write_text(launcher_text, encoding="utf-16")
    return launcher_path


def get_launcher_path() -> Path:
    if IS_FROZEN:
        launcher_path = app_path(BACKGROUND_LAUNCHER_NAME)
        if launcher_path.exists():
            return launcher_path
    return _build_source_launcher()


def _extract_json_payload(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {}
    return json.loads(text[start : end + 1])


def _shortcut_details() -> dict[str, Any]:
    shortcut_path = _shortcut_path()
    if not shortcut_path.exists():
        return {
            "Installed": False,
            "ShortcutPath": str(shortcut_path),
            "Target": "",
            "Arguments": "",
            "WorkingDirectory": "",
        }

    script = f"""
    $shortcutPath = {_ps_quote(str(shortcut_path))}
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    [pscustomobject]@{{
      Installed = $true
      ShortcutPath = $shortcutPath
      Target = $shortcut.TargetPath
      Arguments = $shortcut.Arguments
      WorkingDirectory = $shortcut.WorkingDirectory
    }} | ConvertTo-Json -Compress
    """
    raw = _run_powershell(script)
    return _extract_json_payload(raw)


def _create_shortcut() -> dict[str, Any]:
    startup_dir = _startup_dir()
    startup_dir.mkdir(parents=True, exist_ok=True)
    shortcut_path = _shortcut_path()
    launcher_path = get_launcher_path()
    wscript_path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wscript.exe"
    icon_path = app_path("AttendanceRebuild.exe") if IS_FROZEN else Path(sys.executable).resolve()
    icon_location = f"{icon_path},0"
    launcher_text = str(launcher_path).replace('"', '""')
    launcher_arg = f'"{launcher_text}"'

    script = f"""
    $shortcutPath = {_ps_quote(str(shortcut_path))}
    $targetPath = {_ps_quote(str(wscript_path))}
    $arguments = {_ps_quote(launcher_arg)}
    $workingDirectory = {_ps_quote(str(launcher_path.parent))}
    $iconLocation = {_ps_quote(icon_location)}
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $targetPath
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $workingDirectory
    $shortcut.WindowStyle = 7
    $shortcut.IconLocation = $iconLocation
    $shortcut.Description = 'Start AttendanceRebuild backend at Windows sign-in'
    $shortcut.Save()
    [pscustomobject]@{{
      Installed = $true
      ShortcutPath = $shortcutPath
      Target = $shortcut.TargetPath
      Arguments = $shortcut.Arguments
      WorkingDirectory = $shortcut.WorkingDirectory
    }} | ConvertTo-Json -Compress
    """
    raw = _run_powershell(script)
    return _extract_json_payload(raw)


def _remove_shortcut() -> dict[str, Any]:
    shortcut_path = _shortcut_path()
    if shortcut_path.exists():
        shortcut_path.unlink()
    return {
        "Installed": False,
        "ShortcutPath": str(shortcut_path),
        "Target": "",
        "Arguments": "",
        "WorkingDirectory": "",
    }


def get_public_status() -> dict[str, Any]:
    if not _is_windows():
        return {
            "supported": False,
            "enabled": False,
            "statusText": "当前环境不是 Windows，无法配置开机自启动。",
        }

    details = _shortcut_details()
    installed = bool(details.get("Installed"))
    launcher_path = get_launcher_path()
    return {
        "supported": True,
        "enabled": installed,
        "statusText": "已开启开机自启动，登录 Windows 后只会后台启动后端。" if installed else "当前未开启开机自启动。",
        "modeText": "仅后台启动后端，不自动打开前端页面。",
        "shortcutPath": str(details.get("ShortcutPath") or _shortcut_path()),
        "target": str(details.get("Target") or ""),
        "arguments": str(details.get("Arguments") or ""),
        "workingDirectory": str(details.get("WorkingDirectory") or ""),
        "launcherPath": str(launcher_path),
        "launcherExists": launcher_path.exists(),
        "runMode": "packaged" if IS_FROZEN else "source",
    }


def set_enabled(enabled: bool) -> dict[str, Any]:
    if not _is_windows():
        raise ValueError("当前环境不是 Windows，无法配置开机自启动。")

    if enabled:
        _create_shortcut()
    else:
        _remove_shortcut()
    payload = get_public_status()
    payload["updated"] = True
    return payload
