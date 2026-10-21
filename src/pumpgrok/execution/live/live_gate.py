"""The nine live preconditions, in order (paper-engine.md 7.2, R21, R31).

`LiveGate.evaluate()` reports every precondition, met or not; it never stops at the first
unmet one. `LiveGate.check()` returns the ids of the unmet ones, in order. The CLI runs the
gate whenever the effective mode is live and exits 3 before any other work.

Fail closed: this release has no source=paper metrics reader, no wallet allowlist or
notional cap setting, no confirmation verifier, no adapter implementation and no readable
halt, kill-switch or breaker state. Preconditions 3 to 9 therefore report unmet with the
reason naming what is missing. Precondition 8 is always unmet by design.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

PRECONDITION_IDS: tuple[str, ...] = (
    "mode_live",
    "live_enable_env",
    "min_paper_days",
    "performance_thresholds",
    "wallet_allowlist",
    "notional_cap",
    "confirmation_record",
    "adapter_registered",
    "no_active_stop",
)


@dataclass(frozen=True)
class Precondition:
    number: int
    id: str
    met: bool
    reason: str


class LiveGate:
    """Evaluates R21 against the effective mode, the environment and the working directory."""

    def __init__(self, *, mode: str, environ: Mapping[str, str], root: Path) -> None:
        self._mode = mode
        self._environ = environ
        self._root = root

    def evaluate(self) -> tuple[Precondition, ...]:
        paper_ledger = self._root / "var" / "ledger.sqlite"
        confirmation = self._root / "var" / "live_confirmation.json"
        mode_live = self._mode == "live"
        env_enabled = self._environ.get("PUMPGROK_LIVE_ENABLE", "").strip() == "1"
        paper_reason = (
            "no source=paper ledger at var/ledger.sqlite"
            if not paper_ledger.exists()
            else "paper-window metrics are not computed in this release"
        )
        rows: tuple[tuple[bool, str], ...] = (
            (
                mode_live,
                "effective mode is live" if mode_live else f"effective mode is {self._mode}",
            ),
            (
                env_enabled,
                "PUMPGROK_LIVE_ENABLE=1" if env_enabled else "PUMPGROK_LIVE_ENABLE is not 1",
            ),
            (False, paper_reason),
            (False, paper_reason),
            (False, "live.wallet_allowlist is not a setting in this release"),
            (False, "live.notional_cap_sol is not a setting in this release"),
            (
                False,
                "var/live_confirmation.json missing"
                if not confirmation.exists()
                else "confirmation record verifier is not built in this release",
            ),
            (False, "no live adapter implementation ships in this release"),
            (False, "halt, kill switch and breaker state are not readable in this release"),
        )
        return tuple(
            Precondition(number=index, id=name, met=met, reason=reason)
            for index, (name, (met, reason)) in enumerate(
                zip(PRECONDITION_IDS, rows, strict=True), start=1
            )
        )

    def check(self) -> list[str]:
        """Ids of every unmet precondition, in R21 order. Empty means the gate is open."""
        return [item.id for item in self.evaluate() if not item.met]


def refusal_lines(preconditions: Sequence[Precondition]) -> list[str]:
    """The stderr block for a refused live start: one line per unmet precondition."""
    unmet = [item for item in preconditions if not item.met]
    lines = [
        f"LIVE GATE: refusing to start in mode=live. {len(unmet)} of "
        f"{len(preconditions)} preconditions unmet:"
    ]
    lines.extend(f"  [ ] {item.number} {item.id} {item.reason}" for item in unmet)
    lines.append("Fix every unmet line or run in mode=paper. No transaction was attempted.")
    return lines
