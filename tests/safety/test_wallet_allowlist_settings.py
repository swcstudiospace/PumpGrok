"""Wallet allowlist, platform declaration and live notional cap settings.

The allowlist holds public keys only. Every rejected input must fail at
construction with ValidationError; no exact error text is asserted.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pumpgrok.config.settings import LiveSettings, PlatformSettings, WalletSettings

# 32 zero bytes in base58: the Solana system program, a valid public key.
SYSTEM_PROGRAM = "11111111111111111111111111111111"
# 88 leading '1' characters decode to 88 zero bytes, never 32: must be rejected.
EIGHTY_EIGHT_ONES = "1" * 88


def test_default_allowlist_is_empty() -> None:
    assert WalletSettings().allowlist == ()


def test_valid_public_key_is_accepted() -> None:
    settings = WalletSettings(allowlist=(SYSTEM_PROGRAM,))
    assert settings.allowlist == (SYSTEM_PROGRAM,)


def test_string_decoding_to_wrong_length_is_rejected() -> None:
    with pytest.raises(ValidationError):
        WalletSettings(allowlist=(EIGHTY_EIGHT_ONES,))


def test_character_outside_base58_alphabet_is_rejected() -> None:
    # '0' is not in the base58 alphabet; the rest of the string is valid.
    with pytest.raises(ValidationError):
        WalletSettings(allowlist=(SYSTEM_PROGRAM[:-1] + "0",))


@pytest.mark.parametrize(
    "entry",
    [SYSTEM_PROGRAM + " ", " " + SYSTEM_PROGRAM, SYSTEM_PROGRAM + "\n"],
)
def test_whitespace_is_rejected(entry: str) -> None:
    with pytest.raises(ValidationError):
        WalletSettings(allowlist=(entry,))


def test_platform_defaults_declare_solana_paper_quote_only() -> None:
    platform = PlatformSettings()
    assert platform.chain == "solana"
    assert platform.venue == "pumpfun-bonding-curve"
    assert platform.execution == "paper"
    assert platform.quote_only == ("jupiter-swap-v2",)


def test_platform_rejects_non_solana_chain() -> None:
    with pytest.raises(ValidationError):
        PlatformSettings(chain="ethereum")


def test_platform_rejects_live_execution() -> None:
    with pytest.raises(ValidationError):
        PlatformSettings(execution="live")


def test_live_notional_cap_defaults_to_one_sol() -> None:
    assert LiveSettings().notional_cap_lamports == 1_000_000_000


@pytest.mark.parametrize("cap", [0, 1_000_000_001])
def test_live_notional_cap_outside_range_is_rejected(cap: int) -> None:
    with pytest.raises(ValidationError):
        LiveSettings(notional_cap_lamports=cap)


@pytest.mark.parametrize("cap", [1, 1_000_000_000])
def test_live_notional_cap_inside_range_is_accepted(cap: int) -> None:
    assert LiveSettings(notional_cap_lamports=cap).notional_cap_lamports == cap
