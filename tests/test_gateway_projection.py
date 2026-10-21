"""Gateway projection units for the root -k gateway selector (TOOL-010 half).

The service (plan 03-05) serves these helpers; the root suite pins them
here so `uv run pytest -q -k "least_privilege or gateway"` collects
gateway-named tests without entering services/. Rules under test: the
effective roster for a seat equals its own tools plus the core eight, the
transport name is dotted-with-underscores at exposure time, and the
transport-to-dotted map is built forward from the roster entries (never by
reversing a string replace, since names contain underscores).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

import yaml

from pumpgrok.contracts import projection as facade
from pumpgrok.core.manifests import (
    EXPECTED_SEAT_IDS,
    effective_roster,
    transport_map,
    transport_name,
)
from registry_harness import ROSTERS_DIR, build_full_registry


def _roster_tools(seat_id: str) -> list[dict]:
    doc = yaml.safe_load((ROSTERS_DIR / f"{seat_id}.yaml").read_text(encoding="utf-8"))
    core = yaml.safe_load((ROSTERS_DIR / "_core.yaml").read_text(encoding="utf-8"))
    own = [dict(entry) for entry in doc["tools"]]
    return own + [dict(entry) for entry in core["tools"]]


def test_effective_roster_matches_yaml_for_every_seat() -> None:
    for seat_id in EXPECTED_SEAT_IDS:
        projected = effective_roster(ROSTERS_DIR, seat_id)
        assert [entry["name"] for entry in projected] == [
            entry["name"] for entry in _roster_tools(seat_id)
        ], seat_id


def test_effective_roster_schemas_verbatim() -> None:
    projected = {entry["name"]: entry for entry in effective_roster(ROSTERS_DIR, "bot-04-sniper")}
    assert projected["exec.place"]["input"]["required"] == [
        "ticket_id",
        "mint",
        "side",
        "decision_id",
        "size_lamports",
        "max_slippage_bps",
        "approval_id",
        "rollback_plan",
    ]
    assert (
        projected["desk.brief"]["input"]
        == _roster_tools("bot-04-sniper")[
            next(
                i
                for i, entry in enumerate(_roster_tools("bot-04-sniper"))
                if entry["name"] == "desk.brief"
            )
        ]["input"]
    )


def test_transport_names_use_underscore_form() -> None:
    assert transport_name("onchain.token_metadata") == "onchain_token_metadata"
    assert transport_name("risk.check_limits") == "risk_check_limits"
    assert transport_name("desk.brief") == "desk_brief"


def test_transport_map_built_forward_from_roster() -> None:
    for seat_id in EXPECTED_SEAT_IDS:
        mapping = transport_map(ROSTERS_DIR, seat_id)
        expected = {
            entry["name"].replace(".", "_"): entry["name"] for entry in _roster_tools(seat_id)
        }
        assert mapping == expected, seat_id
        # the underscore form of an underscored name is ambiguous in reverse:
        # desk.memory_retain must be found by dict lookup, never by replace.
        assert mapping["desk_memory_retain"] == "desk.memory_retain"


def test_transport_mapping_injective_over_registry(tmp_path: Path) -> None:
    reg, _, _ = build_full_registry(tmp_path)
    transports = [transport_name(name) for name in reg.names()]
    assert len(set(transports)) == len(transports), "transport collision over registry"
    assert len(reg.names()) == 37


def test_contracts_facade_matches_manifests_for_every_seat() -> None:
    """The service import path is a pure facade: no drift from the loader."""
    assert facade.default_contracts_dir() == ROSTERS_DIR
    for seat_id in EXPECTED_SEAT_IDS:
        assert facade.effective_roster(seat_id) == effective_roster(ROSTERS_DIR, seat_id), seat_id
        assert facade.transport_map(seat_id) == transport_map(ROSTERS_DIR, seat_id), seat_id
        entries = facade.exposure_entries(seat_id)
        assert [entry["name"] for entry in entries] == [
            transport_name(entry["name"]) for entry in effective_roster(ROSTERS_DIR, seat_id)
        ], seat_id
        assert all(set(entry) == {"name", "description", "inputSchema"} for entry in entries), (
            seat_id
        )


def test_contracts_facade_short_maps_match_roster_endpoints() -> None:
    """short<->seat maps derive from roster YAML, matching endpoint suffixes."""
    short_to_seat = facade.short_to_seat()
    assert set(short_to_seat) == {
        "chief",
        "scout",
        "risk",
        "whale",
        "sniper",
        "rug",
        "exit",
        "shill",
        "signal",
        "journal",
    }
    assert facade.seat_to_short() == {seat: short for short, seat in short_to_seat.items()}
    for short, seat_id in short_to_seat.items():
        doc = yaml.safe_load((ROSTERS_DIR / f"{seat_id}.yaml").read_text(encoding="utf-8"))
        assert doc["short"] == short
        assert doc["endpoint"] == f"/mcp/{short}"
