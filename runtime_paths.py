from __future__ import annotations

import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parent
IS_FROZEN = bool(getattr(sys, "frozen", False))
APP_ROOT = Path(sys.executable).resolve().parent if IS_FROZEN else SOURCE_ROOT
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT)).resolve()


def bundle_path(*parts: str) -> Path:
    return BUNDLE_ROOT.joinpath(*parts)


def app_path(*parts: str) -> Path:
    return APP_ROOT.joinpath(*parts)
