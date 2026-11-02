"""Trial ledger with promotion eligibility and typed rejection (BT-04).

CONTEXT D-06: above MAX_ELIGIBLE_TRIALS the verdict flags the result
ineligible for promotion; above MAX_ALLOWED_TRIALS recording is refused with
TooManyTrialsError, never stored. CONTEXT G-06: the ledger is JSONL at
var/backtest/RUNID/trials.jsonl with RUNID supplied by the caller.

The ledger is append-only and self-consistent: reopening the same path sees
the same trials in the same order, and a line that is undecodable,
mis-numbered, mistyped or inconsistent with the eligibility rule raises
CorruptState instead of being trusted. Pure local file I/O: no wall clock
(the verdict derives from the trial count), no randomness, no network.
"""

from __future__ import annotations

import fcntl
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pumpgrok.core.errors import CorruptState, PumpgrokError

MAX_ELIGIBLE_TRIALS = 20
MAX_ALLOWED_TRIALS = 50


class TooManyTrialsError(PumpgrokError):
    """Recording would pass MAX_ALLOWED_TRIALS. The trial is refused, never stored."""

    code = "too_many_trials"


@dataclass(frozen=True)
class TrialVerdict:
    """Outcome of one recorded trial: its 1-based number and promotion flag."""

    trial_number: int
    params_hash: str
    eligible_for_promotion: bool


_RECORD_KEYS = ("trial_number", "params_hash", "eligible_for_promotion")


def _record_of(verdict: TrialVerdict) -> dict[str, Any]:
    return {
        "trial_number": verdict.trial_number,
        "params_hash": verdict.params_hash,
        "eligible_for_promotion": verdict.eligible_for_promotion,
    }


def _read_ledger(path: Path) -> list[TrialVerdict]:
    if not path.exists():
        return []
    verdicts: list[TrialVerdict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise CorruptState(
                    "trials ledger holds a blank line",
                    file=str(path),
                    line=line_number,
                )
            try:
                data = json.loads(line)
            except json.JSONDecodeError as err:
                raise CorruptState(
                    "trials ledger holds an undecodable line",
                    file=str(path),
                    line=line_number,
                ) from err
            if not isinstance(data, dict) or set(data) != set(_RECORD_KEYS):
                raise CorruptState(
                    "trials ledger holds a malformed record",
                    file=str(path),
                    line=line_number,
                )
            number = data["trial_number"]
            params_hash = data["params_hash"]
            eligible = data["eligible_for_promotion"]
            if (
                not isinstance(number, int)
                or isinstance(number, bool)
                or number != line_number
                or not isinstance(params_hash, str)
                or not params_hash
                or not isinstance(eligible, bool)
                or eligible != (number <= MAX_ELIGIBLE_TRIALS)
            ):
                raise CorruptState(
                    "trials ledger holds an inconsistent record",
                    file=str(path),
                    line=line_number,
                )
            verdicts.append(
                TrialVerdict(
                    trial_number=number,
                    params_hash=params_hash,
                    eligible_for_promotion=eligible,
                )
            )
    return verdicts


class TrialLedger:
    """Append-only JSONL ledger of backtest trials for one run.

    path defaults to var/backtest/RUNID/trials.jsonl with RUNID supplied by
    the caller; pass an explicit path (tests do) to store it elsewhere.
    Reopening the same path loads the persisted trials, so the ledger
    round-trips.
    """

    def __init__(self, run_id: str, path: Path | None = None) -> None:
        if not run_id:
            raise ValueError("run_id must be a non-empty id")
        self._run_id = run_id
        self._path = path if path is not None else Path("var/backtest") / run_id / "trials.jsonl"
        self._trials = _read_ledger(self._path)

    @property
    def run_id(self) -> str:
        """Caller-supplied run id (RUNID in the default path)."""
        return self._run_id

    @property
    def path(self) -> Path:
        """Ledger file this instance appends to and loaded from."""
        return self._path

    @property
    def trials(self) -> tuple[TrialVerdict, ...]:
        """Every recorded trial, oldest first."""
        return tuple(self._trials)

    def __len__(self) -> int:
        return len(self._trials)

    def record_trial(self, params_hash: str) -> TrialVerdict:
        """Persist one trial and return its verdict.

        Trial numbers past MAX_ELIGIBLE_TRIALS flag eligible_for_promotion
        false; the trial past MAX_ALLOWED_TRIALS raises TooManyTrialsError
        and is never stored.

        The number is derived from the file as it stands under an exclusive
        flock held across the read, limit check and append, so instances that
        share a path never hand out the same number.
        """
        if not params_hash:
            raise ValueError("params_hash must be a non-empty digest")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                persisted = _read_ledger(self._path)
                trial_number = len(persisted) + 1
                if trial_number > MAX_ALLOWED_TRIALS:
                    raise TooManyTrialsError(
                        f"trial {trial_number} passes the {MAX_ALLOWED_TRIALS} trial limit",
                        run_id=self._run_id,
                        trial_number=trial_number,
                    )
                verdict = TrialVerdict(
                    trial_number=trial_number,
                    params_hash=params_hash,
                    eligible_for_promotion=trial_number <= MAX_ELIGIBLE_TRIALS,
                )
                handle.write(json.dumps(_record_of(verdict), sort_keys=True) + "\n")
                handle.flush()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        self._trials = [*persisted, verdict]
        return verdict
