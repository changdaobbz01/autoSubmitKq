from __future__ import annotations

import http.client
import ssl
import urllib.request
from functools import lru_cache
from typing import Any

# Force direct connections for business and notification traffic so the app
# does not depend on system-wide HTTP(S) proxy settings such as Clash.
_DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class _RoutedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        host: str,
        *,
        host_overrides: dict[str, str],
        context: ssl.SSLContext | None = None,
        check_hostname: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(host, context=context, check_hostname=check_hostname, **kwargs)
        self._host_overrides = host_overrides

    def connect(self) -> None:
        certificate_host = self.host
        connect_host = self._host_overrides.get(certificate_host.lower(), certificate_host)

        # Open the socket against the routed IP, then restore the original host
        # before TLS so SNI and hostname verification still use the certificate domain.
        self.host = connect_host
        try:
            http.client.HTTPConnection.connect(self)
        finally:
            self.host = certificate_host

        server_hostname = self._tunnel_host or certificate_host
        self.sock = self._context.wrap_socket(self.sock, server_hostname=server_hostname)


class _RoutedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, host_overrides: dict[str, str]) -> None:
        super().__init__(context=ssl.create_default_context())
        self._host_overrides = host_overrides

    def https_open(self, request: urllib.request.Request) -> Any:
        def connection_factory(host: str, **kwargs: Any) -> _RoutedHTTPSConnection:
            return _RoutedHTTPSConnection(host, host_overrides=self._host_overrides, **kwargs)

        return self.do_open(connection_factory, request)


@lru_cache(maxsize=8)
def _build_routed_opener(overrides: tuple[tuple[str, str], ...]) -> urllib.request.OpenerDirector:
    host_overrides = {host.lower(): target for host, target in overrides}
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _RoutedHTTPSHandler(host_overrides),
    )


def direct_urlopen(
    request: str | urllib.request.Request,
    timeout: float | None = None,
    *,
    host_overrides: dict[str, str] | None = None,
) -> Any:
    if not host_overrides:
        return _DIRECT_OPENER.open(request, timeout=timeout)

    normalized = tuple(
        sorted(
            (str(host).strip().lower(), str(target).strip())
            for host, target in host_overrides.items()
            if str(host).strip() and str(target).strip()
        )
    )
    opener = _build_routed_opener(normalized) if normalized else _DIRECT_OPENER
    return opener.open(request, timeout=timeout)
