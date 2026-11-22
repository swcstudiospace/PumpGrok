"""HOST-09: non-loopback gateway bind refused without TLS/proxy."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "desk-gateway" / "src"))

from desk_gateway.config import is_loopback_host, validate_gateway_bind


def test_loopback_hosts_allowed() -> None:
    for host in ("127.0.0.1", "localhost", "::1"):
        validate_gateway_bind(host, environ={})


def test_non_loopback_refused_without_flags() -> None:
    try:
        validate_gateway_bind("0.0.0.0", environ={})
    except ValueError:
        return
    raise AssertionError("non-loopback bind without TLS/proxy must raise")


def test_tls_flag_allows_non_loopback() -> None:
    validate_gateway_bind("0.0.0.0", environ={"DESK_GATEWAY_TLS": "1"})


def test_proxy_flag_allows_non_loopback() -> None:
    validate_gateway_bind("10.0.0.5", environ={"DESK_GATEWAY_REVERSE_PROXY": "true"})


def test_is_loopback_helper() -> None:
    assert is_loopback_host("127.0.0.1")
    assert not is_loopback_host("0.0.0.0")
