"""Hash-chained SQLite ledger and derived views (paper-engine.md 3, R26)."""

from pumpgrok.ledger.desk_bus import (
    mirror_halt,
    mirror_halt_cleared,
    mirror_killswitch,
)
from pumpgrok.ledger.export import export_ledger
from pumpgrok.ledger.reconcile import (
    CONSISTENT,
    INCONSISTENT,
    ledger_inconsistent_halt,
    reconcile,
)
from pumpgrok.ledger.reducer import (
    CountersView,
    LedgerState,
    PositionView,
    dump_state,
    initial_state,
    load_state,
    reduce,
)
from pumpgrok.ledger.store import (
    GENESIS_PREV_HASH,
    SCHEMA_VERSION,
    LedgerInconsistent,
    LedgerStore,
    recreate_ledger_db,
)
from pumpgrok.ledger.tickets import TICKET_RE, allocate_ticket, day_ticket_count
from pumpgrok.ledger.views import (
    cash_lamports,
    daily_pnl_fraction,
    drawdown_fraction,
    equity_curve,
    equity_lamports,
    fees_lamports,
    positions,
    profit_factor,
    realized_pnl_lamports,
    unrealized_pnl_lamports,
    win_rate,
)

__all__ = [
    "CONSISTENT",
    "GENESIS_PREV_HASH",
    "INCONSISTENT",
    "SCHEMA_VERSION",
    "TICKET_RE",
    "CountersView",
    "LedgerInconsistent",
    "LedgerState",
    "LedgerStore",
    "PositionView",
    "allocate_ticket",
    "cash_lamports",
    "daily_pnl_fraction",
    "day_ticket_count",
    "drawdown_fraction",
    "dump_state",
    "equity_curve",
    "equity_lamports",
    "export_ledger",
    "fees_lamports",
    "initial_state",
    "ledger_inconsistent_halt",
    "load_state",
    "mirror_halt",
    "mirror_halt_cleared",
    "mirror_killswitch",
    "positions",
    "profit_factor",
    "realized_pnl_lamports",
    "reconcile",
    "recreate_ledger_db",
    "reduce",
    "unrealized_pnl_lamports",
    "win_rate",
]
