"""desk.doctor: subsystem health as structured rows (TOOL-007).

``check`` runs the exact same :func:`doctor_report` code path as the
``pumpgrok doctor`` CLI and returns one structured row per subsystem plus a
mode row. ``register`` records the agent binding (HMAC-bound with the
``digest_*`` helpers). ``install_prompt`` and ``repair`` need seat-bound
prompt assembly, which is gateway work (Phase 4): they fail closed with a
row explaining why, instead of returning a faked prompt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from pumpgrok.config.settings import Settings
from pumpgrok.core.ids import ambient_correlation
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import Tool, ToolInput, ToolOutput, ToolSpec, tool
from pumpgrok.doctor import doctor_report, subsystem_statuses
from pumpgrok.tools._common import meta_now
from pumpgrok.tools.desk._tokens import digest_compare, digest_token

__all__ = [
    "DOCTOR_SPEC",
    "DoctorIn",
    "DoctorOut",
    "build_doctor_tool",
    "run_doctor",
]


class DoctorIn(ToolInput):
    """Doctor action; ``register`` binds an agent id to a channel."""

    action: Literal["check", "register", "install_prompt", "repair"]
    agent_uuid: str | None = None
    channel_id: str | None = None
    prompt_sha256: str | None = None
    installed_skills: list[str] = Field(default_factory=list)


class DoctorOut(ToolOutput):
    """One row per check; ``ok`` is False when any row fails."""

    ok: bool
    rows: list[dict] = Field(default_factory=list)


DOCTOR_SPEC = ToolSpec(
    name="desk.doctor",
    description=(
        "Check verifies prompt SHA, skills, roster, registry grants and that "
        "effective execution mode is paper; register records the agent id; "
        "install_prompt and repair are gateway work."
    ),
    input_model=DoctorIn,
    output_model=DoctorOut,
    side_effect=SideEffect.PAPER_WRITE,
    timeout_s=60.0,
    rate_limit_key="desk",
    idempotent=True,
    backend="pumpgrok.doctor.doctor_report",
)


def _check_rows(settings: Settings) -> tuple[bool, list[dict]]:
    statuses = subsystem_statuses()
    rows = [
        {
            "check": status.name,
            "status": "ok" if status.present else "warn",
            "detail": status.line(),
        }
        for status in statuses
    ]
    mode_ok = settings.effective_mode == "paper"
    rows.append(
        {
            "check": "effective_mode",
            "status": "ok" if mode_ok else "fail",
            "detail": f"effective_mode={settings.effective_mode}",
        }
    )
    lines = doctor_report(settings)
    rows.append(
        {
            "check": "doctor_report",
            "status": "ok" if lines else "fail",
            "detail": lines[-1] if lines else "doctor_report returned nothing",
        }
    )
    ok = all(row["status"] != "fail" for row in rows)
    return ok, rows


def _register_rows(
    inp: DoctorIn, bindings_dir: Path, binding_key: bytes
) -> tuple[bool, list[dict]]:
    if not inp.agent_uuid or not inp.channel_id:
        return False, [
            {
                "check": "register",
                "status": "fail",
                "detail": "register needs agent_uuid and channel_id",
            }
        ]
    binding = digest_token(inp.agent_uuid, inp.channel_id, key=binding_key)
    bindings_dir.mkdir(parents=True, exist_ok=True)
    record = bindings_dir / f"{inp.agent_uuid}.json"
    if record.is_file():
        stored = json.loads(record.read_text(encoding="utf-8"))
        ok = digest_compare(binding, str(stored.get("binding", "")))
        return ok, [
            {
                "check": "register",
                "status": "ok" if ok else "fail",
                "detail": "binding verified" if ok else "binding mismatch",
            }
        ]
    record.write_text(
        json.dumps(
            {"agent_uuid": inp.agent_uuid, "channel_id": inp.channel_id, "binding": binding}
        ),
        encoding="utf-8",
    )
    return True, [{"check": "register", "status": "ok", "detail": "binding recorded"}]


async def run_doctor(
    inp: DoctorIn, settings: Settings, bindings_dir: Path, binding_key: bytes
) -> dict:
    """Dispatch check/register; prompt assembly fails closed (Phase 4)."""
    if inp.action == "check":
        ok, rows = _check_rows(settings)
    elif inp.action == "register":
        ok, rows = _register_rows(inp, bindings_dir, binding_key)
    else:
        ok, rows = (
            False,
            [
                {
                    "check": inp.action,
                    "status": "fail",
                    "detail": f"{inp.action} needs seat-bound prompt assembly (Phase 4 gateway)",
                }
            ],
        )
    ambient = ambient_correlation()
    return DoctorOut.model_validate(
        {
            "ok": ok,
            "rows": rows,
            "meta": meta_now("desk", inp.correlation_id or (str(ambient) if ambient else None)),
        }
    ).model_dump()


def build_doctor_tool(settings: Settings, bindings_dir: Path, binding_key: bytes) -> Tool:
    """Bind ``desk.doctor`` to settings, a bindings dir and an HMAC key."""

    @tool(DOCTOR_SPEC)
    async def _doctor(payload: DoctorIn) -> dict:
        return await run_doctor(payload, settings, bindings_dir, binding_key)

    return _doctor
