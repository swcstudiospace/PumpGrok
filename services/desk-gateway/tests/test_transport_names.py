"""Transport names are exposure-only and unambiguous (T-03-05-03).

Dotted roster ids become underscore transport names at exposure time;
the way back is a forward-built roster dict, never a string reverse
replace (``onchain.token_metadata`` and ``risk.check_limits`` collide
under naive reversal). Injectivity holds registry-wide and per seat.
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.contracts.projection import (
    effective_roster,
    short_to_seat,
    transport_map,
    transport_name,
)

SERVER_PATH = Path(__file__).resolve().parents[1] / "src" / "desk_gateway" / "server.py"


def test_transport_names_use_underscore_form() -> None:
    assert transport_name("onchain.token_metadata") == "onchain_token_metadata"
    assert transport_name("risk.check_limits") == "risk_check_limits"
    assert transport_name("desk.brief") == "desk_brief"


def test_seat_maps_built_forward_from_roster(gateway):  # type: ignore[no-untyped-def]
    _base, _tokens, contracts_dir, _reg, _manifests = gateway
    for short, seat_id in sorted(short_to_seat(contracts_dir).items()):
        mapping = transport_map(seat_id, contracts_dir)
        expected = {
            transport_name(entry["name"]): entry["name"]
            for entry in effective_roster(seat_id, contracts_dir)
        }
        assert mapping == expected, short
        assert len(set(mapping)) == len(set(mapping.values())), short


def test_transport_mapping_injective_registry_wide(gateway):  # type: ignore[no-untyped-def]
    _base, _tokens, _contracts, registry, _manifests = gateway
    transports = [transport_name(name) for name in registry.names()]
    assert len(set(transports)) == len(transports), "transport collision over registry"
    assert len(registry.names()) == 37


def test_server_never_reverse_replaces_underscores() -> None:
    text = SERVER_PATH.read_text(encoding="utf-8")
    assert '.replace("_", ".")' not in text
    assert ".replace('_', '.')" not in text
