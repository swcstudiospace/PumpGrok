"""Human-invoked strategy backtest (REC-03).

One call into the 16-05 scheduler, with no timer. The printed report is the
Metrics v2 set. An undefined value is the text None. The v3 verb is not this
module.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from pumpgrok.backtest.manifest import dataset_digest
from pumpgrok.backtest.metrics_v2 import MetricsV2
from pumpgrok.backtest.scheduler import GRADER_VERSION, Edge, run_edge, strategy_run
from pumpgrok.backtest.store import ResultStore
from pumpgrok.cli.backtest import _backtest_dataset
from pumpgrok.cli.codes import EXIT_OK
from pumpgrok.cli.errors import UsageError, _say
from pumpgrok.config.settings import Settings
from pumpgrok.execution.fees import PAPER_DEFAULT_FEE_MODEL, FeeModelV2
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import WallClock
from pumpgrok.strategies.base import Strategy, version_id
from pumpgrok.strategies.registry import STRATEGIES

# The decided seven, in owner order. annualization_valid is a flag, printed after them.
_METRIC_NAMES = (
    "total_return",
    "max_drawdown",
    "sharpe_ratio",
    "sortino_ratio",
    "hit_rate",
    "profit_factor",
    "expectancy_lamports",
)


def strategy_backtest_verb(args: argparse.Namespace, settings: Settings) -> int:
    """Run one registered strategy and print Metrics v2.

    The scheduler call is human-invoked: one ``run_edge``, no sleep and no
    timer. The autonomy gate inside that call still decides whether the row
    is published. The report is printed either way.
    """
    del settings
    strategy_id = str(getattr(args, "strategy", "") or "")
    cls = _require_strategy(strategy_id)
    dataset = _backtest_dataset(str(args.fixture))
    edge = _edge(cls, strategy_id, dataset.directory)
    _invoke_scheduler(edge)
    metrics = _metrics(strategy_run(edge))
    report = render_strategy_report(dataset.name, edge.dataset_digest, strategy_id, metrics)
    _say(sys.stdout, report)
    return EXIT_OK


def render_strategy_report(
    dataset_name: str,
    digest: str,
    strategy_id: str,
    metrics: MetricsV2,
) -> str:
    """Deterministic markdown. Undefined metric values are the text None."""
    parts = ["# PumpGrok strategy backtest\n", "## Run\n"]
    run_rows = sorted(
        {
            "dataset": dataset_name,
            "dataset_digest": digest,
            "strategy_id": strategy_id,
        }.items()
    )
    parts.extend(f"{key}: {value}\n" for key, value in run_rows)
    parts.append("## Cost basis\n")
    parts.extend(f"{key}: {value}\n" for key, value in _fee_rows())
    parts.append("## Metrics v2\n")
    for name in _METRIC_NAMES:
        parts.append(f"{name}: {_metric_text(getattr(metrics, name))}\n")
    flag = "true" if metrics.annualization_valid else "false"
    parts.append(f"annualization_valid: {flag}\n")
    parts.append("note: undefined values are None; annualization_valid is a flag, not a metric\n")
    body = "".join(parts)
    body.encode("ascii")
    return body


def _require_strategy(strategy_id: str) -> type[Strategy]:
    if not strategy_id:
        raise UsageError("backtest --strategy requires a registered strategy id")
    for cls in STRATEGIES:
        if cls.strategy_id == strategy_id:
            return cls
    known = ", ".join(cls.strategy_id for cls in STRATEGIES)
    raise UsageError(f"unknown strategy {strategy_id!r}; known: {known}")


def _edge(cls: type[Strategy], strategy_id: str, dataset_dir: Path) -> Edge:
    defaults = dict(cls.DEFAULTS)
    return Edge(
        dataset_digest=dataset_digest(dataset_dir),
        strategy_version_id=version_id(cls, defaults),
        params_hash=_params_hash(defaults),
        dataset_dir=str(dataset_dir),
        strategy_id=strategy_id,
        kind="strategy",
        grader_version=GRADER_VERSION,
    )


def _params_hash(params: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(params), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _invoke_scheduler(edge: Edge) -> None:
    """One scheduler call. Ledger writes use the wall clock: a virtual clock
    would stamp 1970-01-01 into the operator ledger (DESK-R-02)."""
    store = ResultStore()
    ledger = _ledger()
    try:
        run_edge(edge, store, ledger, WallClock())
    finally:
        ledger.close()


def _ledger() -> LedgerStore:
    """The operator ledger when it exists; otherwise an empty ledger that skips."""
    if PAPER_LEDGER_PATH.exists():
        return LedgerStore(PAPER_LEDGER_PATH)
    directory = Path(tempfile.mkdtemp(prefix="strategy-backtest-"))
    return LedgerStore(directory / "ledger.sqlite")


def _metrics(run: object) -> MetricsV2:
    metrics = getattr(run, "metrics_v2", None)
    if not isinstance(metrics, MetricsV2):
        raise RuntimeError("scheduler strategy_run did not return Metrics v2")
    return metrics


def _fee_rows() -> tuple[tuple[str, str], ...]:
    fees = PAPER_DEFAULT_FEE_MODEL
    if not isinstance(fees, FeeModelV2):
        raise RuntimeError("strategy path requires fee model v2")
    rows = {
        "ata_rent_epoch": str(fees.ata_rent_epoch),
        "ata_rent_lamports": str(fees.ata_rent_lamports),
        "ata_rent_source": fees.ata_rent_source,
        "base_fee_lamports": str(fees.base_fee_lamports),
        "cost_basis": "fee model v2",
        "fee_model": "v2",
        "network_cost_lamports": str(fees.network_cost()),
        "venue_fee_bps": str(fees.venue_fee_bps),
    }
    return tuple(sorted(rows.items()))


def _metric_text(value: object) -> str:
    if value is None:
        return "None"
    if not isinstance(value, Decimal):
        raise RuntimeError("Metrics v2 value is not a Decimal or None")
    return format(value, "f")
