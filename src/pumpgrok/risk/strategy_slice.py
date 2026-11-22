"""Per-strategy exposure slices and strategy kills on existing R34 rows (RSK-01, RSK-02, RSK-08).

Slice weights come from the version-controlled ``config/strategy_slices.toml``
(0.20 each with a 0.20 reserve per V4-10) and are never duplicated here: the
defaults below are only fallbacks for a missing file, and the loader refuses
weights that sum above 1.0 (T-17-01). Slice state (spent per strategy) is
read from ledger rows, never from process memory alone, and a kill is a
ledger ``JournalNote`` verdict row so it survives a restart and clears only
with a human approval record (T-17-02). Money is integer lamports only.

Enforcement maps onto the existing ``max_token_fraction`` R34 row (capped or
rejected with the reason on that row, G-01) and a kill rejects buys on the
existing ``kill_switch`` row; no new step and no risk_json key is added.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

from pumpgrok.strategies.base import STRATEGY_IDS

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

__all__ = [
    "DEFAULT_SLICE_CONFIG_PATH",
    "SliceConfig",
    "SliceError",
    "clear_strategy_kill",
    "killed_strategies",
    "load_slice_config",
    "record_strategy_kill",
    "spent_from_ledger",
]

DEFAULT_SLICE_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "strategy_slices.toml"

#: One configured weight per registered strategy: 0.20 with a 0.20 reserve.
DEFAULT_WEIGHTS: dict[str, Decimal] = dict.fromkeys(STRATEGY_IDS, Decimal("0.20"))
DEFAULT_RESERVE = Decimal("0.20")

STRATEGY_KILL_RE_PREFIX = "RISK verdict=KILL strategy="
STRATEGY_CLEAR_RE_PREFIX = "RISK verdict=CLEAR strategy="


class SliceError(ValueError):
    """A slice config or a slice lookup is invalid."""


@dataclass(frozen=True)
class SliceConfig:
    """Version-controlled slice weights plus the reserve; integer math only."""

    weights: dict[str, Decimal] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    reserve: Decimal = DEFAULT_RESERVE
    enabled: bool = False

    def __post_init__(self) -> None:
        total = sum(self.weights.values(), Decimal("0")) + self.reserve
        if total > Decimal("1.0"):
            raise SliceError(f"slice weights plus reserve sum to {total} > 1.0")

    def weight_for(self, strategy_id: str) -> Decimal:
        """Configured weight for one strategy; unknown ids refuse."""
        try:
            return self.weights[strategy_id]
        except KeyError:
            raise SliceError(f"unknown strategy id: {strategy_id!r}") from None

    def cap_lamports(self, strategy_id: str, *, equity_lamports: int, spent_lamports: int) -> int:
        """Remaining slice room in integer lamports; negative means exhausted."""
        if equity_lamports < 0 or spent_lamports < 0:
            raise SliceError("equity and spent must be non-negative lamports")
        cap = int(self.weight_for(strategy_id) * equity_lamports) - spent_lamports
        return cap


def load_slice_config(path: Path | str | None = None) -> SliceConfig:
    """Load slice weights from the version-controlled TOML file.

    A missing or unparsable file falls back to the declared defaults so the
    desk still starts; a file whose weights sum above 1.0 refuses to load.
    """
    target = Path(path) if path is not None else DEFAULT_SLICE_CONFIG_PATH
    if not target.exists():
        return SliceConfig()
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
        section = raw.get("strategy", {}).get("slice", {})
        if not isinstance(section, dict):
            return SliceConfig()
        enabled = bool(section.get("enabled", False))
        reserve = Decimal(str(section.get("reserve", str(DEFAULT_RESERVE))))
        weights_raw = section.get("weights", {})
        if not isinstance(weights_raw, dict):
            return SliceConfig()
        weights = {str(k): Decimal(str(v)) for k, v in weights_raw.items()}
        return SliceConfig(weights=weights, reserve=reserve, enabled=enabled)
    except SliceError:
        raise
    except Exception:
        return SliceConfig()


def spent_from_ledger(store: LedgerStore, strategy_id: str) -> int:
    """Lamports this strategy has already spent, summed from ledger rows.

    Attribution scans ``OrderPlaced`` rows whose payload text names the
    strategy id (the desk records the strategy on placement); a restart
    therefore still sees the spends. Sells do not count as spent.
    """
    spent = 0
    for event in store.read(types=["OrderPlaced"], limit=None):
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if str(payload.get("side", "")) != "buy":
            continue
        if strategy_id not in str(payload.get("approval_json", "")) + str(
            payload.get("risk_json", "")
        ) + str(payload.get("quote_json", "")):
            continue
        size = payload.get("size_lamports")
        if isinstance(size, int) and not isinstance(size, bool) and size > 0:
            spent += size
    return spent


def _verdict_texts(store: LedgerStore) -> list[str]:
    texts: list[str] = []
    for event in store.read(types=["JournalNote"], limit=None):
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if str(payload.get("note_kind", "")) != "verdict":
            continue
        texts.append(str(payload.get("text", "")))
    return texts


def killed_strategies(store: LedgerStore) -> set[str]:
    """Strategy ids currently killed, replayed from ledger verdict rows.

    A ``KILL`` row kills; a later ``CLEAR`` row for the same strategy
    un-kills. Rows are read from the ledger on every call, so a restart
    still blocks buys for a killed strategy.
    """
    killed: set[str] = set()
    for text in _verdict_texts(store):
        if text.startswith(STRATEGY_KILL_RE_PREFIX):
            name = text[len(STRATEGY_KILL_RE_PREFIX) :].split(" ", 1)[0]
            if name:
                killed.add(name)
        elif text.startswith(STRATEGY_CLEAR_RE_PREFIX):
            name = text[len(STRATEGY_CLEAR_RE_PREFIX) :].split(" ", 1)[0]
            killed.discard(name)
    return killed


def record_strategy_kill(
    store: LedgerStore,
    strategy_id: str,
    reason: str,
    *,
    ts_utc: str,
    source: str = "paper",
    correlation_id: str = "desk",
) -> None:
    """Append one kill verdict row for a strategy; buys refuse, exits pass."""
    store.append(
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
        idempotency_key=f"strategy-kill|{strategy_id}|{ts_utc}",
        type="JournalNote",
        payload={
            "source": source,
            "seat": "bot-02-risk",
            "note_kind": "verdict",
            "text": f"{STRATEGY_KILL_RE_PREFIX}{strategy_id} reason={reason}",
            "refs": [],
        },
    )


def clear_strategy_kill(
    store: LedgerStore,
    strategy_id: str,
    *,
    ts_utc: str,
    approved_by: str,
    approval_id: str,
    source: str = "paper",
    correlation_id: str = "desk",
) -> None:
    """Clear a strategy kill; requires a human approval record (T-17-02).

    No engine path, timer, or auto-clear calls this: the caller must supply
    an approval recorded by a human (``human:<name>``). A non-human clear
    raises ValueError and writes nothing.
    """
    if not isinstance(approved_by, str) or not approved_by.startswith("human:"):
        raise ValueError(f"strategy kill clear must come from a human, got {approved_by!r}")
    if store.by_key(f"consumed|{approval_id}") is not None:
        raise ValueError(f"kill-clear approval {approval_id} is already consumed")
    store.append(
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
        idempotency_key=f"strategy-clear|{strategy_id}|{ts_utc}",
        type="JournalNote",
        payload={
            "source": source,
            "seat": "bot-02-risk",
            "note_kind": "verdict",
            "text": f"{STRATEGY_CLEAR_RE_PREFIX}{strategy_id} by={approved_by}",
            "refs": [],
        },
    )
    store.append(
        ts_utc=ts_utc,
        source=source,
        correlation_id=correlation_id,
        idempotency_key=f"consumed|{approval_id}",
        type="JournalNote",
        payload={
            "source": source,
            "seat": "bot-00-chief",
            "note_kind": "note",
            "text": f"consumed {approval_id} strategy_kill_clear {strategy_id}",
            "refs": [],
        },
    )
