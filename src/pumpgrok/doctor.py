"""`pumpgrok doctor`: subsystem health report (FOUND-013, R37).

A subsystem is `ok` when its module resolves. Subsystems whose owning phase has not landed
are reported as `warn ... not-yet-implemented`. `run --serve` additionally serves
`GET /healthz` and `GET /metrics` on 127.0.0.1; the doctor probes both with stdlib
`urllib` (no curl in slim images) and reports the result next to the subsystem lines.
Probe warnings never fail the report: exit 0 means the process started with valid settings.

`doctor --json` prints the mode-aware operator input inventory instead (ONB-01, ONB-02): one
record per input with its name, requirement, status and source, never a value. A missing
required input, or a forbidden input present, makes the verb exit nonzero.
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import os
import sqlite3
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pumpgrok.config.settings import Settings, current_profile
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


def doctor_report(settings: Settings) -> list[str]:
    """Lines for stdout: mode, subsystem lines, the ONB-08 RPC line, endpoint probes, summary."""
    statuses = subsystem_statuses()
    present = sum(1 for status in statuses if status.present)
    absent = len(statuses) - present
    lines = [f"info  mode={settings.effective_mode} profile={current_profile()}"]
    lines.extend(status.line() for status in statuses)
    lines.append(onb08_rpc_line())
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
    return any(
        name.startswith(WALLET_ENV_PREFIX) and environ[name].strip() for name in environ
    )


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
    decided = [scope for scope in scopes if scope in decisions and decisions[scope].bound]
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
