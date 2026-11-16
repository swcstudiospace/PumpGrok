"""Read-only backtest evidence for the existing promotion path (BT-13).

``BacktestEvidenceProvider`` reads the sidecar and returns a grade, reasons,
dataset digest and result id, or an explicit absent record. It does not decide
promotion. A non-eligible grade is returned as research_only. Feeding the gate
calls ``apply_candidate`` (UPG-05) with the verdict ``upgrade/gate.py`` already
produced; this module defines no verdict of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pumpgrok.backtest.store import ResultStore
from pumpgrok.upgrade.gate import GateVerdict
from pumpgrok.upgrade.scheduled import apply_candidate

__all__ = ["BacktestEvidenceProvider", "EvidenceRecord"]

_ELIGIBLE = "promotion_eligible"
_RESEARCH = "research_only"
_ABSENT = "absent"
_NEVER_ELIGIBLE = frozenset({"synthetic", "hand_authored"})


@dataclass(frozen=True)
class EvidenceRecord:
    """One stored grade, or an explicit absent record. Never a gate decision."""

    grade: str
    reasons: tuple[str, ...]
    dataset_digest: str | None
    result_id: str | None
    absent: bool


class BacktestEvidenceProvider:
    """Read the sidecar. Writes nothing."""

    def __init__(self, store: ResultStore) -> None:
        self._store = store

    def evidence_for(self, strategy_version_id: str, params_hash: str) -> EvidenceRecord:
        """The first stored row for this version and params, or an absent record."""
        rows = self._store.rows_for(strategy_version_id, params_hash)
        if not rows:
            return EvidenceRecord(_ABSENT, (), None, None, True)
        return _record(rows[0])

    def feed_promotion(
        self,
        ledger_store: Any,
        verdict: GateVerdict,
        *,
        strategy_version_id: str,
        params_hash: str,
        apply_kwargs: dict[str, Any],
    ) -> str:
        """Hand an existing gate verdict to UPG-05, or withhold it.

        Research-only and absent evidence write nothing. A promotion-eligible
        record is not judged here: ``apply_candidate`` receives the verdict
        the gate already returned.
        """
        record = self.evidence_for(strategy_version_id, params_hash)
        if record.absent or record.grade != _ELIGIBLE:
            return "withheld"
        apply_candidate(ledger_store, verdict, **apply_kwargs)
        return "applied"


def _record(row: dict[str, Any]) -> EvidenceRecord:
    stored = row.get("grade")
    reasons = tuple(str(item) for item in row.get("reasons", ()))
    digest = row.get("dataset_digest")
    result_id = row.get("result_id")
    dataset_digest = digest if isinstance(digest, str) else None
    result = result_id if isinstance(result_id, str) else None
    if stored != _ELIGIBLE or _NEVER_ELIGIBLE & set(reasons):
        return EvidenceRecord(_RESEARCH, reasons, dataset_digest, result, False)
    return EvidenceRecord(_ELIGIBLE, reasons, dataset_digest, result, False)
