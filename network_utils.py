from __future__ import annotations

import urllib.request
from typing import Any

# Force direct connections for business and notification traffic so the app
# does not depend on system-wide HTTP(S) proxy settings such as Clash.
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def direct_urlopen(request: str | urllib.request.Request, timeout: float | None = None) -> Any:
    return _DIRECT_OPENER.open(request, timeout=timeout)
