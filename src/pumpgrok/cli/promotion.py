"""Harness-backed scheduled promotion check (UPG-05).

run_promotion_check searches the declared space (upgrade/space.py) over one recorded
dataset with the same holdout path as ``backtest``, takes the search winner alone, asks the
gate for a verdict on that winner, and hands the verdict to upgrade.scheduled.apply_candidate.
It acts only at the autonomous-paper level. A non-autonomous level, an empty space, or a
winner already active returns skipped and writes nothing. Any exception returns failed and
promotes nothing.

make_promotion_check wraps the check in a closure taking (store, clock). The closure runs the
check at most once per PROMOTION_CHECK_INTERVAL_S on the injected clock.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pumpgrok.backtest.divergence import check
from pumpgrok.backtest.evaluate import evaluated_settings_hash
from pumpgrok.backtest.harness import run_search
from pumpgrok.backtest.manifest import build_manifest, param_set_hash
from pumpgrok.backtest.split import holdout_split
from pumpgrok.cli.backtest import _backtest_dataset, _evaluate_holdout, _paper_gate, _run_lock
from pumpgrok.config.settings import ConfigError
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.active_set import read_active_set
from pumpgrok.ledger.autonomy import read_autonomy
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.replay.fixtures import event_epoch, load_dataset
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.upgrade.bounds import load_bounds
from pumpgrok.upgrade.gate import REQUIRED_AUTONOMY_LEVEL, evaluate_candidate
from pumpgrok.upgrade.params import ParamSet
from pumpgrok.upgrade.scheduled import (
    PROMOTION_CHECK_INTERVAL_S,
    CheckOutcome,
    apply_candidate,
    due,
    mark,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from pumpgrok.core.ids import Clock
    from pumpgrok.ledger.store import LedgerStore

__all__ = ["make_promotion_check", "run_promotion_check"]

log = logging.getLogger("pumpgrok.cli")

#: Provenance written on every scheduled promotion row (human rows keep their own prefix).
CHECK_BY = "gate:promotion-check"
CHECK_SOURCE = "replay"
CHECK_CORRELATION_ID = "upgrade-promotion-check"

_MAX_DETAIL_CHARS = 200


def _one_line(exc: BaseException) -> str:
    """Exception text on one bounded line, safe to put in a log field."""
    return " ".join(str(exc).split())[:_MAX_DETAIL_CHARS]


def _declared_params(space: Sequence[Mapping[str, Any]]) -> dict[str, ParamSet]:
    """Each declared mapping as its ParamSet, keyed by content hash so a winner maps back."""
    return {params.content_hash: params for params in (ParamSet(**dict(entry)) for entry in space)}


def _check_and_apply(
    store: LedgerStore,
    dataset_dir: str | Path,
    *,
    clock: Clock,
    space: Sequence[Mapping[str, Any]],
    seed: int,
    initial_equity_lamports: int,
) -> CheckOutcome:
    """Search the declared space, gate its winner alone, and apply the verdict."""
    spec = _backtest_dataset(str(dataset_dir))
    declared = _declared_params(space)
    risk_budget = RiskBudget()
    limits = EngineLimits()
    space_bytes = canonical_json({"candidates": [dict(entry) for entry in space]}).encode("utf-8")
    manifest = build_manifest(
        spec.ref,
        seed,
        evaluated_settings_hash(ParamSet().candidate(), risk_budget=risk_budget, limits=limits),
        param_set_hash(space_bytes),
    )
    events = load_dataset(spec.directory)
    stamps = tuple(event_epoch(event) for event in events.events)
    split = holdout_split(stamps, spec.name)
    run_dir = Path("var/backtest") / manifest.run_id
    holdout_ledger = run_dir / "holdout.sqlite"
    with _run_lock(run_dir):
        trials_path = run_dir / "trials.jsonl"
        if trials_path.exists():
            trials_path.unlink()
        search = run_search(
            spec.ref,
            space,
            len(space),
            seed,
            run_id=manifest.run_id,
            risk_budget=risk_budget,
            limits=limits,
            holdout_ledger_path=holdout_ledger,
        )
        winner = declared.get(search.best_params_hash)
        if winner is None:
            raise ConfigError(["promotion search winner is not in the declared space"])
        if read_active_set(store) == winner.content_hash:
            return "skipped"
        outcome = _evaluate_holdout(
            spec=spec,
            dataset=events,
            stamps=stamps,
            split=split,
            run_id=manifest.run_id,
            holdout_ledger=holdout_ledger,
            initial_fallback=initial_equity_lamports,
        )
        gate = _paper_gate(
            paper_ledger=str(store.path),
            dataset_name=spec.name,
            run_id=manifest.run_id,
            cutoff=split.holdout_start_ts,
            window_end=outcome.window_end_ts,
            elapsed_days=outcome.elapsed_days,
            initial_fallback=initial_equity_lamports,
            backtest_result=outcome.backtest_result,
            window_metrics=outcome.window_metrics,
            eligible=search.eligible_for_promotion,
        )
        if gate.paper_metrics is None:
            raise ConfigError(["promotion needs a paper summary to compare against"])
        bounds = load_bounds()
        verdict = evaluate_candidate(
            winner,
            bounds=bounds,
            search=search,
            run_id=manifest.run_id,
            store=store,
            backtest=outcome.window_metrics,
            paper=gate.paper_metrics,
        )
        return apply_candidate(
            store,
            verdict,
            candidate_hash=winner.content_hash,
            run_id=manifest.run_id,
            holdout_id=split.holdout_id,
            divergence=check(outcome.window_metrics, gate.paper_metrics),
            trial_count=search.trial_count,
            bounds=bounds,
            param_set=winner,
            by=CHECK_BY,
            ts_utc=format_ts_utc(clock.now()),
            source=CHECK_SOURCE,
            correlation_id=CHECK_CORRELATION_ID,
        )


def run_promotion_check(
    store: LedgerStore,
    dataset_dir: str | Path,
    *,
    clock: Clock,
    space: Sequence[Mapping[str, Any]],
    seed: int,
    initial_equity_lamports: int,
) -> CheckOutcome:
    """Run one promotion check over the declared space; return its outcome.

    skipped: the autonomy level is below autonomous-paper, the declared space is empty, or
    the search winner is already the active set. Nothing is written. failed: any exception;
    a structured line names its class, and nothing is promoted. promoted or escalated: the
    gate's verdict on the search winner was applied (see upgrade.scheduled.apply_candidate).
    """
    try:
        if read_autonomy(store) != REQUIRED_AUTONOMY_LEVEL:
            return "skipped"
        if not space:
            log.info("promotion_check outcome=skipped detail=no candidates declared")
            return "skipped"
        outcome = _check_and_apply(
            store,
            dataset_dir,
            clock=clock,
            space=space,
            seed=seed,
            initial_equity_lamports=initial_equity_lamports,
        )
    except Exception as exc:
        log.error(
            "promotion_check outcome=failed error=%s detail=%s",
            type(exc).__name__,
            _one_line(exc),
        )
        return "failed"
    log.info("promotion_check outcome=%s candidates=%d", outcome, len(space))
    return outcome


def make_promotion_check(
    dataset_dir: str | Path,
    *,
    space: Sequence[Mapping[str, Any]],
    seed: int,
    initial_equity_lamports: int,
) -> Callable[[LedgerStore, Clock], None]:
    """Return a closure taking (store, clock) that runs the check once per interval.

    The closure receives the serve's own store and clock on each tick. It checks due() first
    and returns at once when the interval has not passed. When it has, the closure runs
    run_promotion_check and then marks the clock time, so a skipped, promoted, escalated or
    failed check all wait one full interval.
    """

    def _promotion_check(store: LedgerStore, clock: Clock) -> None:
        if not due(store, clock, PROMOTION_CHECK_INTERVAL_S):
            return
        run_promotion_check(
            store,
            dataset_dir,
            clock=clock,
            space=space,
            seed=seed,
            initial_equity_lamports=initial_equity_lamports,
        )
        mark(store, clock)

    return _promotion_check
