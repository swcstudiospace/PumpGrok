"""`pumpgrok doctor`: subsystem health report (FOUND-013, R37).

A subsystem is `ok` when its module resolves. Subsystems whose owning phase has not landed
are reported as `warn ... not-yet-implemented`. Warnings never fail the report: the
container HEALTHCHECK runs this command (plan 01-09), so exit 0 means the process started
with valid settings.
"""

from __future__ import annotations

import importlib.util
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
    """Lines for stdout: effective mode, one status line per subsystem, and a summary."""
    statuses = subsystem_statuses()
    present = sum(1 for status in statuses if status.present)
    absent = len(statuses) - present
    lines = [f"info  mode={settings.effective_mode} profile={current_profile()}"]
    lines.extend(status.line() for status in statuses)
    lines.append(f"doctor: {present} present, {absent} not-yet-implemented (warnings), exit 0")
    return lines
