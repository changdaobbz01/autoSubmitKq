from __future__ import annotations

import logging
from pathlib import Path

import webview

from runtime_paths import APP_ROOT, bundle_path
from token_uploader.bridge import TokenCollectorBridge


def configure_logging() -> None:
    log_dir = APP_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_dir / "token-collector.log", encoding="utf-8")],
    )


def main() -> None:
    configure_logging()
    index_path = bundle_path("token_uploader", "web", "index.html")
    if not index_path.exists():
        raise FileNotFoundError(f"Desktop UI is missing: {index_path}")

    bridge = TokenCollectorBridge()
    webview.create_window(
        "考勤 Token 采集器",
        url=Path(index_path).as_uri(),
        js_api=bridge,
        width=520,
        height=820,
        min_size=(430, 680),
        background_color="#07152d",
        text_select=False,
        zoomable=False,
    )
    webview.start(gui="edgechromium", debug=False, private_mode=True)


if __name__ == "__main__":
    main()
