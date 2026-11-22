"""Wallet addresses must decode to 32 bytes and be curve points."""

from pumpgrok.onboarding.validators import is_valid_wallet_address, refuse_wallet

# A known-valid Solana base58 public key (32 bytes, on the Ed25519 curve).
VALID = "11111111111111111111111111111111"


def test_validator_table() -> None:
    assert is_valid_wallet_address(VALID)
    assert not is_valid_wallet_address("")
    assert not is_valid_wallet_address("0OIl")
    assert not is_valid_wallet_address("1" * 10)
    assert not is_valid_wallet_address("z" * 60)


def test_refusal_never_echoes_value() -> None:
    bad = "0OIl-not-base58"
    message = refuse_wallet(bad)
    assert message
    assert bad not in message
    assert "wallet_public_address" in message
    assert refuse_wallet(VALID) == ""
