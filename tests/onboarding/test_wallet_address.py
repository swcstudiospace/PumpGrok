"""ONB-06: a non-paper wallet address is base58, exactly 32 bytes and an Ed25519 curve point.

The operator must also confirm each allowlist address by typing it again. No refusal names or
echoes an address or any input value: the assertions below check the exception text and the
captured stdout and stderr.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from pumpgrok.cli import dispatch as dispatch_mod
from pumpgrok.config import settings as settings_mod
from pumpgrok.core.ed25519_point import decode_public_point

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# RFC 8032 section 7.1, TEST 1 public key: a valid Ed25519 point.
RFC8032_TEST1_PUBLIC = bytes.fromhex(
    "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
)


def _b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    digits = ""
    while number:
        number, remainder = divmod(number, 58)
        digits = _B58[remainder] + digits
    leading_zeros = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * leading_zeros + digits


def _off_curve_key() -> bytes:
    """First 32-byte value with canonical y that is not on the curve (found deterministically)."""
    for y in range(2, 256):
        raw = y.to_bytes(32, "little")
        try:
            decode_public_point(raw)
        except ValueError:
            return raw
    raise AssertionError("no off-curve vector in range")


VALID_ENTRY = _b58encode(RFC8032_TEST1_PUBLIC)
OFF_CURVE_ENTRY = _b58encode(_off_curve_key())
# y = 2**255 - 1 is at least p: a non-canonical encoding of the point decoder refuses.
NON_CANONICAL_ENTRY = _b58encode(b"\xff" * 31 + b"\x7f")
# 32 zero bytes, base58 "1" x 32: the all-zero system program address (y = 0, order 4).
ALL_ZERO_ENTRY = _b58encode(bytes(32))


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_rfc8032_public_key_is_accepted_as_base58() -> None:
    assert settings_mod.WalletSettings(allowlist=(VALID_ENTRY,)).allowlist == (VALID_ENTRY,)


def test_off_curve_32_byte_base58_is_rejected() -> None:
    with pytest.raises(ValidationError):
        settings_mod.WalletSettings(allowlist=(OFF_CURVE_ENTRY,))


def test_non_canonical_y_is_rejected() -> None:
    with pytest.raises(ValidationError):
        settings_mod.WalletSettings(allowlist=(NON_CANONICAL_ENTRY,))


@pytest.mark.parametrize(
    "raw",
    [RFC8032_TEST1_PUBLIC[:31], RFC8032_TEST1_PUBLIC + b"\x00", b""],
    ids=["31-bytes", "33-bytes", "empty"],
)
def test_wrong_length_is_rejected(raw: bytes) -> None:
    with pytest.raises(ValidationError):
        settings_mod.WalletSettings(allowlist=(_b58encode(raw),))


@pytest.mark.parametrize("entry", ["0OIl", " " + VALID_ENTRY, VALID_ENTRY + "\n", "1" * 88])
def test_non_base58_or_padded_text_is_rejected(entry: str) -> None:
    with pytest.raises(ValidationError):
        settings_mod.WalletSettings(allowlist=(entry,))


def test_refusal_never_echoes_the_address() -> None:
    with pytest.raises(ValidationError) as excinfo:
        settings_mod.WalletSettings(allowlist=(VALID_ENTRY, OFF_CURVE_ENTRY))
    assert OFF_CURVE_ENTRY not in str(excinfo.value)
    assert "allowlist" in str(excinfo.value)


def test_live_load_refusal_names_the_field_and_not_the_value(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setenv("PUMPGROK_MODE", "live")
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", f'["{OFF_CURVE_ENTRY}"]')
    with pytest.raises(settings_mod.ConfigError) as excinfo:
        settings_mod.load_settings()
    text = str(excinfo.value) + "".join(excinfo.value.problems)
    assert "wallet" in text
    assert OFF_CURVE_ENTRY not in text
    out, err = capsys.readouterr()
    assert OFF_CURVE_ENTRY not in out + err


def test_all_zero_address_is_refused_in_live_mode(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    # 32 zero bytes (the system program address) decode to y = 0, a point of order 4.
    monkeypatch.setenv("PUMPGROK_MODE", "live")
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", f'["{ALL_ZERO_ENTRY}"]')
    with pytest.raises(settings_mod.ConfigError) as excinfo:
        settings_mod.load_settings()
    text = str(excinfo.value) + "".join(excinfo.value.problems)
    assert "wallet" in text
    assert ALL_ZERO_ENTRY not in text
    out, err = capsys.readouterr()
    assert ALL_ZERO_ENTRY not in out + err


def test_empty_allowlist_needs_no_confirmation() -> None:
    def never(prompt: str) -> str:
        raise AssertionError("no prompt for an empty allowlist")

    settings_mod.confirm_wallet_allowlist((), never)


def test_exact_retyped_addresses_confirm() -> None:
    typed = iter([VALID_ENTRY, OFF_CURVE_ENTRY])
    prompts: list[str] = []

    def read_line(prompt: str) -> str:
        prompts.append(prompt)
        return next(typed)

    settings_mod.confirm_wallet_allowlist((VALID_ENTRY, OFF_CURVE_ENTRY), read_line)
    assert len(prompts) == 2
    assert all(VALID_ENTRY not in p and OFF_CURVE_ENTRY not in p for p in prompts)


def test_surrounding_whitespace_on_retype_is_tolerated() -> None:
    settings_mod.confirm_wallet_allowlist((VALID_ENTRY,), lambda _prompt: f"  {VALID_ENTRY} ")


@pytest.mark.parametrize("typed", ["", "y", "yes", VALID_ENTRY[:-1]])
def test_mismatch_or_empty_refuses_and_names_index_only(typed: str) -> None:
    with pytest.raises(settings_mod.ConfigError) as excinfo:
        settings_mod.confirm_wallet_allowlist((VALID_ENTRY,), lambda _prompt: typed)
    text = str(excinfo.value)
    assert "entry 0" in text
    assert VALID_ENTRY not in text


def test_each_entry_is_confirmed_in_order_with_no_auto_confirm() -> None:
    answers = [VALID_ENTRY, "not the second"]
    calls: list[str] = []

    def read_line(prompt: str) -> str:
        calls.append(prompt)
        return answers[len(calls) - 1]

    with pytest.raises(settings_mod.ConfigError) as excinfo:
        settings_mod.confirm_wallet_allowlist((VALID_ENTRY, OFF_CURVE_ENTRY), read_line)
    assert len(calls) == 2
    assert "entry 1" in str(excinfo.value)
    assert "entry 0" not in str(excinfo.value)


def test_live_run_refused_without_interactive_terminal(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("PUMPGROK_MODE", "live")
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", f'["{VALID_ENTRY}"]')
    monkeypatch.setattr(dispatch_mod, "_stdio_is_interactive", lambda: False)
    monkeypatch.chdir(tmp_path)
    assert dispatch_mod.main(["run", "--once", "--replay", SMOKE]) == dispatch_mod.EXIT_CONFIG
    out, err = capsys.readouterr()
    assert "interactive terminal" in err
    assert VALID_ENTRY not in out + err


def test_live_run_refused_when_typed_address_does_not_match(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("PUMPGROK_MODE", "live")
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", f'["{VALID_ENTRY}"]')
    monkeypatch.setattr(dispatch_mod, "_stdio_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "wrong")
    monkeypatch.chdir(tmp_path)
    assert dispatch_mod.main(["run", "--once", "--replay", SMOKE]) == dispatch_mod.EXIT_CONFIG
    out, err = capsys.readouterr()
    assert VALID_ENTRY not in out + err


def test_live_run_proceeds_to_the_gate_only_after_typed_match(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("PUMPGROK_MODE", "live")
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", f'["{VALID_ENTRY}"]')
    monkeypatch.setattr(dispatch_mod, "_stdio_is_interactive", lambda: True)
    prompts: list[str] = []

    def typed(prompt: str = "") -> str:
        prompts.append(prompt)
        return VALID_ENTRY

    monkeypatch.setattr("builtins.input", typed)
    monkeypatch.chdir(tmp_path)
    code = dispatch_mod.main(["run", "--once", "--replay", SMOKE])
    out, err = capsys.readouterr()
    assert len(prompts) == 1
    assert code == 3, "after the typed match the live gate, not the confirmation, refuses"
    assert "LIVE GATE" in err
    assert VALID_ENTRY not in out + err


def test_confirmation_is_not_required_for_paper_or_read_only_verbs(
    clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PUMPGROK_WALLET__ALLOWLIST", f'["{VALID_ENTRY}"]')
    monkeypatch.setattr(dispatch_mod, "_stdio_is_interactive", lambda: False)
    monkeypatch.chdir(tmp_path)
    assert dispatch_mod.main(["run", "--mode", "paper", "--once", "--replay", SMOKE]) == 0


