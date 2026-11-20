"""Pump event decoder round-trips the five event types (MKT-02, D-15).

Encoders here mirror the Anchor Borsh layouts the decoder reads: an 8-byte event
discriminator, then little-endian fields. Trailing bytes are ignored; truncation,
bad bools, bad UTF-8 and bad base64 raise EventDecodeError; unknown discriminators
raise UnknownEventError so callers can count them.
"""

from __future__ import annotations

import base64
import hashlib
import struct
from typing import Any

import pytest

from pumpgrok.tools.onchain.pump_events import (
    CompleteEvent,
    CompletePumpAmmMigrationEvent,
    CreateEvent,
    EventDecodeError,
    PostCompleteBuyEvent,
    TradeEvent,
    UnknownEventError,
    decode_event,
    decode_program_data,
)

DISC = {
    "TradeEvent": bytes.fromhex("bddb7fd34ee661ee"),
    "CreateEvent": bytes.fromhex("1b72a94ddeeb6376"),
    "CompleteEvent": bytes.fromhex("5f72619cd42e9808"),
    "CompletePumpAmmMigrationEvent": bytes.fromhex("bde95db95c94ea94"),
    "PostCompleteBuyEvent": bytes.fromhex("6fb06d8b316cd5fb"),
}

# Base58 pins: 31 leading zero bytes then 0x01 encodes as "1"*31 + "2".
KEY_A = "1" * 31 + "2"
RAW_A = bytes(31) + b"\x01"
# 31 leading zero bytes then 0x3a (58) encodes as "1"*31 + "21".
KEY_B = "1" * 31 + "21"
RAW_B = bytes(31) + b"\x3a"
KEY_Z = "1" * 32
RAW_Z = bytes(32)
_RAW = {KEY_A: RAW_A, KEY_B: RAW_B, KEY_Z: RAW_Z}


def _u64(value: int) -> bytes:
    return struct.pack("<Q", value)


def _i64(value: int) -> bytes:
    return struct.pack("<q", value)


def _bool(value: bool) -> bytes:
    return b"\x01" if value else b"\x00"


def _str(value: str) -> bytes:
    raw = value.encode("utf-8")
    return struct.pack("<I", len(raw)) + raw


def _pk(value: str) -> bytes:
    return _RAW[value]


def _encode_trade(e: TradeEvent) -> bytes:
    body = (
        _pk(e.mint)
        + _u64(e.sol_amount)
        + _u64(e.token_amount)
        + _bool(e.is_buy)
        + _pk(e.user)
        + _i64(e.timestamp)
        + _u64(e.virtual_sol_reserves)
        + _u64(e.virtual_token_reserves)
        + _u64(e.real_sol_reserves)
        + _u64(e.real_token_reserves)
        + _pk(e.fee_recipient)
        + _u64(e.fee_basis_points)
        + _u64(e.fee)
        + _pk(e.creator)
        + _u64(e.creator_fee_basis_points)
        + _u64(e.creator_fee)
        + _bool(e.track_volume)
        + _u64(e.total_unclaimed_tokens)
        + _u64(e.total_claimed_tokens)
        + _u64(e.current_sol_volume)
        + _i64(e.last_update_timestamp)
        + _str(e.ix_name)
        + _bool(e.mayhem_mode)
    )
    return DISC["TradeEvent"] + body


def _encode_create(e: CreateEvent) -> bytes:
    body = (
        _str(e.name)
        + _str(e.symbol)
        + _str(e.uri)
        + _pk(e.mint)
        + _pk(e.bonding_curve)
        + _pk(e.user)
        + _pk(e.creator)
        + _i64(e.timestamp)
        + _u64(e.virtual_token_reserves)
        + _u64(e.virtual_sol_reserves)
        + _u64(e.real_token_reserves)
        + _u64(e.token_total_supply)
    )
    return DISC["CreateEvent"] + body


def _encode_complete(e: CompleteEvent) -> bytes:
    body = _pk(e.user) + _pk(e.mint) + _pk(e.bonding_curve) + _i64(e.timestamp)
    return DISC["CompleteEvent"] + body


def _encode_migration(e: CompletePumpAmmMigrationEvent) -> bytes:
    body = (
        _pk(e.user)
        + _pk(e.mint)
        + _u64(e.mint_amount)
        + _u64(e.sol_amount)
        + _u64(e.pool_migration_fee)
        + _pk(e.bonding_curve)
        + _i64(e.timestamp)
        + _pk(e.pool)
    )
    return DISC["CompletePumpAmmMigrationEvent"] + body


def _encode_post_complete_buy(e: PostCompleteBuyEvent) -> bytes:
    body = _pk(e.user) + _pk(e.mint) + _u64(e.sol_amount) + _u64(e.token_amount) + _i64(e.timestamp)
    return DISC["PostCompleteBuyEvent"] + body


TRADE = TradeEvent(
    mint=KEY_A,
    sol_amount=1_500_000_000,
    token_amount=2_000_000_000_000,
    is_buy=True,
    user=KEY_B,
    timestamp=1_700_000_000,
    virtual_sol_reserves=30_000_000_000,
    virtual_token_reserves=1_073_000_000_000_000,
    real_sol_reserves=500_000_000,
    real_token_reserves=793_000_000_000_000,
    fee_recipient=KEY_Z,
    fee_basis_points=95,
    fee=14_250_000,
    creator=KEY_B,
    creator_fee_basis_points=5,
    creator_fee=750_000,
    track_volume=False,
    total_unclaimed_tokens=0,
    total_claimed_tokens=0,
    current_sol_volume=1_500_000_000,
    last_update_timestamp=1_700_000_001,
    ix_name="buy",
    mayhem_mode=False,
)
CREATE = CreateEvent(
    name="Pump Token",
    symbol="PMP",
    uri="https://example.invalid/meta.json",
    mint=KEY_A,
    bonding_curve=KEY_B,
    user=KEY_Z,
    creator=KEY_B,
    timestamp=1_700_000_000,
    virtual_token_reserves=1_073_000_000_000_000,
    virtual_sol_reserves=30_000_000_000,
    real_token_reserves=793_100_000_000_000,
    token_total_supply=1_000_000_000_000_000,
)
COMPLETE = CompleteEvent(user=KEY_A, mint=KEY_B, bonding_curve=KEY_Z, timestamp=1_700_000_500)
MIGRATION = CompletePumpAmmMigrationEvent(
    user=KEY_Z,
    mint=KEY_A,
    mint_amount=793_100_000_000_000,
    sol_amount=85_000_000_000,
    pool_migration_fee=2_000_000_000,
    bonding_curve=KEY_B,
    timestamp=1_700_000_600,
    pool=KEY_A,
)
POST_COMPLETE_BUY = PostCompleteBuyEvent(
    user=KEY_B,
    mint=KEY_Z,
    sol_amount=250_000_000,
    token_amount=1_000_000_000,
    timestamp=1_700_000_700,
)

CASES: list[tuple[str, Any, bytes]] = [
    ("TradeEvent", TRADE, _encode_trade(TRADE)),
    ("CreateEvent", CREATE, _encode_create(CREATE)),
    ("CompleteEvent", COMPLETE, _encode_complete(COMPLETE)),
    ("CompletePumpAmmMigrationEvent", MIGRATION, _encode_migration(MIGRATION)),
    ("PostCompleteBuyEvent", POST_COMPLETE_BUY, _encode_post_complete_buy(POST_COMPLETE_BUY)),
]
IDS = [name for name, _, _ in CASES]


@pytest.mark.parametrize("name", IDS)
def test_discriminator_is_anchor_event_hash(name: str) -> None:
    assert hashlib.sha256(f"event:{name}".encode()).digest()[:8] == DISC[name]


@pytest.mark.parametrize(("name", "event", "encoded"), CASES, ids=IDS)
def test_round_trip_raw_bytes(name: str, event: Any, encoded: bytes) -> None:
    assert decode_event(encoded) == event


@pytest.mark.parametrize(("name", "event", "encoded"), CASES, ids=IDS)
def test_round_trip_program_data_base64(name: str, event: Any, encoded: bytes) -> None:
    assert decode_program_data(base64.b64encode(encoded).decode("ascii")) == event


@pytest.mark.parametrize(("name", "event", "encoded"), CASES, ids=IDS)
def test_trailing_bytes_are_ignored(name: str, event: Any, encoded: bytes) -> None:
    assert decode_event(encoded + b"\xde\xad\xbe\xef") == event


@pytest.mark.parametrize(("name", "event", "encoded"), CASES, ids=IDS)
def test_every_truncation_raises_event_decode_error(name: str, event: Any, encoded: bytes) -> None:
    for cut in range(len(encoded)):
        with pytest.raises(EventDecodeError):
            decode_event(encoded[:cut])


@pytest.mark.parametrize(("name", "event", "encoded"), CASES, ids=IDS)
def test_truncated_program_data_raises(name: str, event: Any, encoded: bytes) -> None:
    truncated = base64.b64encode(encoded[:-1]).decode("ascii")
    with pytest.raises(EventDecodeError):
        decode_program_data(truncated)


def test_unknown_discriminator_is_counted_not_guessed() -> None:
    _, _, encoded = CASES[0]
    with pytest.raises(UnknownEventError):
        decode_event(bytes(8) + encoded[8:])
    assert issubclass(UnknownEventError, EventDecodeError)


def test_invalid_bool_byte_raises() -> None:
    encoded = bytearray(CASES[0][2])
    is_buy_offset = 8 + 32 + 8 + 8
    encoded[is_buy_offset] = 2
    with pytest.raises(EventDecodeError):
        decode_event(bytes(encoded))


def test_invalid_utf8_string_raises() -> None:
    encoded = DISC["CreateEvent"] + struct.pack("<I", 1) + b"\xff" + bytes(200)
    with pytest.raises(EventDecodeError):
        decode_event(encoded)


def test_invalid_base64_raises() -> None:
    with pytest.raises(EventDecodeError):
        decode_program_data("!!!not-base64!!!")


def test_amounts_are_integer_base_units() -> None:
    decoded = decode_event(CASES[0][2])
    assert isinstance(decoded, TradeEvent)
    assert type(decoded.sol_amount) is int
    assert type(decoded.token_amount) is int
    assert decoded.mayhem_mode is False
