"""Pump.fun event decoder (B01, MKT-02): Anchor ``Program data:`` payloads to typed events.

The logs source passes each base64 ``Program data:`` payload here. An Anchor event is an
8-byte discriminator (the sha256 prefix of ``event:<Name>``) followed by little-endian
Borsh fields. Decoding reads the fields in order and ignores appended bytes.

Truncation, an invalid bool byte, invalid UTF-8 and invalid base64 raise
:class:`EventDecodeError`. A discriminator outside the five known types raises
:class:`UnknownEventError` so the caller can count it; nothing is guessed.

Amounts are integer base units (lamports, token base units); timestamps are the chain's
unix seconds; pubkeys are base58 strings. Field order follows the public pump IDL as cited
in the v4 research (B-strategies-backtest-data, section 1). The discriminators are pinned;
the field layouts were approved by human review (``EVENT_DECODE_REVIEWED_BY``).
"""

from __future__ import annotations

import base64
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

# Set to VERIFIED only through human review; the approver is recorded in
# EVENT_DECODE_REVIEWED_BY. Decoding does not read this status.
EVENT_DECODE_STATUS: Final[str] = "VERIFIED"
EVENT_DECODE_REVIEWED_BY: Final[str] = "human:Ove"


class EventDecodeError(ValueError):
    """A pump event payload is truncated or malformed."""


class UnknownEventError(EventDecodeError):
    """The 8-byte discriminator is not one of the five pump event types."""


_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_DISCRIMINATOR_BYTES = 8
_PUBKEY_BYTES = 32


def _base58(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    digits: list[str] = []
    while number:
        number, remainder = divmod(number, 58)
        digits.append(_BASE58_ALPHABET[remainder])
    leading_zero_bytes = len(raw) - len(raw.lstrip(b"\x00"))
    return "1" * leading_zero_bytes + "".join(reversed(digits))


@dataclass(frozen=True, slots=True)
class TradeEvent:
    mint: str
    sol_amount: int
    token_amount: int
    is_buy: bool
    user: str
    timestamp: int
    virtual_sol_reserves: int
    virtual_token_reserves: int
    real_sol_reserves: int
    real_token_reserves: int
    fee_recipient: str
    fee_basis_points: int
    fee: int
    creator: str
    creator_fee_basis_points: int
    creator_fee: int
    track_volume: bool
    total_unclaimed_tokens: int
    total_claimed_tokens: int
    current_sol_volume: int
    last_update_timestamp: int
    ix_name: str
    mayhem_mode: bool


@dataclass(frozen=True, slots=True)
class CreateEvent:
    name: str
    symbol: str
    uri: str
    mint: str
    bonding_curve: str
    user: str
    creator: str
    timestamp: int
    virtual_token_reserves: int
    virtual_sol_reserves: int
    real_token_reserves: int
    token_total_supply: int


@dataclass(frozen=True, slots=True)
class CompleteEvent:
    user: str
    mint: str
    bonding_curve: str
    timestamp: int


@dataclass(frozen=True, slots=True)
class CompletePumpAmmMigrationEvent:
    user: str
    mint: str
    mint_amount: int
    sol_amount: int
    pool_migration_fee: int
    bonding_curve: str
    timestamp: int
    pool: str


@dataclass(frozen=True, slots=True)
class PostCompleteBuyEvent:
    user: str
    mint: str
    sol_amount: int
    token_amount: int
    timestamp: int


type PumpEvent = (
    TradeEvent | CreateEvent | CompleteEvent | CompletePumpAmmMigrationEvent | PostCompleteBuyEvent
)


class _Reader:
    """Sequential little-endian Borsh reader; every short read is a typed error."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def _take(self, count: int) -> bytes:
        end = self._pos + count
        if end > len(self._data):
            raise EventDecodeError(
                f"truncated event: need {count} bytes at offset {self._pos}, have {len(self._data)}"
            )
        chunk = self._data[self._pos : end]
        self._pos = end
        return chunk

    def u32(self) -> int:
        return int(struct.unpack("<I", self._take(4))[0])

    def u64(self) -> int:
        return int(struct.unpack("<Q", self._take(8))[0])

    def i64(self) -> int:
        return int(struct.unpack("<q", self._take(8))[0])

    def boolean(self) -> bool:
        byte = self._take(1)[0]
        if byte > 1:
            raise EventDecodeError(f"invalid bool byte {byte} at offset {self._pos - 1}")
        return byte == 1

    def pubkey(self) -> str:
        return _base58(self._take(_PUBKEY_BYTES))

    def string(self) -> str:
        length = self.u32()
        raw = self._take(length)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EventDecodeError("invalid UTF-8 in event string") from exc


def _decode_trade(r: _Reader) -> TradeEvent:
    return TradeEvent(
        mint=r.pubkey(),
        sol_amount=r.u64(),
        token_amount=r.u64(),
        is_buy=r.boolean(),
        user=r.pubkey(),
        timestamp=r.i64(),
        virtual_sol_reserves=r.u64(),
        virtual_token_reserves=r.u64(),
        real_sol_reserves=r.u64(),
        real_token_reserves=r.u64(),
        fee_recipient=r.pubkey(),
        fee_basis_points=r.u64(),
        fee=r.u64(),
        creator=r.pubkey(),
        creator_fee_basis_points=r.u64(),
        creator_fee=r.u64(),
        track_volume=r.boolean(),
        total_unclaimed_tokens=r.u64(),
        total_claimed_tokens=r.u64(),
        current_sol_volume=r.u64(),
        last_update_timestamp=r.i64(),
        ix_name=r.string(),
        mayhem_mode=r.boolean(),
    )


def _decode_create(r: _Reader) -> CreateEvent:
    return CreateEvent(
        name=r.string(),
        symbol=r.string(),
        uri=r.string(),
        mint=r.pubkey(),
        bonding_curve=r.pubkey(),
        user=r.pubkey(),
        creator=r.pubkey(),
        timestamp=r.i64(),
        virtual_token_reserves=r.u64(),
        virtual_sol_reserves=r.u64(),
        real_token_reserves=r.u64(),
        token_total_supply=r.u64(),
    )


def _decode_complete(r: _Reader) -> CompleteEvent:
    return CompleteEvent(
        user=r.pubkey(),
        mint=r.pubkey(),
        bonding_curve=r.pubkey(),
        timestamp=r.i64(),
    )


def _decode_migration(r: _Reader) -> CompletePumpAmmMigrationEvent:
    return CompletePumpAmmMigrationEvent(
        user=r.pubkey(),
        mint=r.pubkey(),
        mint_amount=r.u64(),
        sol_amount=r.u64(),
        pool_migration_fee=r.u64(),
        bonding_curve=r.pubkey(),
        timestamp=r.i64(),
        pool=r.pubkey(),
    )


def _decode_post_complete_buy(r: _Reader) -> PostCompleteBuyEvent:
    return PostCompleteBuyEvent(
        user=r.pubkey(),
        mint=r.pubkey(),
        sol_amount=r.u64(),
        token_amount=r.u64(),
        timestamp=r.i64(),
    )


_DECODERS: dict[bytes, Callable[[_Reader], PumpEvent]] = {
    bytes.fromhex("bddb7fd34ee661ee"): _decode_trade,
    bytes.fromhex("1b72a94ddeeb6376"): _decode_create,
    bytes.fromhex("5f72619cd42e9808"): _decode_complete,
    bytes.fromhex("bde95db95c94ea94"): _decode_migration,
    bytes.fromhex("6fb06d8b316cd5fb"): _decode_post_complete_buy,
}


def decode_event(raw: bytes) -> PumpEvent:
    """Decode one event from its raw bytes (discriminator first); trailing bytes are ignored."""
    if len(raw) < _DISCRIMINATOR_BYTES:
        raise EventDecodeError(
            f"truncated event: {len(raw)} bytes, need {_DISCRIMINATOR_BYTES} for discriminator"
        )
    discriminator = raw[:_DISCRIMINATOR_BYTES]
    decoder = _DECODERS.get(discriminator)
    if decoder is None:
        raise UnknownEventError(f"unknown event discriminator {discriminator.hex()}")
    return decoder(_Reader(raw[_DISCRIMINATOR_BYTES:]))


def decode_program_data(encoded: str) -> PumpEvent:
    """Decode one base64 ``Program data:`` payload from a pump program invocation."""
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise EventDecodeError("invalid base64 in program data") from exc
    return decode_event(raw)
