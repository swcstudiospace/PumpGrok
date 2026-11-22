"""Fail-closed entry checks on mint facts (RSK-05, T-17-05, T-17-06).

Each check is a small pure function over the mint facts the engine already
receives. Checks run in a fixed order and stop at the first failure so
the recorded reason is deterministic; no partial order is placed. Verdicts
name the check that failed, never wallet or key material (T-17-06).

BLIND follows the amended rule, consulted here and not redefined: BLIND
data is KILL except SAFE-4 and SAFE-8 while no paid RPC provider is
recorded.

Thresholds are Decimal ratios from config, never float money. A missing
or unparsable mint list fails closed (every mint refused).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

__all__ = [
    "DEFAULT_HOLDER_LIMIT",
    "DEFAULT_MINT_LISTS_PATH",
    "EntryChecks",
    "EntryRefusal",
    "MintFacts",
    "MintListError",
    "load_mint_lists",
]

DEFAULT_MINT_LISTS_PATH = Path(__file__).resolve().parents[1] / "config" / "mint_lists.toml"

#: Holder concentration ceiling per V4-12 (fraction of supply held by holders).
DEFAULT_HOLDER_LIMIT = Decimal("0.30")

#: Mint-data classes exempt from BLIND-KILL while no paid provider is recorded.
BLIND_SAFE_CLASSES: frozenset[str] = frozenset({"SAFE-4", "SAFE-8"})


class MintListError(ValueError):
    """The mint list file is missing or unparsable; fail closed."""


@dataclass(frozen=True)
class MintFacts:
    """On-chain facts about one mint, as the engine already receives them."""

    mint: str
    authority_present: bool = False
    extensions: tuple[str, ...] = ()
    holder_concentration: Decimal = Decimal("0")
    blocklisted: bool = False
    allowlisted: bool = False
    blind: bool = False
    safe_class: str | None = None
    paid_rpc_recorded: bool = False


@dataclass(frozen=True)
class EntryRefusal:
    """A typed refusal: the check name plus a safe, key-free detail."""

    check: str
    detail: str

    def __str__(self) -> str:  # pragma: no cover - formatting helper
        return f"{self.check}: {self.detail}"


def load_mint_lists(path: Path | str | None = None) -> tuple[frozenset[str], frozenset[str]]:
    """Load (allowlist, blocklist) from the version-controlled TOML file.

    Raises MintListError when the file is missing or unparsable so the
    caller fails closed instead of skipping the list check (T-17-05).
    """
    target = Path(path) if path is not None else DEFAULT_MINT_LISTS_PATH
    if not target.exists():
        raise MintListError(f"mint list file missing: {target}")
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise MintListError(f"mint list file unparsable: {target}: {exc}") from exc
    allowlist = raw.get("allowlist", [])
    blocklist = raw.get("blocklist", [])
    if not isinstance(allowlist, list) or not isinstance(blocklist, list):
        raise MintListError(f"mint list entries must be lists: {target}")
    return frozenset(str(x) for x in allowlist), frozenset(str(x) for x in blocklist)


@dataclass(frozen=True)
class EntryChecks:
    """The fail-closed entry check suite; first failure wins."""

    holder_limit: Decimal = DEFAULT_HOLDER_LIMIT
    allowlist: frozenset[str] = field(default_factory=frozenset)
    blocklist: frozenset[str] = field(default_factory=frozenset)
    lists_available: bool = True

    @classmethod
    def from_mint_lists(
        cls,
        *,
        holder_limit: Decimal = DEFAULT_HOLDER_LIMIT,
        path: Path | str | None = None,
    ) -> EntryChecks:
        """Build from the version-controlled mint list file; fail closed."""
        try:
            allowlist, blocklist = load_mint_lists(path)
        except MintListError:
            return cls(holder_limit=holder_limit, lists_available=False)
        return cls(holder_limit=holder_limit, allowlist=allowlist, blocklist=blocklist)

    def check(self, facts: MintFacts) -> EntryRefusal | None:
        """Run every check in fixed order; first failure wins, else None."""
        if facts.authority_present:
            return EntryRefusal("authority", f"mint {facts.mint} has an authority")
        if facts.extensions:
            return EntryRefusal(
                "extension",
                f"mint {facts.mint} uses unsupported extensions {list(facts.extensions)}",
            )
        if facts.holder_concentration > self.holder_limit:
            return EntryRefusal(
                "holders", f"mint {facts.mint} holder concentration above {self.holder_limit}"
            )
        refusal = self._check_lists(facts)
        if refusal is not None:
            return refusal
        if facts.blind and not self._blind_exempt(facts):
            return EntryRefusal("blind", f"mint {facts.mint} data is BLIND")
        return None

    def _check_lists(self, facts: MintFacts) -> EntryRefusal | None:
        if not self.lists_available:
            return EntryRefusal("list", f"mint list unavailable; refusing {facts.mint} fail-closed")
        if facts.mint in self.blocklist or facts.blocklisted:
            return EntryRefusal("list", f"mint {facts.mint} is blocklisted")
        if self.allowlist and facts.mint not in self.allowlist and not facts.allowlisted:
            return EntryRefusal("list", f"mint {facts.mint} is not allowlisted")
        return None

    @staticmethod
    def _blind_exempt(facts: MintFacts) -> bool:
        """SAFE-4/SAFE-8 are exempt only while no paid RPC provider is recorded."""
        return facts.safe_class in BLIND_SAFE_CLASSES and not facts.paid_rpc_recorded
