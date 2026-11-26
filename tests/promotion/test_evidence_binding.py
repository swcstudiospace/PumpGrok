"""S-P2 (PRM-06): a gate verdict is applied only to the candidate its evidence was read for.

feed_promotion binds the verdict, the candidate hash and the evidence record in one value. A
candidate hash that differs from the params hash the evidence was read for is refused before
apply_candidate runs, so nothing is written.
"""

from __future__ import annotations

from typing import Any

import pytest

from pumpgrok.backtest import evidence as evidence_module
from pumpgrok.backtest.evidence import BacktestEvidenceProvider
from pumpgrok.upgrade.gate import GateVerdict

VERSION = "strategy-version-1"
PARAMS_HASH = "a" * 64
OTHER_HASH = "b" * 64

_PASS = GateVerdict(promotion_eligible=True, reason="pass", detail="eligible")
_ELIGIBLE_ROW: dict[str, Any] = {
    "grade": "promotion_eligible",
    "reasons": [],
    "dataset_digest": "digest-1",
    "result_id": "result-1",
}


class _RowStore:
    """Stands in for the sidecar: returns the stored rows for any version and params."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def rows_for(self, strategy_version_id: str, params_hash: str) -> list[dict[str, Any]]:
        return list(self._rows)


@pytest.fixture
def applied(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record every apply_candidate call instead of writing to a ledger."""
    calls: list[dict[str, Any]] = []

    def _record(store: object, verdict: GateVerdict, **kwargs: Any) -> str:
        calls.append({"verdict": verdict, **kwargs})
        return "promoted"

    monkeypatch.setattr(evidence_module, "apply_candidate", _record)
    return calls


def _feed(candidate_hash: str | None, rows: list[dict[str, Any]]) -> str:
    provider = BacktestEvidenceProvider(_RowStore(rows))  # type: ignore[arg-type]
    kwargs: dict[str, Any] = {"run_id": "run-1"}
    if candidate_hash is not None:
        kwargs["candidate_hash"] = candidate_hash
    return provider.feed_promotion(
        object(),
        _PASS,
        strategy_version_id=VERSION,
        params_hash=PARAMS_HASH,
        apply_kwargs=kwargs,
    )


def test_candidate_hash_differing_from_params_hash_writes_nothing(
    applied: list[dict[str, Any]],
) -> None:
    outcome = _feed(OTHER_HASH, [_ELIGIBLE_ROW])
    assert outcome == "refused"
    assert applied == []


def test_missing_candidate_hash_writes_nothing(applied: list[dict[str, Any]]) -> None:
    outcome = _feed(None, [_ELIGIBLE_ROW])
    assert outcome == "refused"
    assert applied == []


def test_matching_candidate_hash_with_eligible_evidence_applies_once(
    applied: list[dict[str, Any]],
) -> None:
    outcome = _feed(PARAMS_HASH, [_ELIGIBLE_ROW])
    assert outcome == "applied"
    assert len(applied) == 1
    assert applied[0]["verdict"] is _PASS
    assert applied[0]["candidate_hash"] == PARAMS_HASH


def test_absent_evidence_is_withheld_even_when_hashes_match(
    applied: list[dict[str, Any]],
) -> None:
    outcome = _feed(PARAMS_HASH, [])
    assert outcome == "withheld"
    assert applied == []
