"""Command line: parse, check, main (FOUND-013, R30, R37; port of grokbot `pipeline.py` shape).

Verbs: `run` (paper, `--once --replay <dir>` runs one engine-decision cycle) and `doctor`
print text (exemptions: the replay checkpoint prints the engine-decision line and the
doctor report is human-readable). Every other section-12 verb is a thin JSON wrapper
over catalog tools through `build_operator_registry` + `registry.find` (TOOL-011, I1):
`paper buy|sell` (simulate then place against the paper engine; fail closed on
unknown `--approval-id`, exit 1, R63), `state` (status, halt, halt --clear,
autonomy, resume), `killswitch` (set, flatten, status, clear), `ticket`
(next, create, list), `verify`, plus the find-only orchestration verbs
(`scout`, `risk`, `chief`, `rug`, `journal`, `report`, `audit`) and the
human-only `live confirm`, which print the JSON envelope and exit 5 (B5
partial until Phase 4). Replay maintenance verbs exit 5. `paper` and `state`
halt/autonomy require `--seat` and refuse `sniper`/`exit`. Hidden
`tools <id> --help` prints the tool JSON schema (B8).
Exit codes: 0 ok; 1 config or usage; 2 ledger inconsistent; 3 live refused; 4 corrupt
fixture; 5 not implemented; 6 a kill flatten that left a position open.
argparse's own exit 2 is overridden so that 2 means only a ledger inconsistency.
Stdout carries JSON (or the doctor report and the engine decision); diagnostics go to stderr.

Run order: refuse key-bearing CLI values -> parse -> settings (mode R30) -> logging ->
live gate (live exits 3 before any other work) -> verb. For the replay cycle: manifest
verification (exit 4, before any ledger file exists) -> recreate ledger -> judge each
fixture tick as a candidate carrying its evidence -> append the verdict `JournalNote`
(source=replay) -> run the ten seat cycles, the sniper placing granted BUYs through risk
and PaperAdapter -> print the `engine decision=` line and one `trade` line per order
attempt -> verify chain.
"""

import logging

from pumpgrok.cli.codes import (
    EXIT_CONFIG,
    EXIT_FIXTURE,
    EXIT_LEDGER,
    EXIT_LIVE,
    EXIT_NOT_IMPLEMENTED,
    EXIT_OK,
    EXIT_UNFLATTENED,
)
from pumpgrok.cli.dispatch import main
from pumpgrok.cli.errors import UsageError
from pumpgrok.cli.parsing import build_parser
from pumpgrok.cli.validators import (
    _jsonable,
    _mint_approval_id,
    _size_sol,
    _utc_now,
    size_sol_to_lamports,
)
from pumpgrok.cli.wiring import _unflattened_lines
from pumpgrok.tools import build_operator_registry

log = logging.getLogger("pumpgrok.cli")

__all__ = [
    "EXIT_CONFIG",
    "EXIT_FIXTURE",
    "EXIT_LEDGER",
    "EXIT_LIVE",
    "EXIT_NOT_IMPLEMENTED",
    "EXIT_OK",
    "EXIT_UNFLATTENED",
    "UsageError",
    "_jsonable",
    "_mint_approval_id",
    "_size_sol",
    "_unflattened_lines",
    "_utc_now",
    "build_operator_registry",
    "build_parser",
    "main",
    "size_sol_to_lamports",
]
