"""Shared exit codes, argument patterns and find-only verb routes."""

from __future__ import annotations

import logging
import re

log = logging.getLogger("pumpgrok.cli")

EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_LEDGER = 2
EXIT_LIVE = 3
EXIT_FIXTURE = 4
# A killswitch flatten that did not close every open position (G7). 6 is the lowest code the CLI
# does not otherwise use (0-5 are taken above), so it collides with no other verb. The UNFLATTENED
# stderr line names the positions. The latch stays set either way.
EXIT_UNFLATTENED = 6
EXIT_NOT_IMPLEMENTED = 5

DATASET_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")

# Canonical paper ledger: pumpgrok.ledger.paths.PAPER_LEDGER_PATH (paper-engine.md 3.1),
# shared with the desk gateway and the daily report.

FORBIDDEN_OWNERS = frozenset({"sniper", "exit"})
TICKET_RE = re.compile(r"^SOL-\d{8}-\d{3}$")
APPROVAL_RE = re.compile(r"^apr-[0-9A-HJKMNP-TV-Z]{26}$")
_BASE58 = frozenset("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

_EXIT_BY_CODE = {
    "not_yet_implemented": EXIT_NOT_IMPLEMENTED,
    "ledger_unavailable": EXIT_LEDGER,
    "live_gate": EXIT_LIVE,
}

_TRADE_UNAVAILABLE = (
    "trade commands need a verified curve price source; no paper fills run from the CLI "
    "until the Phase 4 curve reader is verified"
)

_TOOLS_HELP = (
    "usage: pumpgrok tools <id> [--help]",
    "",
    "Hidden developer verb (B8): print one catalog tool JSON schema.",
    "Not listed in top-level help. The schema is mode-independent.",
    "",
    "examples:",
    "  pumpgrok tools exec.quote --help",
)

_SCOUT_FLOW = ("market.trades", "market.liquidity", "onchain.authorities", "journal.append")
_RISK_AUDIT = (
    "portfolio.ledger_read",
    "portfolio.exposure",
    "portfolio.pnl",
    "risk.drawdown",
    "risk.check_limits",
    "risk.halt_status",
    "desk.event_emit",
)
_CHIEF_PICKUP = ("desk.brief", "risk.halt_status", "exec.positions", "notify.alert")
_RUG_WATCH = (
    "onchain.lp_status",
    "onchain.authorities",
    "onchain.top_holders",
    "market.price",
    "desk.event_emit",
)

# Find-only verbs (B5 partial): verb -> (calling seat, capabilities resolved through find).
_FIND_ONLY_ROUTES: dict[str, tuple[str, tuple[str, ...]]] = {
    "scout": ("scout", _SCOUT_FLOW),
    "risk": ("risk", _RISK_AUDIT),
    "chief": ("chief", _CHIEF_PICKUP),
    "rug": ("rug", _RUG_WATCH),
    "journal": ("journal", ("journal.render_report",)),
    "audit": ("desk", ("desk.doctor",)),
}
