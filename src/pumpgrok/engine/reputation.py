"""Creator memory: the same deployer must not drain us twice in a row.

The pipeline scores each launch from a clean slate, so without this book
one deployer could rug us three times running — and look brand new every
time. The auditor would not catch it either: it sees one token, not an
address history.

The reputation book closes this cheaply and without an LLM: an address
whose token already closed deep in the red is rejected at ingress, before
a single Grok call. Decisions rest only on our own closed trades — not an
internet blocklist, not a heuristic, but a fact from our own log.

Port of ``vendor/grokbot-pumpfun/src/reputation.py``. All prose is
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
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from pumpgrok.core.atomic_write import atomic_write_json
from pumpgrok.replay.clock import Clock, WallClock

log = logging.getLogger(__name__)

# How many addresses to remember. Past that, evict the stalest.
MAX_CREATORS = 50_000


class CreatorRecord(BaseModel):
    """What we know about one address from our own trades."""

    model_config = ConfigDict(extra="forbid")

    creator: str
    tokens_seen: int = 0
    tokens_bought: int = 0
    closed: int = 0
    rugs: int = 0
    realized_pnl_sol: float = 0.0
    worst_pnl_pct: float = 0.0
    last_seen: float = 0.0

    @property
    def is_known_bad(self) -> bool:
        return self.rugs > 0

    model_config = ConfigDict(extra="forbid")


class ReputationBook(BaseModel):
    version: int = 1
    creators: dict[str, CreatorRecord] = Field(default_factory=dict)
    updated_at: float = 0.0

    _clock: Clock = PrivateAttr(default_factory=WallClock)

    # -- disk --------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path, clock: Clock | None = None) -> ReputationBook:
        file = Path(path)
        if not file.exists():
            book = cls()
            if clock is not None:
                book._clock = clock
            return book
        try:
            raw: Any = json.loads(file.read_text(encoding="utf-8"))
            book = cls.model_validate(raw)
        except Exception as exc:
            log.error("reputation book %s unreadable (%s), starting empty", file, exc)
            book = cls()
        if clock is not None:
            book._clock = clock
        return book

    def save(self, path: str | Path) -> None:
        """Atomically, like the pipeline state: half a file is worse than none."""
        self.updated_at = self._clock.now()
        atomic_write_json(path, self.model_dump(mode="json"))

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
        pnl_sol: float,
        pnl_pct: float,
        rug_loss_pct: float,
    ) -> CreatorRecord | None:
        """A closed position. A deep loss counts as a rug for the address."""
        if not creator:
            return None
        record = self._record(creator)
        record.closed += 1
        record.realized_pnl_sol += pnl_sol
        record.worst_pnl_pct = min(record.worst_pnl_pct, pnl_pct)
        if rug_loss_pct and -pnl_pct >= rug_loss_pct:
            record.rugs += 1
            log.warning(
                "creator %s: rug %d, worst %.1f%%, its next tokens are rejected at ingress",
                creator[:8],
                record.rugs,
                record.worst_pnl_pct,
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
            return f"creator_rugged {record.rugs}x (worst {record.worst_pnl_pct:.0f}%)"
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
