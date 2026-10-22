"""`pumpgrok doctor`: subsystem health report (FOUND-013, R37).

A subsystem is `ok` when its module resolves. Subsystems whose owning phase has not landed
are reported as `warn ... not-yet-implemented`. `run --serve` additionally serves
`GET /healthz` and `GET /metrics` on 127.0.0.1; the doctor probes both with stdlib
`urllib` (no curl in slim images) and reports the result next to the subsystem lines.
Probe warnings never fail the report: exit 0 means the process started with valid settings.
"""

from __future__ import annotations

import importlib.util
import urllib.error
import urllib.request
from dataclasses import dataclass

from pumpgrok.config.settings import Settings, current_profile

SUBSYSTEMS: tuple[tuple[str, str], ...] = (
    ("settings", "pumpgrok.config.settings"),
    ("core", "pumpgrok.core"),
    ("ledger", "pumpgrok.ledger"),
    ("replay", "pumpgrok.replay"),
    ("logging", "pumpgrok.logging"),
    ("execution.live", "pumpgrok.execution.live"),
    ("engine", "pumpgrok.engine"),
    ("tools", "pumpgrok.tools"),
    ("gateway", "pumpgrok.gateway"),
    ("supervisor", "pumpgrok.supervisor"),
    ("reports", "pumpgrok.reports"),
)


#: Endpoints served by `run --serve` on 127.0.0.1, probed by the doctor.
SERVED_ENDPOINTS: tuple[str, ...] = ("/healthz", "/metrics")


@dataclass(frozen=True)
class EndpointProbe:
    """One served-endpoint probe: `ok` only for HTTP 200, else `warn` (never fatal)."""

    name: str
    ok: bool
    detail: str

    def line(self) -> str:
        if self.ok:
            return f"ok    {self.name} (served, {self.detail})"
        return f"warn  {self.name} (not served: {self.detail})"


def probe_served_endpoints(port: int, *, timeout_s: float = 2.0) -> list[EndpointProbe]:
    """Probe the serve endpoints on 127.0.0.1 with stdlib urllib (no curl dependency)."""
    probes: list[EndpointProbe] = []
    for path in SERVED_ENDPOINTS:
        url = f"http://127.0.0.1:{port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=timeout_s) as resp:
                code = resp.status
        except urllib.error.HTTPError as exc:
            probes.append(EndpointProbe(name=path, ok=False, detail=f"HTTP {exc.code}"))
            continue
        except Exception as exc:
            probes.append(EndpointProbe(name=path, ok=False, detail=type(exc).__name__))
            continue
        probes.append(
            EndpointProbe(name=path, ok=code == 200, detail=f"HTTP {code}")
        )
    return probes
SUBSYSTEMS: tuple[tuple[str, str], ...] = (
    ("settings", "pumpgrok.config.settings"),
    ("core", "pumpgrok.core"),
    ("ledger", "pumpgrok.ledger"),
    ("replay", "pumpgrok.replay"),
    ("logging", "pumpgrok.logging"),
    ("execution.live", "pumpgrok.execution.live"),
    ("engine", "pumpgrok.engine"),
    ("tools", "pumpgrok.tools"),
    ("gateway", "pumpgrok.gateway"),
    ("supervisor", "pumpgrok.supervisor"),
    ("reports", "pumpgrok.reports"),
)


@dataclass(frozen=True)
class SubsystemStatus:
    name: str
    module: str
    present: bool

    def line(self) -> str:
        if self.present:
            return f"ok    {self.name} ({self.module})"
        return f"warn  {self.name} ({self.module}): not-yet-implemented"


def subsystem_statuses() -> list[SubsystemStatus]:
    return [
        SubsystemStatus(
            name=name, module=module, present=importlib.util.find_spec(module) is not None
        )
        for name, module in SUBSYSTEMS
    ]


def doctor_report(settings: Settings) -> list[str]:
    """Lines for stdout: effective mode, one status line per subsystem, endpoint probes, summary."""
    statuses = subsystem_statuses()
    present = sum(1 for status in statuses if status.present)
    absent = len(statuses) - present
    lines = [f"info  mode={settings.effective_mode} profile={current_profile()}"]
    lines.extend(status.line() for status in statuses)
    port = settings.health.port
    if port <= 0:
        lines.append(
            "warn  /healthz (not served: health.port=0, only `run --serve` binds a port)"
        )
        lines.append(
            "warn  /metrics (not served: health.port=0, only `run --serve` binds a port)"
        )
    else:
        lines.extend(probe.line() for probe in probe_served_endpoints(port))
    lines.append(f"doctor: {present} present, {absent} not-yet-implemented (warnings), exit 0")
    return lines
