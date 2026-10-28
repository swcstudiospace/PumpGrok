"""Backtest verb: holdout evaluation, paper gating and report."""

from __future__ import annotations

import argparse
import fcntl
import logging
import math
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pumpgrok.backtest.candidate import param_set_mapping
from pumpgrok.backtest.divergence import breach_line, check, enforce
from pumpgrok.backtest.equity import equity_lamports
from pumpgrok.backtest.evaluate import CandidateParams, evaluated_settings_hash, fold_windows
from pumpgrok.backtest.harness import run_search
from pumpgrok.backtest.manifest import build_manifest, param_set_hash
from pumpgrok.backtest.metrics import MetricsContext, MetricsReport, summarize
from pumpgrok.backtest.report import build_report
from pumpgrok.backtest.report import render as render_backtest
from pumpgrok.backtest.results import SharedResult
from pumpgrok.backtest.split import HoldoutSplit, holdout_split
from pumpgrok.backtest.trials import MAX_ALLOWED_TRIALS, MAX_ELIGIBLE_TRIALS
from pumpgrok.cli.codes import EXIT_OK
from pumpgrok.cli.errors import UsageError, _not_implemented, _say
from pumpgrok.cli.wiring import _repo_root
from pumpgrok.config.settings import ConfigError, Settings
from pumpgrok.core.adapter import Fill, FillStatus
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.fees import BASE_FEE_LAMPORTS, VENUE_FEE_BPS, FeeModel
from pumpgrok.ledger.reducer import LedgerState, initial_state, reduce
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import format_ts_utc, parse_ts_utc
from pumpgrok.replay.fixtures import FixtureDataset, event_epoch, load_dataset
from pumpgrok.risk.limits import EngineLimits

log = logging.getLogger("pumpgrok.cli")


@dataclass(frozen=True)
class _Dataset:
    """One backtest dataset: report name, replay reference and directory.

    name labels the report and the holdout and fold ids. ref is the identity
    string the manifest, the search and the window replays resolve: the
    fixture name for a bundled dataset, the resolved directory for a recording
    path. directory is that same location as a path, read by load_dataset.
    """

    name: str
    ref: str
    directory: Path


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
) -> tuple[list[Fill], list[Decimal]]:
    """Fills and confirmation latencies from ledger rows, in ledger order.

    Only FillRecorded rows become fills; other row types never filled.
    Forced closes (graduation, blind flatten) record an empty decision_id
    because no order decision caused them; their Fill keeps that empty
    decision rather than inventing one. Fail closed: a fill row without a
    payload mapping, with non-integer money, or with ids the Fill model
    rejects raises ConfigError.
    """
    fills: list[Fill] = []
    latencies: list[Decimal] = []
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
            order_id = str(payload["order_id"])
            decision_id = str(payload["decision_id"])
            fill = Fill(
                order_id=order_id,
                # Fill validates decision_id as a ULID, so a forced close passes the
                # order id through the constructor and then takes the recorded empty value.
                decision_id=decision_id or order_id,
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
            if not decision_id:
                fill = fill.model_copy(update={"decision_id": ""})
            fills.append(fill)
            latencies.append(Decimal(str(payload.get("latency_s", "0"))))
        except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
            raise ConfigError(["backtest ledger holds an unusable fill row"]) from exc
    return (fills, latencies)


def _rejection_fees(rows: Sequence[Mapping[str, Any]]) -> int:
    """Fees paid by refused attempts: the OrderRejected fees in the rows.

    The reducer deducts these from cash, so they are real cost even though
    no fill exists for them. Fail closed on a rejection row without a
    payload mapping or with non-integer fees.
    """
    total = 0
    for row in rows:
        if row.get("type") != "OrderRejected":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            raise ConfigError(["backtest ledger holds a rejection row without a payload mapping"])
        fees = payload.get("fees_lamports", 0)
        if not isinstance(fees, int) or isinstance(fees, bool) or fees < 0:
            raise ConfigError(["backtest ledger holds a rejection row with unusable fees"])
        total += fees
    return total


def _row_stamp(row: Mapping[str, Any]) -> float:
    """Epoch stamp of one ledger row; an unusable timestamp fails closed."""
    try:
        return parse_ts_utc(str(row["ts_utc"]))
    except (KeyError, ValueError, TypeError) as exc:
        raise ConfigError(["paper ledger holds a row with an unusable timestamp"]) from exc


def _window_curve(genesis: LedgerState, rows: Sequence[Mapping[str, Any]]) -> tuple[int, ...]:
    """Equity after each fill, folding every row of the window in ledger order.

    Each fill's point is taken when the next fill begins or the window ends,
    so the settlement rows that follow a fill (position opened or closed,
    marks, refused attempts) count toward it. The final point is therefore
    the equity at window end. There is one point per FillRecorded row, the
    same count the fill list pairs with.
    """
    state = genesis
    curve: list[int] = []
    pending = False
    for row in rows:
        if row.get("type") == "FillRecorded":
            if pending:
                curve.append(equity_lamports(state))
            pending = True
        state = reduce(state, row)
    if pending:
        curve.append(equity_lamports(state))
    return tuple(curve)


def _paper_window(
    rows: Sequence[Mapping[str, Any]],
    *,
    cutoff: float,
    window_end: float,
    initial: int,
) -> tuple[LedgerState, list[Mapping[str, Any]]]:
    """Fold paper rows before the window into its opening state; keep the window rows.

    Rows stamped before the cutoff set the opening equity, so the paper curve
    starts where the window starts rather than at genesis. Rows at or past the
    window end are left out, so the paper summary counts the same span the
    holdout summary does, whatever the paper ledger holds after it.
    """
    opening = initial_state(source="backtest", initial_equity_lamports=initial, day_utc="")
    window_rows: list[Mapping[str, Any]] = []
    for row in rows:
        stamp = _row_stamp(row)
        if stamp < cutoff:
            opening = reduce(opening, row)
        elif stamp < window_end:
            window_rows.append(row)
    return (opening, window_rows)


def _last_row_stamp(rows: Sequence[Mapping[str, Any]]) -> float:
    """Latest stamp over every row of the holdout ledger, settling orders included.

    Replay advances the clock while an order confirms, so a settlement row can
    land past the last recorded tick. An empty ledger fails closed: replay
    always writes its checkpoint verdict row, so an empty one means a broken run.
    """
    if not rows:
        raise ConfigError(["backtest holdout ledger holds no rows"])
    return max(_row_stamp(row) for row in rows)


def _window_end(last_stamp: float) -> float:
    """Half-open window end: the first float past the latest holdout row.

    The holdout summary and the paper comparison both take their end from
    this one rule, so they count the same fills and marks.
    """
    return math.nextafter(last_stamp, math.inf)


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
    window_end_ts: float
    rejected_fees_lamports: int


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
    spec: _Dataset,
    dataset: FixtureDataset,
    stamps: tuple[float, ...],
    split: HoldoutSplit,
    run_id: str,
    holdout_ledger: Path,
    initial_fallback: int,
) -> _HoldoutOutcome:
    """Summarize the holdout fills of the ledger that run_search already replayed (BT-05, BT-06).

    The window comes from fold_windows with the same fold count the search
    used, so tuning never reads past the cutoff; the identity check against
    the split fails closed on drift. Fills rebuild from the recorded
    FillRecorded rows, the equity curve folds every window row from genesis,
    and the span between the first and last window event sets the elapsed
    days. The window ends at the first float past the latest holdout row,
    settling orders included; the shared result and the paper comparison use that end.
    """
    cutoff = split.holdout_start_ts
    windows = fold_windows(stamps, spec.name, 3)
    holdout_window = windows.holdout
    if holdout_window.window_id != split.holdout_id:
        raise ConfigError(["backtest holdout window identity drifted"])
    rows, meta = _read_window_ledger(holdout_ledger)
    last_row_stamp = _last_row_stamp(rows)
    window_end_ts = _window_end(last_row_stamp)
    fills, latencies = _fills_from_rows(rows)
    initial = int(meta) if meta is not None else initial_fallback
    genesis = initial_state(source="backtest", initial_equity_lamports=initial, day_utc="")
    events = dataset.events
    window_points = [
        (event_epoch(event), str(event["ts_utc"]))
        for event in events
        if event_epoch(event) >= cutoff
    ]
    if window_points:
        window_start_utc = window_points[0][1]
        first_stamp = window_points[0][0]
        last_stamp = window_points[-1][0]
    else:
        window_start_utc = format_ts_utc(cutoff)
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
            equity_curve_lamports=_window_curve(genesis, rows),
            elapsed_days=elapsed_days,
        ),
    )
    backtest_result = SharedResult.from_fills(
        run_id=run_id,
        dataset=spec.name,
        window_start_ts=cutoff,
        window_end_ts=window_end_ts,
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
        window_end_utc=format_ts_utc(last_row_stamp),
        window_end_ts=window_end_ts,
        rejected_fees_lamports=_rejection_fees(rows),
    )


def _paper_gate(
    *,
    paper_ledger: str | None,
    dataset_name: str,
    run_id: str,
    cutoff: float,
    window_end: float,
    elapsed_days: Decimal,
    initial_fallback: int,
    backtest_result: SharedResult,
    window_metrics: MetricsReport,
    eligible: bool,
) -> _PaperOutcome:
    """Same-window paper comparison and the D7 promotion gate (PAP-02, G-08).

    Without a paper ledger path promotion stays ineligible with reason
    divergence not compared. With one, the paper rows over the holdout window
    (from the cutoff to the window end) build the paper summary,
    opened at the equity the paper ledger held at the cutoff. SharedResult.compare
    enforces window equality before divergence.check, and a breach prints the
    DIVERGENCE BREACH line on stderr and exits 1 via enforce. Promotion is
    eligible only when trials are within limit and the verdict passes.
    """
    if paper_ledger is None:
        return _PaperOutcome(None, (), False, ("divergence not compared",), EXIT_OK)
    paper_file = Path(paper_ledger)
    if not paper_file.is_file():
        raise UsageError(f"bad --paper-ledger {paper_ledger!r}: want a ledger sqlite file")
    paper_rows, paper_meta = _read_window_ledger(paper_file)
    paper_initial = int(paper_meta) if paper_meta is not None else initial_fallback
    opening, window_rows = _paper_window(
        paper_rows, cutoff=cutoff, window_end=window_end, initial=paper_initial
    )
    paper_fills, _ = _fills_from_rows(window_rows)
    paper_metrics = summarize(
        paper_fills,
        MetricsContext(
            initial_equity_lamports=equity_lamports(opening),
            equity_curve_lamports=_window_curve(opening, window_rows),
            elapsed_days=elapsed_days,
        ),
    )
    paper_result = SharedResult.from_ledger_rows(
        run_id=run_id,
        dataset=dataset_name,
        window_start_ts=cutoff,
        window_end_ts=window_end,
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
