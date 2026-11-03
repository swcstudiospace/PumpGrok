"""Doctor endpoint probes catch only the typed network errors (QLT-06, 11-04).

An unreachable or misbehaving endpoint is a warn line naming the error type, so the report still
exits 0. Anything outside the typed tuple (OSError, ValueError, http.client.HTTPException) is a
programming error and propagates instead of being reported as a warning.
"""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request

import pytest

from pumpgrok import doctor


class _Response:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def _urlopen_raising(error: BaseException):
    def fake(url: str, timeout: float) -> None:
        raise error

    return fake


def test_served_endpoint_answering_200_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout: _Response(200))
    probes = doctor.probe_served_endpoints(8080)
    assert [probe.ok for probe in probes] == [True, True]
    assert all(probe.detail == "HTTP 200" for probe in probes)


def test_http_error_status_is_a_warn_with_the_code(monkeypatch: pytest.MonkeyPatch) -> None:
    error = urllib.error.HTTPError("http://127.0.0.1/healthz", 503, "degraded", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_raising(error))
    probes = doctor.probe_served_endpoints(8080)
    assert all(probe.ok is False for probe in probes)
    assert all(probe.detail == "HTTP 503" for probe in probes)


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("connection refused"),
        TimeoutError("timed out"),
        http.client.RemoteDisconnected("closed without a response"),
        http.client.InvalidURL("bad port"),
    ],
    ids=["URLError", "TimeoutError", "RemoteDisconnected", "InvalidURL"],
)
def test_typed_network_failure_is_a_warn_named_by_type(
    monkeypatch: pytest.MonkeyPatch, error: BaseException
) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_raising(error))
    probes = doctor.probe_served_endpoints(8080)
    assert all(probe.ok is False for probe in probes)
    assert all(probe.detail == type(error).__name__ for probe in probes)


def test_unexpected_error_propagates_instead_of_becoming_a_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_raising(RuntimeError("probe bug")))
    with pytest.raises(RuntimeError, match="probe bug"):
        doctor.probe_served_endpoints(8080)
