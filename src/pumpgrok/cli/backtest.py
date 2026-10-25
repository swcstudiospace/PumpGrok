"""Backtest verb: holdout evaluation, paper gating and report."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pumpgrok.backtest.divergence import breach_line, check, enforce
from pumpgrok.backtest.evaluate import CandidateParams, evaluate_window, fold_windows
from pumpgrok.backtest.harness import run_search
from pumpgrok.backtest.manifest import build_manifest, filter_settings_hash, param_set_hash
from pumpgrok.backtest.metrics import MetricsContext, MetricsReport, summarize
from pumpgrok.backtest.report import build_report
from pumpgrok.backtest.report import render as render_backtest
from pumpgrok.backtest.results import SharedResult
from pumpgrok.backtest.split import HoldoutSplit, holdout_split
from pumpgrok.backtest.trials import MAX_ALLOWED_TRIALS, MAX_ELIGIBLE_TRIALS
from pumpgrok.cli.codes import EXIT_OK
from pumpgrok.cli.errors import UsageError, _not_implemented, _say, _tool_error
from pumpgrok.cli.wiring import _repo_root
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.core.adapter import Fill, FillStatus
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.execution.fees import BASE_FEE_LAMPORTS, VENUE_FEE_BPS, FeeModel
from pumpgrok.replay.clock import format_ts_utc, parse_ts_utc
from pumpgrok.replay.fixtures import FixtureDataset, event_epoch, load_dataset

log = logging.getLogger("pumpgrok.cli")


def _backtest_dataset(raw: str) -> tuple[str, Path]:
    """Resolve a backtest fixture name to its name and directory.

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
        return (resolved.name, resolved)
    bundled = fixtures_root / raw
    if not bundled.is_dir():
        raise ConfigError([f"unknown fixture dataset: {raw!r}"])
    return (raw, bundled)


def _backtest_params(raw: str | None) -> tuple[bytes, dict[str, Any]]:
    """Read parameter-set file bytes plus the mapping, or desk defaults.

    Absent means the desk default empty mapping. The file bytes are the
    hash input (CONTEXT G-03); the mapping must be JSON-stable, so float
    leaves fail closed instead of hashing ambiguously.
    """
    if raw is None:
        return (canonical_json({}).encode("utf-8"), {})
    try:
        data = Path(raw).read_bytes()
    except OSError as exc:
        raise ConfigError([f"unreadable --params file: {raw!r}"]) from exc
    try:
        parsed: Any = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise UsageError(f"bad --params {raw!r}: want a JSON mapping file") from exc
    if not isinstance(parsed, dict):
        raise UsageError(f"bad --params {raw!r}: want a JSON mapping file")
    return (data, parsed)


def _read_window_ledger(ledger_path: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Every row plus the initial-equity meta of one ledger, read-only.

    LedgerStore.read documents itself read-only: no locks, no chain
    mutation. This helper owns open and close around the read.
    """
    store = LedgerStore(ledger_path)
    try:
        rows = store.read(limit=None)
        meta = store.get_meta("initial_equity_lamports")
    finally:
        store.close()
    return (rows, meta)


def _fills_from_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[Fill], list[Decimal], list[int]]:
    """Fills, confirmation latencies and cash deltas from ledger rows.

    Only FillRecorded rows become fills; other row types never filled.
    Cash deltas are the recorded per-fill cash movement in row order, so
    only FillRecorded costs enter the curve. Fail closed: a fill row
    without a payload mapping, with non-integer money, or with ids the
    Fill model rejects raises ConfigError.
    """
    fills: list[Fill] = []
    latencies: list[Decimal] = []
    deltas: list[int] = []
    money_fields = (
        "filled_lamports",
        "filled_units",
        "realised_slippage_bps",
        "venue_fee_lamports",
        "network_cost_lamports",
        "cash_delta_lamports",
    )
    for row in rows:
        if row.get("type") != "FillRecorded":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            raise ConfigError(["backtest ledger holds a fill row without a payload mapping"])
        try:
            money: dict[str, int] = {}
            for name in money_fields:
                raw_amount = payload.get(name, 0)
                if not isinstance(raw_amount, int) or isinstance(raw_amount, bool):
                    raise ValueError(f"fill row carries non-integer {name}")
                money[name] = raw_amount
            fraction = Decimal(str(payload["filled_fraction"]))
            status = FillStatus.FILLED if fraction >= 1 else FillStatus.PARTIAL
            fills.append(
                Fill(
                    order_id=str(payload["order_id"]),
                    decision_id=str(payload["decision_id"]),
                    status=status,
                    venue_tx_ref=str(payload["venue_tx_ref"]),
                    filled_lamports=money["filled_lamports"],
                    filled_units=money["filled_units"],
                    filled_fraction=fraction,
                    price_avg=Decimal(str(payload["price_avg"])),
                    realised_slippage_bps=money["realised_slippage_bps"],
                    venue_fee_lamports=money["venue_fee_lamports"],
                    network_cost_lamports=money["network_cost_lamports"],
                    route=str(payload.get("route", "curve")),
                    ledger_seq=int(row["seq"]),
                )
            )
            latencies.append(Decimal(str(payload.get("latency_s", "0"))))
            deltas.append(money["cash_delta_lamports"])
        except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
            raise ConfigError(["backtest ledger holds an unusable fill row"]) from exc
    return (fills, latencies, deltas)


def _row_in_window(row: Mapping[str, Any], cutoff: float) -> bool:
    """Half-open window test for one paper ledger row: cutoff in, end open."""
    if row.get("type") != "FillRecorded":
        return False
    try:
        stamp = parse_ts_utc(str(row["ts_utc"]))
    except (ValueError, TypeError) as exc:
        raise ConfigError(["paper ledger holds a row with an unusable timestamp"]) from exc
    return stamp >= cutoff


def _window_curve(initial: int, cash_deltas: Sequence[int]) -> tuple[int, ...]:
    """Realized equity after each fill: genesis plus cumulative cash deltas.

    Cash deltas are recorded per fill in row order, so the curve reflects
    realized cash only; open-position marks stay invisible between fills
    by construction.
    """
    running = initial
    curve: list[int] = []
    for delta in cash_deltas:
        running += delta
        curve.append(running)
    return tuple(curve)


@dataclass(frozen=True)
class _HoldoutOutcome:
    """Evaluated holdout window: fills, metrics and report identity."""

    fills: list[Fill]
    latencies: list[Decimal]
    window_metrics: MetricsReport
    backtest_result: SharedResult
    elapsed_days: Decimal
    data_start_utc: str
    data_end_utc: str
    window_start_utc: str
    window_end_utc: str


@dataclass(frozen=True)
class _PaperOutcome:
    """Paper-gate result: summaries, promotion flag, reason text, exit code."""

    paper_metrics: MetricsReport | None
    divergence_reasons: tuple[str, ...]
    promotion_eligible: bool
    reasons: tuple[str, ...]
    exit_code: int


def _evaluate_holdout(
    *,
    fixture_name: str,
    dataset: FixtureDataset,
    stamps: tuple[float, ...],
    split: HoldoutSplit,
    params: CandidateParams,
    seed: int,
    run_id: str,
    run_dir: Path,
    initial_fallback: int,
) -> _HoldoutOutcome:
    """Replay the holdout window once and summarize its fills (BT-05, BT-06).

    The window comes from fold_windows with the same fold count the search
    used, so tuning never reads past the cutoff; the identity check against
    the split fails closed on drift. Fills rebuild from the recorded
    FillRecorded rows, the equity curve cumulates their cash deltas from
    genesis, and the span between the first and last window event sets the
    elapsed days. The shared result carries the same window bounds the
    paper comparison enforces.
    """
    cutoff = split.holdout_start_ts
    windows = fold_windows(stamps, fixture_name, 3)
    holdout_window = windows.holdout
    if holdout_window.window_id != split.holdout_id:
        raise ConfigError(["backtest holdout window identity drifted"])
    holdout_ledger = run_dir / "holdout.sqlite"
    evaluate_window(
        fixture_name, params, seed=seed, ledger_path=holdout_ledger, window=holdout_window
    )
    rows, meta = _read_window_ledger(holdout_ledger)
    fills, latencies, cash_deltas = _fills_from_rows(rows)
    initial = int(meta) if meta is not None else initial_fallback
    events = dataset.events
    window_points = [
        (event_epoch(event), str(event["ts_utc"]))
        for event in events
        if event_epoch(event) >= cutoff
    ]
    if window_points:
        window_start_utc = window_points[0][1]
        window_end_utc = window_points[-1][1]
        first_stamp = window_points[0][0]
        last_stamp = window_points[-1][0]
    else:
        window_start_utc = format_ts_utc(cutoff)
        window_end_utc = format_ts_utc(cutoff)
        first_stamp = cutoff
        last_stamp = cutoff
    if last_stamp > first_stamp:
        elapsed_days = (Decimal(str(last_stamp)) - Decimal(str(first_stamp))) / Decimal(86400)
    else:
        elapsed_days = Decimal(0)
    window_metrics = summarize(
        fills,
        MetricsContext(
            initial_equity_lamports=initial,
            equity_curve_lamports=_window_curve(initial, cash_deltas),
            elapsed_days=elapsed_days,
        ),
    )
    backtest_result = SharedResult.from_fills(
        run_id=run_id,
        dataset=fixture_name,
        window_start_ts=cutoff,
        window_end_ts=float("inf"),
        fills=fills,
        latencies=latencies,
    )
    return _HoldoutOutcome(
        fills=fills,
        latencies=latencies,
        window_metrics=window_metrics,
        backtest_result=backtest_result,
        elapsed_days=elapsed_days,
        data_start_utc=str(events[0]["ts_utc"]),
        data_end_utc=str(events[-1]["ts_utc"]),
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
    )


def _paper_gate(
    *,
    paper_ledger: str | None,
    fixture_name: str,
    run_id: str,
    cutoff: float,
    elapsed_days: Decimal,
    initial_fallback: int,
    backtest_result: SharedResult,
    window_metrics: MetricsReport,
    eligible: bool,
) -> _PaperOutcome:
    """Same-window paper comparison and the D7 promotion gate (PAP-02, G-08).

    Without a paper ledger path promotion stays ineligible with reason
    divergence not compared. With one, the paper FillRecorded rows over
    the same window build the paper summary, SharedResult.compare
    enforces window equality before divergence.check, and a breach
    prints the DIVERGENCE BREACH line on stderr and exits 1 via
    enforce. Promotion is eligible only when trials are within limit
    and the verdict passes.
    """
    if paper_ledger is None:
        return _PaperOutcome(None, (), False, ("divergence not compared",), EXIT_OK)
    paper_file = Path(paper_ledger)
    if not paper_file.is_file():
        raise UsageError(f"bad --paper-ledger {paper_ledger!r}: want a ledger sqlite file")
    paper_rows, paper_meta = _read_window_ledger(paper_file)
    paper_window_rows = [row for row in paper_rows if _row_in_window(row, cutoff)]
    paper_fills, _, paper_deltas = _fills_from_rows(paper_window_rows)
    paper_initial = int(paper_meta) if paper_meta is not None else initial_fallback
    paper_metrics = summarize(
        paper_fills,
        MetricsContext(
            initial_equity_lamports=paper_initial,
            equity_curve_lamports=_window_curve(paper_initial, paper_deltas),
            elapsed_days=elapsed_days,
        ),
    )
    paper_result = SharedResult.from_ledger_rows(
        run_id=run_id,
        dataset=fixture_name,
        window_start_ts=cutoff,
        window_end_ts=float("inf"),
        rows=paper_rows,
    )
    backtest_result.compare(paper_result)
    verdict = check(window_metrics, paper_metrics)
    if verdict.blocks_promotion:
        line = breach_line(verdict)
        if line is None:
            raise ConfigError(["divergence verdict blocks without a breach line"])
        _say(sys.stderr, line)
        return _PaperOutcome(
            paper_metrics,
            verdict.reasons,
            False,
            ("divergence breach: " + "|".join(verdict.reasons),),
            enforce(verdict),
        )
    if eligible:
        return _PaperOutcome(
            paper_metrics,
            verdict.reasons,
            True,
            ("trial count within limit and paper divergence within D7 defaults",),
            EXIT_OK,
        )
    return _PaperOutcome(paper_metrics, verdict.reasons, False, (), EXIT_OK)


def _backtest_verb(args: argparse.Namespace, settings: Settings) -> int:
    """Run one parameter set over the recorded dataset with the holdout (BT-06).

    ``--fixture`` names a recorded dataset (CONTEXT G-02) and ``--params``
    points at a parameter-set JSON file (CONTEXT G-03, desk defaults when
    absent); the mapping is validated through CandidateParams so unknown
    keys and inert scoring knobs fail closed. The verb records one trial
    in the trial ledger, replays the holdout window once under the winning
    overrides, summarizes the holdout fills into window metrics, and prints
    the deterministic Markdown report to stdout (CONTEXT G-01). Ledger
    writes are idempotent: rerunning identical inputs rewrites the
    identical trial and holdout ledger, so reruns stay byte-identical.
    ``--paper-ledger`` points at a paper ledger sqlite whose FillRecorded
    rows build the same-window paper summary; SharedResult.compare
    enforces window equality before divergence.check gates promotion
    (PAP-02, G-08). Without it promotion stays ineligible with reason
    divergence not compared. This verb places no paper orders itself.
    """
    fixture_name, dataset_dir = _backtest_dataset(str(args.fixture))
    params_data, params_mapping = _backtest_params(args.params)
    try:
        params = CandidateParams(**params_mapping)
    except ValidationError as exc:
        raise UsageError(
            "bad --params file: want filter/exits overrides validated against desk settings"
        ) from exc
    seed = settings.replay.seed
    manifest = build_manifest(
        fixture_name,
        seed,
        filter_settings_hash(settings.filter),
        param_set_hash(params_data),
    )
    dataset = load_dataset(dataset_dir)
    stamps = tuple(event_epoch(event) for event in dataset.events)
    split = holdout_split(stamps, fixture_name)
    cutoff = split.holdout_start_ts
    tuning_events = sum(1 for stamp in stamps if stamp < cutoff)
    holdout_events = len(stamps) - tuning_events
    run_dir = Path("var/backtest") / manifest.run_id
    trials_path = run_dir / "trials.jsonl"
    if trials_path.exists():
        trials_path.unlink()
    try:
        harness_result = run_search(fixture_name, [params_mapping], 1, seed, run_id=manifest.run_id)
    except TypeError as exc:
        raise UsageError("bad --params file: want JSON-stable ints and strings") from exc
    manifest_path = run_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        canonical_json(manifest.model_dump(mode="json")) + "\n", encoding="utf-8"
    )
    outcome = _evaluate_holdout(
        fixture_name=fixture_name,
        dataset=dataset,
        stamps=stamps,
        split=split,
        params=params,
        seed=seed,
        run_id=manifest.run_id,
        run_dir=run_dir,
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
        fixture_name=fixture_name,
        run_id=manifest.run_id,
        cutoff=cutoff,
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
        dataset=fixture_name,
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
    _say(sys.stdout, render_backtest(report))
    return gate.exit_code


def _replay_verb(args: argparse.Namespace, _settings: Settings) -> int:
    return _not_implemented(f"replay {args.cmd}")
