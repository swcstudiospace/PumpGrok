"""Entry checks: reject unsafe mints before a BUY (RSK-05, D17-6, S-E1).

Pure functions over the safety payloads for one mint. Every missing input is
a rejection, never a pass (fail closed): a missing authority field, a missing
or duplicated REQUIRED_IDS result, and absent extension or concentration data
all reject. A BLIND REQUIRED_IDS result rejects too, except the SAFE-4/SAFE-8
holder pair while no paid RPC provider is recorded: that pair only warns
(amendment 2026-10-25, mirroring score_report). Thresholds come from
``SafetyThresholds`` (config), never literals. The checks read no clock, no
file and schedule nothing; the caller supplies the advisory flag.

``tools/safety/checks/readers.py`` is not changed. The Token-2022 classification
lives here, over the same extension list that the readers only warn on.
"""

from __future__ import annotations

import math
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from pumpgrok.config.settings import SafetyThresholds
from pumpgrok.tools.safety.checks import HOLDER_ADVISORY_PAIR, REQUIRED_IDS, CheckResult

__all__ = [
    "DEFAULT_HOLDER_LIMIT",
    "DEFAULT_MINT_LISTS_PATH",
    "REJECT_EXTENSIONS",
    "EntryChecks",
    "EntryRefusal",
    "EntryVerdict",
    "MintFacts",
    "MintLists",
    "default_mint_lists_path",
    "evaluate_entry",
    "load_mint_lists",
]

# Matched against the lowercased, alphanumeric-only text of each extension
# entry. token_metadata stores ``str(e)`` of each RPC record, so a bare name
# ("transferHook") and a record repr ("{'extension': 'transferHook', ...}")
# both match.
REJECT_EXTENSIONS: Mapping[str, str] = {
    "permanentdelegate": "PermanentDelegate",
    "transferhook": "TransferHook",
    "nontransferable": "NonTransferable",
}

# Authority metadata keys, as produced by tools/onchain/authorities_tool.py.
_AUTHORITY_FIELDS: Mapping[str, str] = {
    "has_mint_authority": "mint authority",
    "has_freeze_authority": "freeze authority",
}

_LIST_KEYS: tuple[str, ...] = ("deny", "warn")

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


@dataclass(frozen=True)
class EntryEvidence:
    """Safety payloads for one mint. ``None`` marks data that was not produced.

    ``authorities``: the authorities reader payload (``has_mint_authority``,
    ``has_freeze_authority``). ``extensions``: Token-2022 extension entries.
    ``top10_share``: top-10 supply share as a fraction (0..1). ``checks``: the
    score-report rows for the mint.
    """

    mint: str
    authorities: Mapping[str, Any] | None
    extensions: Sequence[str] | None
    top10_share: float | None
    checks: Sequence[CheckResult] | None


class EntryVerdict(BaseModel):
    """Entry decision: ``ok`` is False exactly when ``reasons`` is non-empty."""

    model_config = ConfigDict(frozen=True)

    mint: str
    ok: bool
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class MintLists:
    """Mint lists: ``deny`` rejects at entry, ``warn`` enters with a warning."""

    deny: frozenset[str]
    warn: frozenset[str]


def default_mint_lists_path() -> Path:
    """In-package mint_lists.toml path."""
    return Path(__file__).resolve().parents[1] / "config" / "mint_lists.toml"


def load_mint_lists(path: Path | str | None = None) -> MintLists:
    """Read and validate the mint lists, failing closed.

    A missing or unreadable file raises OSError; a malformed file raises
    ValueError (tomllib.TOMLDecodeError is a ValueError). Either way the
    caller does not enter.
    """
    resolved = Path(path) if path is not None else default_mint_lists_path()
    if not resolved.exists():
        raise MintListError(f"mint list file missing: {resolved}")
    with open(resolved, "rb") as handle:
        raw = tomllib.load(handle)
    if set(raw) != set(_LIST_KEYS):
        raise ValueError(
            f"mint lists {resolved}: expected exactly the keys {_LIST_KEYS}, found {sorted(raw)}"
        )
    parsed: dict[str, frozenset[str]] = {}
    for key in _LIST_KEYS:
        value = raw[key]
        if not isinstance(value, list) or not all(isinstance(mint, str) and mint for mint in value):
            raise ValueError(
                f"mint lists {resolved}: {key} must be a list of non-empty mint strings"
            )
        parsed[key] = frozenset(value)
    return MintLists(deny=parsed["deny"], warn=parsed["warn"])


@dataclass(frozen=True)
class EntryChecks:
    """The fail-closed entry check suite; first failure wins."""

    holder_limit: Decimal = DEFAULT_HOLDER_LIMIT
    allowlist: frozenset[str] = field(default_factory=frozenset)
    blocklist: frozenset[str] = field(default_factory=frozenset)
    lists_available: bool = True
    #: True while no paid RPC provider is recorded: a BLIND SAFE-4 holder row
    #: only warns instead of rejecting (amendment 2026-10-25). The composition
    #: root stamps this from ``tools/safety/provider`` at build time.
    holder_blind_advisory: bool = False

    @classmethod
    def from_mint_lists(
        cls,
        *,
        holder_limit: Decimal = DEFAULT_HOLDER_LIMIT,
        path: Path | str | None = None,
    ) -> EntryChecks:
        try:
            mint_lists = load_mint_lists(path)
        except (OSError, ValueError):
            return cls(holder_limit=holder_limit, lists_available=False)
        allowlist = mint_lists.deny
        blocklist = mint_lists.warn
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


def evaluate_entry(
    evidence: EntryEvidence,
    lists: MintLists,
    thresholds: SafetyThresholds,
    *,
    holder_blind_advisory: bool,
) -> EntryVerdict:
    """Decide whether ``evidence.mint`` may be entered; every absence rejects.

    ``holder_blind_advisory`` is the caller's ``not paid_rpc_provider_recorded()``
    (tools/safety/provider.py), the same gate score_report uses. While it is
    True a BLIND SAFE-4/SAFE-8 row warns; otherwise it rejects.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    if evidence.mint in lists.deny:
        reasons.append("mint is on the deny list")
    if evidence.mint in lists.warn:
        warnings.append("mint is on the warn list")
    _check_required(evidence.checks, holder_blind_advisory, reasons, warnings)
    _check_authorities(evidence.authorities, reasons)
    _check_extensions(evidence.extensions, reasons, warnings)
    _check_concentration(evidence.top10_share, thresholds, reasons, warnings)
    return EntryVerdict(
        mint=evidence.mint,
        ok=not reasons,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def _check_required(
    checks: Sequence[CheckResult] | None,
    holder_blind_advisory: bool,
    reasons: list[str],
    warnings: list[str],
) -> None:
    """Every REQUIRED_IDS id needs exactly one result; a BLIND one rejects.

    The holder pair is the exception while ``holder_blind_advisory`` is set: its
    BLIND row warns. An absent row always rejects, advisory or not. Advisory
    ids (outside REQUIRED_IDS) are blind by construction and never reject.
    """
    if checks is None:
        reasons.append("safety report missing")
        return
    by_id: dict[str, CheckResult] = {}
    for result in checks:
        if result.id in by_id:
            reasons.append(f"duplicate result for check {result.id}")
        by_id[result.id] = result
    for check_id in sorted(REQUIRED_IDS):
        row = by_id.get(check_id)
        if row is None:
            reasons.append(f"required check {check_id} has no result")
        elif row.status == "blind":
            if holder_blind_advisory and check_id in HOLDER_ADVISORY_PAIR:
                warnings.append(
                    f"required check {check_id} is blind; advisory while no paid RPC provider"
                    " is recorded"
                )
            else:
                reasons.append(f"required check {check_id} is blind")


def _check_authorities(authorities: Mapping[str, Any] | None, reasons: list[str]) -> None:
    """A live mint or freeze authority rejects; a missing field rejects."""
    if authorities is None:
        reasons.append("authority metadata missing")
        return
    for name, label in _AUTHORITY_FIELDS.items():
        value = authorities.get(name)
        if not isinstance(value, bool):
            reasons.append(f"{name} missing from authority metadata")
        elif value:
            reasons.append(f"{label} is live")


def _normalise(entry: object) -> str:
    return "".join(ch for ch in str(entry).lower() if ch.isalnum())


def _check_extensions(
    extensions: Sequence[str] | None, reasons: list[str], warnings: list[str]
) -> None:
    """PermanentDelegate, TransferHook and NonTransferable reject; others warn."""
    if extensions is None:
        reasons.append("token-2022 extension data missing")
        return
    for entry in extensions:
        text = _normalise(entry)
        rejected = next((name for name in REJECT_EXTENSIONS if name in text), None)
        if rejected is not None:
            reasons.append(f"token-2022 extension {REJECT_EXTENSIONS[rejected]} is rejected")
        else:
            warnings.append(f"token-2022 extension present: {entry}")


def _pct(share: float) -> float:
    """Share as a percent, computed in Decimal the way readers.py does."""
    return float(Decimal(str(share)) * Decimal(100))


def _check_concentration(
    top10_share: float | None,
    thresholds: SafetyThresholds,
    reasons: list[str],
    warnings: list[str],
) -> None:
    """Top-10 at or above the fail threshold rejects; at or above warn warns."""
    if top10_share is None:
        reasons.append("top-10 concentration missing")
        return
    try:
        pct = _pct(top10_share)
    except (ArithmeticError, ValueError):
        reasons.append("top-10 concentration is not a number")
        return
    if not math.isfinite(pct) or pct < 0:
        reasons.append("top-10 concentration is not a valid share")
    elif pct >= thresholds.top10_concentration_fail_pct:
        reasons.append(
            f"top-10 holders own {pct:.2f}% (fail at {thresholds.top10_concentration_fail_pct}%)"
        )
    elif pct >= thresholds.top10_concentration_warn_pct:
        warnings.append(
            f"top-10 holders own {pct:.2f}% (warn at {thresholds.top10_concentration_warn_pct}%)"
        )
