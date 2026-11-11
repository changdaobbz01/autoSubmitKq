from __future__ import annotations

import ssl
import unittest
import urllib.error
from unittest.mock import Mock, patch

import network_utils


FINGERPRINT = "A" * 64


class DirectUrlOpenTests(unittest.TestCase):
    def test_expired_certificate_retries_with_pinned_opener(self) -> None:
        expired = ssl.SSLCertVerificationError(1, "certificate has expired")
        direct_opener = Mock()
        direct_opener.open.side_effect = urllib.error.URLError(expired)
        pinned_opener = Mock()
        response = object()
        pinned_opener.open.return_value = response

        with (
            patch.object(network_utils, "_DIRECT_OPENER", direct_opener),
            patch.object(network_utils, "_build_routed_opener", return_value=pinned_opener) as build,
        ):
            result = network_utils.direct_urlopen(
                "https://attendance.example/api",
                expired_certificate_pins={"attendance.example": FINGERPRINT},
            )

        self.assertIs(response, result)
        build.assert_called_once_with((), (("attendance.example", FINGERPRINT),))

    def test_other_tls_failures_are_not_bypassed(self) -> None:
        mismatch = ssl.SSLCertVerificationError(1, "hostname mismatch")
        direct_opener = Mock()
        direct_opener.open.side_effect = urllib.error.URLError(mismatch)

        with (
            patch.object(network_utils, "_DIRECT_OPENER", direct_opener),
            patch.object(network_utils, "_build_routed_opener") as build,
        ):
            with self.assertRaises(urllib.error.URLError):
                network_utils.direct_urlopen(
                    "https://attendance.example/api",
                    expired_certificate_pins={"attendance.example": FINGERPRINT},
                )

        build.assert_not_called()

    def test_invalid_pin_is_rejected_before_network_request(self) -> None:
        direct_opener = Mock()
        with patch.object(network_utils, "_DIRECT_OPENER", direct_opener):
            with self.assertRaises(ValueError):
                network_utils.direct_urlopen(
                    "https://attendance.example/api",
                    expired_certificate_pins={"attendance.example": "invalid"},
                )
        direct_opener.open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
