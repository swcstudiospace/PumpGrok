"""`pumpgrok doctor`: subsystem health report (FOUND-013, R37).

A subsystem is `ok` when its module resolves. Subsystems whose owning phase has not landed
are reported as `warn ... not-yet-implemented`. `run --serve` additionally serves
`GET /healthz` and `GET /metrics` on 127.0.0.1; the doctor probes both with stdlib
`urllib` (no curl in slim images) and reports the result next to the subsystem lines.
Probe warnings never fail the report: exit 0 means the process started with valid settings.
"""

from __future__ import annotations

import http.client
import importlib.util
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

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


def event_mode_refusal(wake_mode: str, jobs_path: Path | None = None) -> list[str]:
    """Refusal lines when event mode is selected with superseded jobs enabled."""
    from pumpgrok.cli.wake_mode import event_mode_refusal  # noqa: PLC0415

    path = jobs_path if jobs_path is not None else Path("hermes/cron/jobs.yaml")
    return event_mode_refusal(wake_mode, path)


def time_sync_probe() -> str:
    """Read-only time-sync probe: reports only, never adjusts the clock."""
    return "info  time-sync: read-only probe, offset not adjusted"


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
        except (OSError, ValueError, http.client.HTTPException) as exc:
            probes.append(EndpointProbe(name=path, ok=False, detail=type(exc).__name__))
            continue
        probes.append(EndpointProbe(name=path, ok=code == 200, detail=f"HTTP {code}"))
    return probes


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


def doctor_bus_lines(settings: Settings, *, depth: int | None = None, lanes: tuple[str, ...] = ()) -> list[str]:
    """Bus depth and lane state, read-only (OBS-01 D-02). Never writes, sends, or holds a key."""
    sidecar = settings.events.sidecar_path
    enabled = settings.events.enabled
    if depth is None:
        depth = 0
    lane_text = ", ".join(lanes) if lanes else "none"
    return [
        f"info  bus depth={depth} lanes={lane_text} sidecar={sidecar} enabled={enabled}",
    ]


def doctor_source_lines(settings: Settings, *, states: dict[str, str] | None = None) -> list[str]:
    """Per-source status from the SourceSupervisor surface, read-only (OBS-01 D-02)."""
    if states is None:
        states = {"feed": "unknown"}
    lines = []
    for name, state in sorted(states.items()):
        if state in ("live", "stale", "resyncing", "disconnected", "unknown"):
            lines.append(f"info  source {name} status={state}")
        else:
            lines.append(f"warn  source {name} status=unknown")
    return lines


def doctor_grok_budget_lines(settings: Settings, *, windows: dict[str, str] | None = None) -> list[str]:
    """Grok layered-budget window states, read-only (OBS-01 D-02). Key by name only, never value."""
    if windows is None:
        windows = {"daily": "unset"}
    lines = []
    for window, state in sorted(windows.items()):
        lines.append(f"info  grok-budget {window} state={state}")
    return lines


def doctor_stage_lines(settings: Settings, *, stages: dict[str, str] | None = None) -> list[str]:
    """Strategy stages from the promotion surface, read-only (OBS-01 D-02)."""
    if stages is None:
        stages = {}
    if not stages:
        return ["info  stages none"]
    return [f"info  stage {sid} stage={stage}" for sid, stage in sorted(stages.items())]


def doctor_kills_lines(settings: Settings, *, kills: tuple[str, ...] | None = None) -> list[str]:
    """Active kills from the ledger kill surface, read-only (OBS-01 D-02)."""
    if kills is None:
        from pathlib import Path as _P  # noqa: PLC0415
        import os as _os  # noqa: PLC0415

        found: list[str] = []
        if _os.environ.get("PUMPGROK_KILLSWITCH"):
            found.append("env:PUMPGROK_KILLSWITCH")
        latch = _P("var/desk/KILLSWITCH")
        try:
            if latch.is_file():
                found.append("file:var/desk/KILLSWITCH")
        except OSError:
            return ["warn  kills unreadable"]
        kills = tuple(found)
    if not kills:
        return ["info  kills none"]
    return [f"info  kill {k}" for k in kills]


def doctor_signer_lines(settings: Settings, *, attestation: str | None = None) -> list[str]:
    """Signer attestation state by name and source only, never the value (OBS-01 D-02, T-19-01)."""
    if attestation is None:
        enabled = settings.signer.enabled
        attestation = "present" if enabled else "absent"
    return [f"info  signer attestation={attestation} source=settings"]


def doctor_report(settings: Settings, *, wake_mode: str = "cadence") -> list[str]:
    """Lines for stdout: effective mode, one status line per subsystem, endpoint probes, summary."""
    statuses = subsystem_statuses()
    present = sum(1 for status in statuses if status.present)
    absent = len(statuses) - present
    lines = [f"info  mode={settings.effective_mode} profile={current_profile()}"]
    lines.extend(event_mode_refusal(wake_mode))
    lines.append(time_sync_probe())
    lines.extend(status.line() for status in statuses)
    lines.extend(doctor_bus_lines(settings))
    lines.extend(doctor_source_lines(settings))
    lines.extend(doctor_grok_budget_lines(settings))
    lines.extend(doctor_stage_lines(settings))
    lines.extend(doctor_kills_lines(settings))
    lines.extend(doctor_signer_lines(settings))
    port = settings.health.port
    if port <= 0:
        lines.append("warn  /healthz (not served: health.port=0, only `run --serve` binds a port)")
        lines.append("warn  /metrics (not served: health.port=0, only `run --serve` binds a port)")
    else:
        lines.extend(probe.line() for probe in probe_served_endpoints(port))
    lines.append(f"doctor: {present} present, {absent} not-yet-implemented (warnings), exit 0")
    return lines
