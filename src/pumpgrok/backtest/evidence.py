"""BacktestEvidenceProvider for the promotion gate (BT-13; D-05/D-07).

Serves a persisted run record plus its grading verdict to the Phase 17
promotion gate. Given (strategy, param hash) it returns the run and
whether the dataset grades eligible; an unknown pair refuses (KeyError).
Fixture data never promotes: a run whose result kind is "fixture" grades
ineligible regardless of duration.
"""

from __future__ import annotations

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
