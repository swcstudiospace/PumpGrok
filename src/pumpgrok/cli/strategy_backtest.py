"""Human-invoked strategy backtest (REC-03).

One run through the strategy replay runtime, with no timer. The report
prints the run's realized net. The v3 verb is not this module.
"""

from __future__ import annotations

import argparse
import sys

from pumpgrok.backtest.manifest import dataset_digest
from pumpgrok.backtest.strategy_run import run_strategy
from pumpgrok.cli.backtest import _backtest_dataset
from pumpgrok.cli.codes import EXIT_OK
from pumpgrok.cli.errors import _say
from pumpgrok.config.settings import Settings
from pumpgrok.execution.fees import PAPER_DEFAULT_FEE_MODEL, FeeModelV2
from pumpgrok.strategies.registry import is_known_strategy, registered_ids


def strategy_backtest_verb(args: argparse.Namespace, settings: Settings) -> int:
    """Run one registered strategy and print the realized net.

    The call is human-invoked through the strategy replay runtime with
    no sleep and no timer. The report is printed either way.
    """
    strategy_id = str(getattr(args, "strategy", "") or "")
    _require_strategy(strategy_id)
    dataset = _backtest_dataset(str(args.fixture))
    result = run_strategy(
        dataset.directory, strategy_id, seed=settings.replay.seed
    )
    report = render_strategy_report(
        dataset.name,
        dataset_digest(dataset.directory),
        strategy_id,
        result.net_lamports,
    )
    _say(sys.stdout, report)
    return EXIT_OK


def render_strategy_report(
    dataset_name: str,
    digest: str,
    strategy_id: str,
    net_lamports: int,
) -> str:
    """Deterministic markdown for one strategy run."""
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
    parts.append("## Result\n")
    parts.append(f"net_lamports: {net_lamports}\n")
    parts.append("note: realized history only; no forward-looking statements\n")
    body = "".join(parts)
    body.encode("ascii")
    return body


def _require_strategy(strategy_id: str) -> None:
    if not strategy_id:
        raise ValueError("backtest --strategy requires a registered strategy id")
    if not is_known_strategy(strategy_id):
        known = ", ".join(registered_ids())
        raise ValueError(f"unknown strategy {strategy_id!r}; known: {known}")


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
