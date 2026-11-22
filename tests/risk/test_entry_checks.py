"""RSK-05: authority, extension, holder, list and BLIND cases are rejected.

One test per case class plus the missing-file fail-closed case, each with
a passing control mint. Mint facts are fabricated structs; no network.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import pytest

from pumpgrok.execution.entry_hook import EntryHook, EntryRefusedError
from pumpgrok.risk.entry_checks import (
    EntryChecks,
    MintFacts,
    MintListError,
    load_mint_lists,
)

MINT_OK = "So11111111111111111111111111111111111111112"
MINT_BAD = "So99999999999999999999999999999999999999999"


def _checks() -> EntryChecks:
    return EntryChecks(
        holder_limit=Decimal("0.30"),
        allowlist=frozenset({MINT_OK}),
        blocklist=frozenset({MINT_BAD}),
    )


def _ok(**overrides: object) -> MintFacts:
    facts: dict[str, object] = {"mint": MINT_OK}
    facts.update(overrides)
    return MintFacts(**facts)  # type: ignore[arg-type]


def test_control_mint_passes() -> None:
    assert _checks().check(_ok()) is None


def test_authority_present_is_rejected() -> None:
    refusal = _checks().check(_ok(authority_present=True))
    assert refusal is not None
    assert refusal.check == "authority"


def test_token2022_extension_is_rejected() -> None:
    refusal = _checks().check(_ok(extensions=("memo",)))
    assert refusal is not None
    assert refusal.check == "extension"


def test_holder_concentration_above_limit_is_rejected() -> None:
    refusal = _checks().check(_ok(holder_concentration=Decimal("0.31")))
    assert refusal is not None
    assert refusal.check == "holders"


def test_holder_concentration_at_limit_passes() -> None:
    assert _checks().check(_ok(holder_concentration=Decimal("0.30"))) is None


def test_blocklisted_mint_is_rejected() -> None:
    refusal = _checks().check(_ok(mint=MINT_BAD))
    assert refusal is not None
    assert refusal.check == "list"


def test_unlisted_mint_is_rejected_when_allowlist_present() -> None:
    refusal = _checks().check(_ok(mint="So22222222222222222222222222222222222"))
    assert refusal is not None
    assert refusal.check == "list"


def test_blind_is_kill() -> None:
    refusal = _checks().check(_ok(blind=True))
    assert refusal is not None
    assert refusal.check == "blind"


def test_blind_safe_class_exempt_without_paid_rpc() -> None:
    assert _checks().check(_ok(blind=True, safe_class="SAFE-4")) is None
    assert _checks().check(_ok(blind=True, safe_class="SAFE-8")) is None


def test_blind_safe_class_kills_with_paid_rpc() -> None:
    refusal = _checks().check(_ok(blind=True, safe_class="SAFE-4", paid_rpc_recorded=True))
    assert refusal is not None
    assert refusal.check == "blind"


def test_first_failure_wins_in_fixed_order() -> None:
    refusal = _checks().check(_ok(authority_present=True, extensions=("memo",), blind=True))
    assert refusal is not None
    assert refusal.check == "authority"


def test_missing_mint_list_file_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(MintListError):
        load_mint_lists(tmp_path / "nope.toml")
    checks = EntryChecks.from_mint_lists(path=tmp_path / "nope.toml")
    assert checks.lists_available is False
    refusal = checks.check(_ok())
    assert refusal is not None
    assert refusal.check == "list"


def test_unparsable_mint_list_fails_closed(tmp_path: Path) -> None:
    bad = tmp_path / "mint_lists.toml"
    bad.write_text("allowlist = [", encoding="utf-8")
    checks = EntryChecks.from_mint_lists(path=bad)
    assert checks.lists_available is False
    assert checks.check(_ok()) is not None


def test_mint_lists_toml_parses_as_toml() -> None:
    import tomllib

    path = Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "config" / "mint_lists.toml"
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw["allowlist"], list)
    assert isinstance(raw["blocklist"], list)


def test_hook_refuses_bad_mint_before_adapter() -> None:
    hook = EntryHook()
    with pytest.raises(EntryRefusedError):
        hook.check_place(
            side="buy",
            curve_source="replay",
            entry_checks=_checks(),
            mint_facts=_ok(authority_present=True),
        )


def test_hook_passes_sells_through_untouched() -> None:
    hook = EntryHook()
    hook.check_place(
        side="sell",
        curve_source="replay",
        entry_checks=_checks(),
        mint_facts=_ok(authority_present=True),
    )


def test_hook_without_checks_behaves_as_before() -> None:
    hook = EntryHook()
    hook.check_place(side="buy", curve_source="replay")
