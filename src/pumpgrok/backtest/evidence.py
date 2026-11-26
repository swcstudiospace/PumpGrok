<<<<<<< HEAD
"""BacktestEvidenceProvider for the promotion gate (BT-13; D-05/D-07).

Serves a persisted run record plus its grading verdict to the Phase 17
promotion gate. Given (strategy, param hash) it returns the run and
whether the dataset grades eligible; an unknown pair refuses (KeyError).
Fixture data never promotes: a run whose result kind is "fixture" grades
ineligible regardless of duration.
=======
"""Read-only backtest evidence for the existing promotion path (BT-13).

``BacktestEvidenceProvider`` reads the sidecar and returns a grade, reasons,
dataset digest and result id, or an explicit absent record. It does not decide
promotion. A non-eligible grade is returned as research_only. Feeding the gate
calls ``apply_candidate`` (UPG-05) with the verdict ``upgrade/gate.py`` already
produced; this module defines no verdict of its own.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
from typing import Any

from pumpgrok.backtest.store import RunStore

__all__ = ["BacktestEvidenceProvider"]


class BacktestEvidenceProvider:
    """Gate-readable evidence over persisted backtest runs."""

    def __init__(self, store: RunStore) -> None:
        self._store = store

    def get(self, strategy_id: str, param_hash: str) -> dict[str, Any]:
        """Persisted run record plus grading verdict for one (strategy, param hash).

        Refuses unknown pairs with KeyError. Fixture-kind runs never
        promote (D-05).
        """
        for record in self._store.load_all():
            if (
                record.get("strategy_id") == strategy_id
                and record.get("param_hash") == param_hash
                and record.get("kind") == "run"
            ):
                result = dict(record.get("result") or {})
                eligible = bool(result.get("eligible"))
                kind = str(result.get("kind", ""))
                if kind in ("fixture", "traded_only", "hand-authored"):
                    eligible = False
                return {
                    "record": record,
                    "eligible": eligible,
                    "reasons": list(result.get("reasons", [])),
                }
        raise KeyError(f"no persisted run for {strategy_id!r}:{param_hash!r}")
=======
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


@dataclass(frozen=True)
class _PromotionBinding:
    """One promotion decision: the gate verdict, the candidate it names and the evidence read.

    Built only inside feed_promotion. The three values are checked together before any write,
    so a verdict cannot reach apply_candidate for a candidate other than the one its evidence
    was read for.
    """

    verdict: GateVerdict
    candidate_hash: str | None
    params_hash: str
    evidence: EvidenceRecord

    def refusal(self) -> str | None:
        """Why this binding may not be written, or None when it may."""
        if self.evidence.absent or self.evidence.grade != _ELIGIBLE:
            return "withheld"
        if self.candidate_hash is None or self.candidate_hash != self.params_hash:
            return "refused"
        return None


def _candidate_of(apply_kwargs: dict[str, Any]) -> str | None:
    candidate = apply_kwargs.get("candidate_hash")
    return candidate if isinstance(candidate, str) else None


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
        """Hand an existing gate verdict to UPG-05, or withhold or refuse it.

        Research-only and absent evidence are withheld. A candidate hash that is
        missing or differs from params_hash is refused. Nothing is written in either
        case. A promotion-eligible record is not judged here: ``apply_candidate``
        receives the verdict the gate already returned.
        """
        binding = _PromotionBinding(
            verdict=verdict,
            candidate_hash=_candidate_of(apply_kwargs),
            params_hash=params_hash,
            evidence=self.evidence_for(strategy_version_id, params_hash),
        )
        refusal = binding.refusal()
        if refusal is not None:
            return refusal
        apply_candidate(ledger_store, binding.verdict, **apply_kwargs)
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
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
