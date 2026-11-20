"""Named lane, retry, and sidecar constants. Numbers are not inlined in the bus."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.ledger.paths import PAPER_LEDGER_PATH

P0_LANE_CAP: int | None = None
P1_LANE_CAP = 1000
P2_COALESCE_CAP = 1
STALE_AFTER_S = 120.0
STABLE_S = 30.0
RETRY_ATTEMPTS = 5
P0_DEDUP_TTL_S = 86400
P1_DEDUP_TTL_S = 300
P2_DEBOUNCE_S = 1.0
# Clock seconds shutdown() waits for running handler calls. Calls still running after this
# are cancelled, and their events stay pending. Cancellation is never a handler failure.
SHUTDOWN_TIMEOUT_S = 5.0
BACKOFF_INITIAL_S = 1.0
BACKOFF_FACTOR = 2
BACKOFF_MAX_S = 16.0
BACKOFF_JITTER_S = 1.0
EVENTS_SIDECAR_PATH = Path("var") / "desk" / "events.sqlite"


def path_is_paper_ledger(path: Path) -> bool:
    """True when `path` is the paper ledger. Callers must refuse it, not open it."""
    return Path(path) == PAPER_LEDGER_PATH
