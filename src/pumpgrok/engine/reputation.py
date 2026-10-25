"""Creator memory: the same deployer must not drain us twice in a row.

The pipeline scores each launch from a clean slate, so without this book
one deployer could rug us three times running - and look brand new every
time. The auditor would not catch it either: it sees one token, not an
address history.

The reputation book closes this cheaply and without an LLM: an address
whose token already closed deep in the red is rejected at ingress, before
a single Grok call. Decisions rest only on our own closed trades - not an
internet blocklist, not a heuristic, but a fact from our own log.

Port of the retired oracle ``src/reputation.py``. All prose is
English; the vendor text is Russian.

Deliberate divergences from the oracle:

- Wall time is gone: ``ReputationBook`` carries the injected clock as a
  private attribute and ``forget_older_than`` takes ``now`` explicitly.
- Persistence goes through ``core/atomic_write.py`` and keeps the vendor
  JSON shape (``version``/``creators``/``updated_at``). An ``OSError`` now
  propagates instead of being logged and swallowed: the ledger must fail
  loudly.
- ``verdict`` and ``summary`` are English ASCII. ``verdict`` returns the
  code-shaped string ``creator_rugged`` with counts, never free text.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from pumpgrok.core.atomic_write import atomic_write_json
from pumpgrok.replay.clock import Clock, WallClock, format_ts_utc

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

log = logging.getLogger(__name__)

# How many addresses to remember. Past that, evict the stalest.
MAX_CREATORS = 50_000

# Lamports per SOL: the ledger settles in lamports, and so does the book (INT-01).
LAMPORTS_PER_SOL = 1_000_000_000


class CreatorRecord(BaseModel):
    """What we know about one address from our own trades."""

    model_config = ConfigDict(extra="forbid")

    creator: str
    tokens_seen: int = 0
    tokens_bought: int = 0
    closed: int = 0
    rugs: int = 0
    realized_pnl_lamports: int = 0
    worst_loss_pct: float = 0.0
    last_seen: float = 0.0

    @field_validator("realized_pnl_lamports", mode="before")
    @classmethod
    def _require_int_lamports(cls, v: Any) -> Any:
        """Old float books must rebuild from the ledger, not coerce (INT-01, D-01)."""
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("integer lamports required; rebuild the book from the ledger")
        return v

    @property
    def is_known_bad(self) -> bool:
        return self.rugs > 0

    model_config = ConfigDict(extra="forbid")


class ReputationBook(BaseModel):
    version: int = 1
    creators: dict[str, CreatorRecord] = Field(default_factory=dict)
    updated_at: float = 0.0
    # True when load quarantined a corrupt file: history was lost, act blind.
    # Excluded from the dump so the vendor JSON shape never changes.
    degraded: bool = Field(default=False, exclude=True)

    _clock: Clock = PrivateAttr(default_factory=WallClock)

    # -- disk --------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path, clock: Clock | None = None) -> ReputationBook:
        """Load the book. A corrupt or marked book comes back degraded (refusing buys).

        A corrupt file is quarantined beside itself, and a durable degraded marker
        ``<stem>.degraded.json`` is written beside the book. The marker records the
        quarantine path, the cause and the detection time. Every later load treats an
        existing marker as degraded, even when the book file is missing, so a restarted
        process cannot come back healthy and empty.

        Nothing clears the marker automatically. A human clears the degraded state by
        removing the marker, after restoring or rebuilding the book. The refusal logic
        is unchanged: a degraded book refuses buys.
        """
        file = Path(path)
        marker = file.with_name(f"{file.stem}.degraded.json")
        if marker.exists():
            book = cls()
            if clock is not None:
                book._clock = clock
            book.degraded = True
            log.error("reputation book degraded by marker %s: remove it to clear", marker)
            return book
        if not file.exists():
            book = cls()
            if clock is not None:
                book._clock = clock
            return book
        try:
            raw: Any = json.loads(file.read_text(encoding="utf-8"))
            book = cls.model_validate(raw)
        except Exception as exc:
            book = cls()
            if clock is not None:
                book._clock = clock
            stamp = format_ts_utc(book._clock.now()).replace(":", "-")
            quarantine = file.with_name(f"{file.name}.corrupt-{stamp}")
            moved_to: Path | None = None
            try:
                file.rename(quarantine)
            except OSError as move_exc:
                log.error(
                    "reputation book %s unreadable (%s), quarantine to %s failed (%s)",
                    file,
                    type(exc).__name__,
                    quarantine,
                    type(move_exc).__name__,
                )
            else:
                moved_to = quarantine
                log.error(
                    "reputation book %s unreadable (%s), quarantined to %s",
                    file,
                    type(exc).__name__,
                    quarantine,
                )
            book.degraded = True
            cls._write_degraded_marker(
                marker,
                book_file=file,
                quarantine=moved_to,
                cause=type(exc).__name__,
                now=book._clock.now(),
            )
            return book
        if clock is not None:
            book._clock = clock
        return book

    @staticmethod
    def _write_degraded_marker(
        marker: Path, *, book_file: Path, quarantine: Path | None, cause: str, now: float
    ) -> None:
        """Persist the degraded state so the next process starts degraded too.

        A failed write raises: a process must not start healthy over a corrupt book, so the
        operator registry refuses to build until the marker can be written.
        """
        payload = {
            "book": str(book_file),
            "quarantine": str(quarantine) if quarantine is not None else None,
            "cause": cause,
            "detected_at": format_ts_utc(now),
        }
        try:
            atomic_write_json(marker, payload)
        except OSError as exc:
            raise RuntimeError(
                f"reputation degraded marker {marker} not written ({type(exc).__name__}); "
                "refusing to start healthy over a corrupt book"
            ) from exc

    def save(self, path: str | Path) -> None:
        """Atomically, like the pipeline state: half a file is worse than none."""
        self.updated_at = self._clock.now()
        atomic_write_json(path, self.model_dump(mode="json"))

    @classmethod
    def rebuild_from_ledger(
        cls,
        store: LedgerStore,
        *,
        clock: Clock | None = None,
        rug_loss_pct: float = 60.0,
    ) -> ReputationBook:
        """Reconstruct the book from ledger fills after a quarantine (R62).

        Scans ``PositionOpened`` rows for the mint creator and ``PositionClosed``
        rows for ``realized_pnl_lamports`` plus the fractional ``pnl_pct`` to
        rebuild per-creator losses. The ledger settles in lamports and stores
        ``pnl_pct`` as a fraction; the book keeps integer lamports and a float
        percent, so only the percent unit is converted. A close whose mint
        never opened cannot be attributed and is skipped. When nothing is
        restorable the book stays ``degraded`` and keeps refusing.
        """
        events = store.read(types=["PositionOpened", "PositionClosed"], limit=None)
        mint_creator = _mint_creators(events)
        book = cls()
        if clock is not None:
            book._clock = clock
        restored = False
        for event in events:
            restored = _replay_event(book, mint_creator, event, rug_loss_pct) or restored
        if not restored:
            book.degraded = True
        return book

    # -- accounting --------------------------------------------------------

    def _record(self, creator: str) -> CreatorRecord:
        record = self.creators.get(creator)
        if record is None:
            record = CreatorRecord(creator=creator)
            self.creators[creator] = record
            self._evict_if_crowded()
        record.last_seen = self._clock.now()
        return record

    def observe(self, creator: str | None) -> None:
        if creator:
            self._record(creator).tokens_seen += 1

    def record_open(self, creator: str | None) -> None:
        if creator:
            self._record(creator).tokens_bought += 1

    def record_close(
        self,
        creator: str | None,
        *,
        pnl_lamports: int,
        return_pct: float,
        rug_loss_pct: float,
    ) -> CreatorRecord | None:
        """A closed position. A deep loss counts as a rug for the address."""
        if not creator:
            return None
        record = self._record(creator)
        record.closed += 1
        record.realized_pnl_lamports += pnl_lamports
        record.worst_loss_pct = min(record.worst_loss_pct, return_pct)
        if rug_loss_pct and -return_pct >= rug_loss_pct:
            record.rugs += 1
            log.warning(
                "creator %s: rug %d, worst %.1f%%, its next tokens are rejected at ingress",
                creator[:8],
                record.rugs,
                record.worst_loss_pct,
            )
        return record

    # -- verdict -----------------------------------------------------------

    def verdict(self, creator: str | None, block_after_rugs: int) -> str | None:
        """Why to avoid this address, or None."""
        if not creator or block_after_rugs <= 0:
            return None
        record = self.creators.get(creator)
        if record is None:
            return None
        if record.rugs >= block_after_rugs:
            return f"creator_rugged {record.rugs}x (worst {record.worst_loss_pct:.0f}%)"
        return None

    # -- maintenance -------------------------------------------------------

    def forget_older_than(self, days: float, now: float) -> int:
        """Forget addresses unheard from for a while. Rugs are never forgotten."""
        if days <= 0:
            return 0
        cutoff = now - days * 86_400
        stale = [
            key
            for key, record in self.creators.items()
            if record.last_seen < cutoff and not record.is_known_bad
        ]
        for key in stale:
            del self.creators[key]
        return len(stale)

    def _evict_if_crowded(self) -> None:
        """Evict clean addresses first: rugs are what this book is for."""
        if len(self.creators) <= MAX_CREATORS:
            return
        order = sorted(
            self.creators.items(),
            key=lambda item: (item[1].is_known_bad, item[1].last_seen),
        )
        for key, _ in order:
            if len(self.creators) <= MAX_CREATORS:
                break
            del self.creators[key]

    def summary(self) -> str:
        bad = sum(1 for r in self.creators.values() if r.is_known_bad)
        return f"{len(self.creators)} creators, {bad} with rugs"


def _mint_creators(events: list[dict[str, Any]]) -> dict[str, str]:
    """First opener wins per mint; unattributed mints stay out."""
    mint_creator: dict[str, str] = {}
    for event in events:
        if event["type"] != "PositionOpened":
            continue
        payload = event["payload"]
        if not isinstance(payload, dict):
            continue
        mint = str(payload.get("mint", ""))
        creator = str(payload.get("creator", ""))
        if mint and creator:
            mint_creator.setdefault(mint, creator)
    return mint_creator


def _replay_event(
    book: ReputationBook,
    mint_creator: dict[str, str],
    event: dict[str, Any],
    rug_loss_pct: float,
) -> bool:
    """Fold one ledger row into the book; True when it restored history."""
    payload = event["payload"]
    if not isinstance(payload, dict):
        return False
    if event["type"] == "PositionOpened":
        creator = str(payload.get("creator", ""))
        if not creator:
            return False
        book.record_open(creator)
        return True
    if event["type"] != "PositionClosed":
        return False
    return _replay_close(book, mint_creator, payload, rug_loss_pct)


def _replay_close(
    book: ReputationBook,
    mint_creator: dict[str, str],
    payload: dict[str, Any],
    rug_loss_pct: float,
) -> bool:
    """Attribute one close to its opener; False when it cannot be used."""
    creator = mint_creator.get(str(payload.get("mint", "")), "")
    if not creator:
        return False
    try:
        pnl_lamports = int(payload.get("realized_pnl_lamports", 0))
        return_pct = float(str(payload.get("pnl_pct", "0"))) * 100.0
    except (TypeError, ValueError):
        return False
    book.record_close(
        creator,
        pnl_lamports=pnl_lamports,
        return_pct=return_pct,
        rug_loss_pct=rug_loss_pct,
    )
    return True
