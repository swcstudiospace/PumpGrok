"""`pumpgrok doctor`: subsystem health report (FOUND-013, R37).

A subsystem is `ok` when its module resolves. Subsystems whose owning phase has not landed
are reported as `warn ... not-yet-implemented`. `run --serve` additionally serves
`GET /healthz` and `GET /metrics` on 127.0.0.1; the doctor probes both with stdlib
`urllib` (no curl in slim images) and reports the result next to the subsystem lines.
Probe warnings never fail the report: exit 0 means the process started with valid settings.

`doctor --json` prints the mode-aware operator input inventory instead (ONB-01, ONB-02): one
record per input with its name, requirement, status and source, never a value. A missing
required input, or a forbidden input present, makes the verb exit nonzero.

Installed Hermes cron jobs and host clock sync are reported too (EVT-13). Event mode is refused
(ConfigError) while a superseded job is enabled or a job store is unreadable; cadence mode only
reports them as info. A missing job store is a pass, never a skip.
"""

from __future__ import annotations

import ctypes
import http.client
import importlib.util
import json
import os
import sqlite3
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pumpgrok.config.sections.v4 import resolve_wake_mode
from pumpgrok.config.settings import ConfigError, Settings, current_profile
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH

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


def doctor_bus_lines(
    settings: Settings, *, depth: int | None = None, lanes: tuple[str, ...] = ()
) -> list[str]:
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


def doctor_grok_budget_lines(
    settings: Settings, *, windows: dict[str, str] | None = None
) -> list[str]:
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
        import os as _os  # noqa: PLC0415
        from pathlib import Path as _P  # noqa: PLC0415

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


def onb08_rpc_line(
    operator_dir: Path = oc.OPERATOR_DIR, ledger_path: Path = PAPER_LEDGER_PATH
) -> str:
    """ONB-08: the default RPC, or an explicit operator-authenticated endpoint choice."""
    try:
        status, endpoint = oc.rpc_status(operator_dir, ledger_path)
    except (oc.OperatorChoiceError, OSError, ValueError, sqlite3.Error) as exc:
        no_key = not (operator_dir / oc.KEY_NAME).exists()
        no_choices = not (operator_dir / oc.CHOICES_NAME).exists()
        if no_key and no_choices:
            # No key and no choices file: no operator choice can exist, so the default stands.
            return "ok    ONB-08 rpc=default (no operator key; no endpoint choice recorded)"
        return f"warn  ONB-08 rpc=unavailable: {exc}"
    if status == "explicit" and endpoint is not None:
        return f"ok    ONB-08 rpc=explicit endpoint={endpoint.label()} (operator-authenticated)"
    if status == "unbound":
        return "warn  ONB-08 rpc=unbound (choice not authenticated by the ledger; none in effect)"
    return "ok    ONB-08 rpc=default (no operator endpoint choice recorded)"


#: Superseded Hermes cron jobs (EVT-13): (stable id, installed name) from hermes/cron/jobs.yaml.
#: Installed jobs get Hermes-generated ids, so a job is matched by its stable id or its name.
SUPERSEDED_HERMES_JOBS: tuple[tuple[str, str], ...] = (
    ("scout-discover", "[bot:scout] discover"),
    ("risk-audit-open-leads", "[bot:risk] audit-open-leads"),
    ("chief-pickup", "[bot:chief] pickup"),
    ("rug-watch-paper", "[bot:rug] watch-paper"),
    ("chief-journal-rollup", "[bot:chief] journal-rollup"),
    ("scout-pipeline", "[bot:scout] pipeline"),
)


@dataclass(frozen=True)
class InstalledJobFindings:
    """Installed-state probe result: counts and job ids only, never prompts or values."""

    stores: int
    jobs: int
    superseded_active: tuple[str, ...]
    unreadable: tuple[str, ...]


def hermes_home_dir() -> Path:
    """The Hermes root: HERMES_HOME when set, else ~/.hermes (the Linux platform default)."""
    raw = os.environ.get("HERMES_HOME", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".hermes"


def _job_stores(home: Path) -> list[tuple[str, Path]]:
    """Existing cron stores: the default profile, then each named profile under profiles/."""
    candidates = [("default", home / "cron" / "jobs.json")]
    profiles = home / "profiles"
    if profiles.is_dir():
        candidates.extend(
            (child.name, child / "cron" / "jobs.json")
            for child in sorted(profiles.iterdir())
            if child.is_dir()
        )
    return [(label, path) for label, path in candidates if path.is_file()]


def _read_store(path: Path) -> list[dict[str, object]] | None:
    """Jobs in one store, or None when the store cannot be read (fail closed)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    if isinstance(jobs, dict):
        jobs = [
            {**value, "id": value.get("id") or key}
            for key, value in jobs.items()
            if isinstance(value, dict)
        ]
    if not isinstance(jobs, list) or not all(isinstance(job, dict) for job in jobs):
        return None
    return jobs


def _superseded_id(job: dict[str, object]) -> str | None:
    job_id = str(job.get("id") or "").strip()
    name = str(job.get("name") or "").strip()
    for stable_id, installed_name in SUPERSEDED_HERMES_JOBS:
        if job_id == stable_id or name == installed_name:
            return stable_id
    return None


def _is_active(job: dict[str, object]) -> bool:
    """Hermes is_job_runnable: enabled (default true) and carrying no pause marker."""
    paused = str(job.get("state") or "").strip() == "paused" or bool(job.get("paused_at"))
    return bool(job.get("enabled", True)) and not paused


def installed_job_findings() -> InstalledJobFindings:
    """Read every installed Hermes cron store that exists. A missing store is simply absent."""
    stores = _job_stores(hermes_home_dir())
    jobs_seen = 0
    active: set[str] = set()
    unreadable: list[str] = []
    for label, path in stores:
        jobs = _read_store(path)
        if jobs is None:
            unreadable.append(label)
            continue
        jobs_seen += len(jobs)
        for job in jobs:
            stable_id = _superseded_id(job)
            if stable_id is not None and _is_active(job):
                active.add(stable_id)
    return InstalledJobFindings(
        stores=len(stores),
        jobs=jobs_seen,
        superseded_active=tuple(sorted(active)),
        unreadable=tuple(unreadable),
    )


def event_mode_problems(findings: InstalledJobFindings) -> list[str]:
    """Why event mode is refused. Empty when event mode may start (EVT-13)."""
    problems = [
        f"superseded Hermes job {stable_id} is enabled; disable it before event mode"
        for stable_id in findings.superseded_active
    ]
    problems.extend(
        f"Hermes job store unreadable for profile {label}; event mode refused"
        for label in findings.unreadable
    )
    return problems


def hermes_jobs_line(findings: InstalledJobFindings) -> str:
    """Installed-state line. A pass when no store or no superseded job exists; never a skip."""
    if findings.unreadable:
        labels = ", ".join(findings.unreadable)
        return (
            f"info  hermes-jobs: store unreadable for profile {labels} "
            "(cadence; event mode refused)"
        )
    if findings.superseded_active:
        ids = ", ".join(findings.superseded_active)
        return f"info  hermes-jobs: superseded enabled: {ids} (cadence; event mode refused)"
    if findings.jobs == 0:
        return "ok    hermes-jobs: no installed jobs found (default profile)"
    return f"ok    hermes-jobs: {findings.jobs} installed, no superseded job enabled"


#: Linux `STA_UNSYNC` (linux/timex.h): set while the kernel clock is not NTP-synchronized.
_STA_UNSYNC = 0x0040


class _Timeval(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class _Timex(ctypes.Structure):
    """`struct timex` (linux/timex.h), 64-bit layout. Only `status` is read."""

    _fields_ = [
        ("modes", ctypes.c_uint),
        ("offset", ctypes.c_long),
        ("freq", ctypes.c_long),
        ("maxerror", ctypes.c_long),
        ("esterror", ctypes.c_long),
        ("status", ctypes.c_int),
        ("constant", ctypes.c_long),
        ("precision", ctypes.c_long),
        ("tolerance", ctypes.c_long),
        ("time", _Timeval),
        ("tick", ctypes.c_long),
        ("ppsfreq", ctypes.c_long),
        ("jitter", ctypes.c_long),
        ("shift", ctypes.c_int),
        ("stabil", ctypes.c_long),
        ("jitcnt", ctypes.c_long),
        ("calcnt", ctypes.c_long),
        ("errcnt", ctypes.c_long),
        ("stbcnt", ctypes.c_long),
        ("tai", ctypes.c_int),
        ("_reserved", ctypes.c_int * 11),
    ]


def _kernel_ntp_state() -> tuple[int, int]:
    """(return code, status bits) from adjtimex(2) with modes=0: a read-only query, no process."""
    libc = ctypes.CDLL(None)
    adjtimex = libc.adjtimex
    adjtimex.argtypes = [ctypes.POINTER(_Timex)]
    adjtimex.restype = ctypes.c_int
    state = _Timex()  # zeroed: modes == 0 asks for a read only
    rc: int = adjtimex(ctypes.byref(state))
    status: int = state.status
    return rc, status


def timedatectl_synchronized() -> bool | None:
    """NTP sync state as timedatectl reports it (kernel STA_UNSYNC): True, False, or None."""
    try:
        rc, status = _kernel_ntp_state()
    except (OSError, AttributeError):
        return None
    if rc == -1:
        return None
    return (status & _STA_UNSYNC) == 0


def clock_sync_line(probe: Callable[[], bool | None] | None = None) -> str:
    """Host clock sync, report only. Never warn: the fixed warn shapes stay unchanged."""
    synced = (timedatectl_synchronized if probe is None else probe)()
    if synced is True:
        return "ok    clock-sync (NTP synchronized)"
    if synced is False:
        return "info  clock-sync (not NTP-synchronized; wall clock may drift)"
    return "info  clock-sync (unknown: timedatectl unavailable)"


def doctor_report(settings: Settings, *, wake_mode: str | None = None) -> list[str]:
    """Lines for stdout: mode, subsystem lines, ONB-08, Hermes jobs, clock, probes, summary.

    Raises ConfigError when the resolved wake mode is event and a superseded Hermes job is
    enabled or a job store is unreadable (EVT-13). `wake_mode` is the `--wake-mode` value; None
    defers to settings.events.wake_mode.
    """
    findings = installed_job_findings()
    if resolve_wake_mode(wake_mode, settings.events.wake_mode) == "event":
        problems = event_mode_problems(findings)
        if problems:
            raise ConfigError(problems)
    statuses = subsystem_statuses()
    present = sum(1 for status in statuses if status.present)
    absent = len(statuses) - present
    lines = [f"info  mode={settings.effective_mode} profile={current_profile()}"]
    lines.extend(event_mode_refusal(resolve_wake_mode(wake_mode, settings.events.wake_mode)))
    lines.append(time_sync_probe())
    lines.extend(status.line() for status in statuses)
    lines.extend(doctor_bus_lines(settings))
    lines.extend(doctor_source_lines(settings))
    lines.extend(doctor_grok_budget_lines(settings))
    lines.extend(doctor_stage_lines(settings))
    lines.extend(doctor_kills_lines(settings))
    lines.extend(doctor_signer_lines(settings))
    lines.append(onb08_rpc_line())
    lines.append(hermes_jobs_line(findings))
    lines.append(clock_sync_line())
    port = settings.health.port
    if port <= 0:
        lines.append("warn  /healthz (not served: health.port=0, only `run --serve` binds a port)")
        lines.append("warn  /metrics (not served: health.port=0, only `run --serve` binds a port)")
    else:
        lines.extend(probe.line() for probe in probe_served_endpoints(port))
    lines.append(f"doctor: {present} present, {absent} not-yet-implemented (warnings), exit 0")
    return lines


# ONB-01 / ONB-02: the operator input inventory, per mode. Presence and source only.

INPUT_NAMES: tuple[str, ...] = (
    "xai_api_key",
    "wallet_public_address",
    "rpc_endpoint",
    "seat_tool_access",
    "hmac_confirmation_key",
)

REQUIRED = "required"
OPTIONAL = "optional"
FORBIDDEN = "forbidden"
NOT_READ = "not-read"

PRESENT = "present"
MISSING = "missing"
ABSENT = "absent"

#: Policy matrix. The x.ai key is also required in both modes when a Grok seat is enabled.
REQUIREMENTS: dict[str, dict[str, str]] = {
    "paper": {
        "xai_api_key": OPTIONAL,
        "wallet_public_address": NOT_READ,
        "rpc_endpoint": OPTIONAL,
        "seat_tool_access": REQUIRED,
        "hmac_confirmation_key": OPTIONAL,
    },
    "live": {
        "xai_api_key": OPTIONAL,
        "wallet_public_address": REQUIRED,
        "rpc_endpoint": REQUIRED,
        "seat_tool_access": REQUIRED,
        "hmac_confirmation_key": FORBIDDEN,
    },
}

HMAC_ENV = "PUMPGROK_CONFIRMATION_KEY"
WALLET_ENV_PREFIX = "PUMPGROK_WALLET"


@dataclass(frozen=True)
class InputRecord:
    """One inventory row: the input's name, requirement, status and source. Never its value."""

    name: str
    required_for_mode: str
    status: str
    source: str

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "required_for_mode": self.required_for_mode,
            "status": self.status,
            "source": self.source,
        }


def _status(required: str, present: bool) -> str:
    if present:
        return PRESENT
    return MISSING if required == REQUIRED else ABSENT


def _xai_record(settings: Settings, mode: str) -> InputRecord:
    required = REQUIREMENTS[mode]["xai_api_key"]
    if settings.grok_gateway.enabled:
        required = REQUIRED
    present = bool(settings.grok.api_key.get_secret_value())
    source = "env" if present else "none"
    return InputRecord("xai_api_key", required, _status(required, present), source)


def _wallet_env_set(environ: Mapping[str, str]) -> bool:
    return any(name.startswith(WALLET_ENV_PREFIX) and environ[name].strip() for name in environ)


def _wallet_record(settings: Settings, mode: str, environ: Mapping[str, str]) -> InputRecord:
    required = REQUIREMENTS[mode]["wallet_public_address"]
    if required == NOT_READ:
        # The paper path never reads the wallet input: neither the settings field nor any
        # PUMPGROK_WALLET* name is looked up here.
        return InputRecord("wallet_public_address", NOT_READ, NOT_READ, "none")
    present = bool(settings.wallet.allowlist)
    source = "none"
    if present:
        source = "env" if _wallet_env_set(environ) else "config"
    return InputRecord("wallet_public_address", required, _status(required, present), source)


def _rpc_record(mode: str) -> InputRecord:
    required = REQUIREMENTS[mode]["rpc_endpoint"]
    operator_dir = oc.OPERATOR_DIR
    try:
        status, _endpoint = oc.rpc_status(operator_dir, PAPER_LEDGER_PATH)
    except (oc.OperatorChoiceError, OSError, ValueError, sqlite3.Error):
        no_key = not (operator_dir / oc.KEY_NAME).exists()
        no_choices = not (operator_dir / oc.CHOICES_NAME).exists()
        if no_key and no_choices:
            return InputRecord("rpc_endpoint", required, _status(required, False), "default")
        return InputRecord("rpc_endpoint", required, MISSING, "none")
    if status == "explicit":
        return InputRecord("rpc_endpoint", required, PRESENT, "ledger")
    if status == "default":
        # An unselected RPC is the default, not the operator's consent.
        return InputRecord("rpc_endpoint", required, _status(required, False), "default")
    # Unbound: a recorded choice that the ledger does not authenticate, so none is in effect.
    return InputRecord("rpc_endpoint", required, MISSING, "none")


def _seat_record(mode: str) -> InputRecord:
    required = REQUIREMENTS[mode]["seat_tool_access"]
    try:
        scopes = [
            oc.tool_scope(seat, tool)
            for seat in EXPECTED_SEAT_IDS
            for tool in sorted(roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat))
        ]
        decisions = oc.read_authority(oc.OPERATOR_DIR, PAPER_LEDGER_PATH)
    except (oc.OperatorChoiceError, OSError, ValueError, sqlite3.Error):
        return InputRecord("seat_tool_access", required, MISSING, "none")
    decided = [scope for scope in scopes if scope in decisions and decisions[scope].allowed]
    complete = bool(scopes) and len(decided) == len(scopes)
    source = "ledger" if decided else "none"
    return InputRecord("seat_tool_access", required, _status(required, complete), source)


def _hmac_record(mode: str, environ: Mapping[str, str]) -> InputRecord:
    required = REQUIREMENTS[mode]["hmac_confirmation_key"]
    present = bool(environ.get(HMAC_ENV, "").strip())
    source = "env" if present else "none"
    return InputRecord("hmac_confirmation_key", required, _status(required, present), source)


def input_inventory(
    settings: Settings, mode: str, *, environ: Mapping[str, str] | None = None
) -> list[InputRecord]:
    """Every operator input for ``mode``, in INPUT_NAMES order, with its requirement and status."""
    if mode not in REQUIREMENTS:
        raise ValueError(f"unknown mode: {mode!r}")
    env: Mapping[str, str] = os.environ if environ is None else environ
    return [
        _xai_record(settings, mode),
        _wallet_record(settings, mode, env),
        _rpc_record(mode),
        _seat_record(mode),
        _hmac_record(mode, env),
    ]


def failing_inputs(records: Sequence[InputRecord]) -> list[InputRecord]:
    """Inputs that fail the mode: a required input not present, or a forbidden input present."""
    return [
        record
        for record in records
        if (record.required_for_mode == REQUIRED and record.status != PRESENT)
        or (record.required_for_mode == FORBIDDEN and record.status == PRESENT)
    ]


def inventory_json(records: Sequence[InputRecord]) -> str:
    """One JSON record per input: name, required_for_mode, status and source. No values."""
    return json.dumps([record.as_dict() for record in records], indent=2)
