"""``pumpgrok promotion demote --strategy ID``: one-operation rollback (PRM-04).

A thin CLI over the same demotion function the evaluator uses: one
command rolls the named strategy back exactly one stage, writes the
ledger rows and exits 0. The verb never deletes history; the decision
log keeps both directions.
"""

from __future__ import annotations

import argparse
import json
import sys

from pumpgrok.cli.codes import EXIT_OK
from pumpgrok.cli.errors import _say
from pumpgrok.config.settings import Settings
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.promotion.demotion import demote_one_stage
from pumpgrok.replay.clock import WallClock, format_ts_utc
from pumpgrok.tools import ensure_paper_genesis


def _promotion_verb(args: argparse.Namespace, settings: Settings) -> int:
    """Roll one strategy back exactly one stage (thin CLI over demote_one_stage)."""
    if args.cmd == "demote":
        store = LedgerStore(str(PAPER_LEDGER_PATH))
        try:
            ensure_paper_genesis(store, settings.risk)
            demoted = demote_one_stage(
                store,
                args.strategy,
                by=args.by,
                ts_utc=format_ts_utc(WallClock().now()),
                source="paper",
                correlation_id="desk",
            )
        finally:
            store.close()
        if demoted is None:
            _say(sys.stderr, f"promotion demote refused: unknown strategy {args.strategy!r}")
            return 1
        _say(
            sys.stdout,
            json.dumps({"ok": True, "strategy": args.strategy, "stage": demoted.stage.value, "by": args.by}),
        )
        return EXIT_OK
    return 1
