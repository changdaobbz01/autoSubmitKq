from __future__ import annotations

import hashlib
import hmac
import http.client
import ssl
import string
import urllib.error
import urllib.parse
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
        certificate_sha256: str | None = None,
        context: ssl.SSLContext | None = None,
        check_hostname: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(host, context=context, check_hostname=check_hostname, **kwargs)
        self._host_overrides = host_overrides
        self._certificate_sha256 = certificate_sha256

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
        if self._certificate_sha256:
            actual = hashlib.sha256(self.sock.getpeercert(binary_form=True)).hexdigest().upper()
            if not hmac.compare_digest(actual, self._certificate_sha256):
                self.sock.close()
                raise ssl.SSLCertVerificationError(
                    1,
                    "server certificate fingerprint does not match the pinned certificate",
                )


class _RoutedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(
        self,
        host_overrides: dict[str, str],
        certificate_pins: dict[str, str] | None = None,
    ) -> None:
        super().__init__(context=ssl.create_default_context())
        self._host_overrides = host_overrides
        self._certificate_pins = certificate_pins or {}

    def https_open(self, request: urllib.request.Request) -> Any:
        def connection_factory(host: str, **kwargs: Any) -> _RoutedHTTPSConnection:
            hostname = urllib.parse.urlsplit(f"//{host}").hostname or host
            certificate_sha256 = self._certificate_pins.get(hostname.lower())
            if certificate_sha256:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                kwargs["context"] = context
                kwargs["check_hostname"] = False
            return _RoutedHTTPSConnection(
                host,
                host_overrides=self._host_overrides,
                certificate_sha256=certificate_sha256,
                **kwargs,
            )

        return self.do_open(connection_factory, request)


@lru_cache(maxsize=8)
def _build_routed_opener(
    overrides: tuple[tuple[str, str], ...],
    certificate_pins: tuple[tuple[str, str], ...] = (),
) -> urllib.request.OpenerDirector:
    host_overrides = {host.lower(): target for host, target in overrides}
    normalized_pins = {host.lower(): fingerprint for host, fingerprint in certificate_pins}
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _RoutedHTTPSHandler(host_overrides, normalized_pins),
    )


def _normalize_certificate_pins(pins: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    normalized: list[tuple[str, str]] = []
    for host, fingerprint in (pins or {}).items():
        normalized_host = str(host).strip().lower()
        normalized_fingerprint = str(fingerprint).replace(":", "").replace(" ", "").upper()
        if not normalized_host or not normalized_fingerprint:
            continue
        if len(normalized_fingerprint) != 64 or any(
            character not in string.hexdigits for character in normalized_fingerprint
        ):
            raise ValueError(f"Invalid SHA-256 certificate fingerprint for {normalized_host}")
        normalized.append((normalized_host, normalized_fingerprint))
    return tuple(sorted(normalized))


def _is_expired_certificate_error(exception: BaseException) -> bool:
    pending: list[BaseException] = [exception]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, ssl.SSLCertVerificationError):
            verify_code = getattr(current, "verify_code", None)
            verify_message = str(getattr(current, "verify_message", "") or current).lower()
            if verify_code == 10 or "certificate has expired" in verify_message:
                return True
        for related in (
            getattr(current, "reason", None),
            current.__cause__,
            current.__context__,
        ):
            if isinstance(related, BaseException):
                pending.append(related)
    return False


def direct_urlopen(
    request: str | urllib.request.Request,
    timeout: float | None = None,
    *,
    host_overrides: dict[str, str] | None = None,
    expired_certificate_pins: dict[str, str] | None = None,
) -> Any:
    normalized = tuple(
        sorted(
            (str(host).strip().lower(), str(target).strip())
            for host, target in (host_overrides or {}).items()
            if str(host).strip() and str(target).strip()
        )
    )
    normalized_pins = _normalize_certificate_pins(expired_certificate_pins)
    opener = _build_routed_opener(normalized) if normalized else _DIRECT_OPENER
    try:
        return opener.open(request, timeout=timeout)
    except urllib.error.URLError as exception:
        if not normalized_pins or not _is_expired_certificate_error(exception):
            raise

    # The fallback still authenticates the exact known certificate by SHA-256.
    pinned_opener = _build_routed_opener(normalized, normalized_pins)
    return pinned_opener.open(request, timeout=timeout)
