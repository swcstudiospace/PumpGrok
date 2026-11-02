"""Backtest verb: holdout evaluation, paper gating and report."""

from __future__ import annotations

import argparse
import fcntl
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pumpgrok.backtest.candidate import param_set_mapping
from pumpgrok.backtest.evaluate import CandidateParams, evaluated_settings_hash
from pumpgrok.backtest.harness import run_search
from pumpgrok.backtest.manifest import build_manifest, param_set_hash
from pumpgrok.backtest.report import build_report
from pumpgrok.backtest.report import render as render_backtest
from pumpgrok.backtest.split import holdout_split
from pumpgrok.backtest.trials import MAX_ALLOWED_TRIALS, MAX_ELIGIBLE_TRIALS
from pumpgrok.cli.backtest_holdout import (
    _Dataset,
    _evaluate_holdout,
    _fills_from_rows,
    _read_window_ledger,
    _rejection_fees,
    _row_stamp,
    _window_curve,
)
from pumpgrok.cli.backtest_paper_gate import _paper_gate, _paper_window
from pumpgrok.cli.errors import UsageError, _not_implemented, _say
from pumpgrok.cli.wiring import _repo_root
from pumpgrok.config.settings import ConfigError, Settings
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.fees import BASE_FEE_LAMPORTS, VENUE_FEE_BPS, FeeModel
from pumpgrok.replay.fixtures import event_epoch, load_dataset
from pumpgrok.risk.limits import EngineLimits

# Names that promotion.py and the backtest test suites import from this module. Their
# definitions live in backtest_holdout.py and backtest_paper_gate.py.
__all__ = [
    "_Dataset",
    "_evaluate_holdout",
    "_fills_from_rows",
    "_paper_gate",
    "_paper_window",
    "_read_window_ledger",
    "_rejection_fees",
    "_row_stamp",
    "_window_curve",
]

log = logging.getLogger("pumpgrok.cli")


def _backtest_dataset(raw: str) -> _Dataset:
    """Resolve a backtest fixture name or recording path to its dataset.

    Names resolve under tests/fixtures/replay; a directory path resolves
    only inside that tree. Anything else fails closed: the backtest path
    never fetches an external dataset over the network (CONTEXT D-04).
    """
    fixtures_root = (_repo_root() / "tests" / "fixtures" / "replay").resolve()
    candidate = Path(raw)
    if candidate.is_dir():
        resolved = candidate.resolve()
        try:
            resolved.relative_to(fixtures_root)
        except ValueError:
            raise ConfigError([f"backtest dataset outside recorded fixtures: {raw!r}"]) from None
        return _Dataset(name=resolved.name, ref=str(resolved), directory=resolved)
    bundled = fixtures_root / raw
    if not bundled.is_dir():
        raise ConfigError([f"unknown fixture dataset: {raw!r}"])
    return _Dataset(name=raw, ref=raw, directory=bundled)


def _backtest_params(raw: str | None) -> tuple[bytes, dict[str, Any]]:
    """Read parameter-set file bytes plus the mapping, or desk defaults.

    Absent means the desk default empty mapping. The file bytes feed the manifest
    identity through param_set_hash, and the mapping comes from param_set_mapping,
    so float leaves fail closed with a usage error instead of hashing ambiguously.
    """
    if raw is None:
        return (canonical_json({}).encode("utf-8"), {})
    try:
        data = Path(raw).read_bytes()
    except OSError as exc:
        raise ConfigError([f"unreadable --params file: {raw!r}"]) from exc
    try:
        parsed = param_set_mapping(data)
    except ValueError as exc:
        raise UsageError(
            f"bad --params {raw!r}: want a JSON mapping of ints, strings and bools; "
            "floats are refused"
        ) from exc
    return (data, parsed)


@contextmanager
def _run_lock(run_dir: Path) -> Iterator[None]:
    """Hold an exclusive lock on one run directory for the whole backtest.

    Identical inputs share a run directory, and a run deletes and rewrites
    its trial and holdout files. A second identical run while one is live
    would race on those files, so it is refused instead of waiting.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / ".lock").open("a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise UsageError(
                f"backtest run {run_dir.name} is already running in {run_dir}; "
                "wait for it to finish"
            ) from exc
        yield


def _backtest_verb(args: argparse.Namespace, settings: Settings) -> int:
    """Run one parameter set over the recorded dataset with the holdout (BT-06).

    ``--fixture`` names a recorded dataset (CONTEXT G-02), either a bundled
    fixture name or a recording directory inside the fixtures tree, and
    ``--params`` points at a parameter-set JSON file (CONTEXT G-03, desk
    defaults when absent); the mapping is validated through CandidateParams
    so unknown keys and inert scoring knobs fail closed. The verb records one
    trial in the trial ledger, replays the holdout window once under the
    winning overrides, summarizes the holdout fills into window metrics, and
    prints the deterministic Markdown report to stdout (CONTEXT G-01). Ledger
    writes are idempotent: rerunning identical inputs rewrites the identical
    trial and holdout ledger, so reruns stay byte-identical; a run whose
    identical twin is still live is refused. ``--paper-ledger`` points at a
    paper ledger sqlite whose FillRecorded rows build the same-window paper
    summary over the recording's span; SharedResult.compare enforces window
    equality before divergence.check gates promotion (PAP-02, G-08). Without
    it promotion stays ineligible with reason divergence not compared. This
    verb places no paper orders itself.
    """
    dataset = _backtest_dataset(str(args.fixture))
    params_data, params_mapping = _backtest_params(args.params)
    try:
        params = CandidateParams(**params_mapping)
    except ValidationError as exc:
        raise UsageError(
            "bad --params file: want filter/exits overrides validated against desk settings"
        ) from exc
    seed = settings.replay.seed
    # The replay evaluates desk defaults for the risk budget and engine limits, with the
    # candidate filter and exits overrides. The report identity covers exactly that set,
    # so operator overlays that the replay never reads stay out of it.
    risk_budget = RiskBudget()
    limits = EngineLimits()
    manifest = build_manifest(
        dataset.ref,
        seed,
        evaluated_settings_hash(params, risk_budget=risk_budget, limits=limits),
        param_set_hash(params_data),
    )
    events = load_dataset(dataset.directory)
    stamps = tuple(event_epoch(event) for event in events.events)
    split = holdout_split(stamps, dataset.name)
    cutoff = split.holdout_start_ts
    tuning_events = sum(1 for stamp in stamps if stamp < cutoff)
    holdout_events = len(stamps) - tuning_events
    run_dir = Path("var/backtest") / manifest.run_id
    holdout_ledger = run_dir / "holdout.sqlite"
    with _run_lock(run_dir):
        trials_path = run_dir / "trials.jsonl"
        if trials_path.exists():
            trials_path.unlink()
        harness_result = run_search(
            dataset.ref,
            [params_mapping],
            1,
            seed,
            run_id=manifest.run_id,
            risk_budget=risk_budget,
            limits=limits,
            holdout_ledger_path=holdout_ledger,
        )
        if harness_result.best_params_hash != params.content_hash:
            raise ConfigError(["backtest winner differs from the evaluated parameter set"])
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(
            canonical_json(manifest.model_dump(mode="json")) + "\n", encoding="utf-8"
        )
        outcome = _evaluate_holdout(
            spec=dataset,
            dataset=events,
            stamps=stamps,
            split=split,
            run_id=manifest.run_id,
            holdout_ledger=holdout_ledger,
            initial_fallback=settings.risk.paper_equity_lamports,
        )
        eligible = harness_result.eligible_for_promotion
        reasons: list[str] = []
        if not eligible:
            reasons.append(
                f"trial count {harness_result.trial_count} is past the promotion limit of "
                f"{MAX_ELIGIBLE_TRIALS}"
            )
        gate = _paper_gate(
            paper_ledger=args.paper_ledger,
            dataset_name=dataset.name,
            run_id=manifest.run_id,
            cutoff=cutoff,
            window_end=outcome.window_end_ts,
            elapsed_days=outcome.elapsed_days,
            initial_fallback=settings.risk.paper_equity_lamports,
            backtest_result=outcome.backtest_result,
            window_metrics=outcome.window_metrics,
            eligible=eligible,
        )
        reasons.extend(gate.reasons)
        fees = FeeModel()
        report = build_report(
            run_id=manifest.run_id,
            dataset=dataset.name,
            dataset_digest=manifest.dataset_digest,
            seed=seed,
            filter_settings_hash=manifest.filter_settings_hash,
            param_set_hash=manifest.param_set_hash,
            code_version=manifest.code_version,
            data_start_utc=outcome.data_start_utc,
            data_end_utc=outcome.data_end_utc,
            window_start_utc=outcome.window_start_utc,
            window_end_utc=outcome.window_end_utc,
            holdout_id=split.holdout_id,
            split_ids=(*split.train_ids, split.holdout_id),
            holdout_events=holdout_events,
            tuning_events=tuning_events,
            trial_count=harness_result.trial_count,
            max_eligible_trials=MAX_ELIGIBLE_TRIALS,
            max_allowed_trials=MAX_ALLOWED_TRIALS,
            eligible_for_promotion=eligible,
            promotion_eligible=gate.promotion_eligible,
            promotion_reason="; ".join(reasons),
            venue_fee_bps=VENUE_FEE_BPS,
            base_fee_lamports=BASE_FEE_LAMPORTS,
            network_cost_lamports=fees.network_cost(),
            fills=outcome.fills,
            metrics=outcome.window_metrics,
            elapsed_days=outcome.elapsed_days,
            paper_metrics=gate.paper_metrics,
            divergence_reasons=gate.divergence_reasons,
        )
        # Refused attempts paid fees that the cash curve already deducts, so the
        # realized fee total adds them to the fills' venue and network costs.
        report = replace(
            report,
            realized_fees_lamports_total=(
                report.realized_fees_lamports_total + outcome.rejected_fees_lamports
            ),
        )
        _say(sys.stdout, render_backtest(report))
    return gate.exit_code


def _replay_verb(args: argparse.Namespace, _settings: Settings) -> int:
    return _not_implemented(f"replay {args.cmd}")
