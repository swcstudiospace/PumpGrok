"""Regression: tools/list inputSchema must accept what tools/call accepts (Greptile P1).

The advertised schema now comes from each tool's implementation input model
(``ToolSpec.input_json_schema``), the same model ``tools/call`` validates with.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pumpgrok.contracts import projection
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS
from pumpgrok.tools.desk.brief import BRIEF_SPEC, BriefIn
from pumpgrok.tools.exec.place import PlaceIn
from pumpgrok.tools.market.price import PriceIn
from registry_harness import ROSTERS_DIR

MINT = "So11111111111111111111111111111111111111112"
CURVE = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
ULID = "01J5T8Z3K9Q2W4R6X8Y0ABCDEF"
APPROVAL = "apr-01J5T8Z3K9Q2W4R6X8Y0ABCDEF"


def _entries_by_name(seat_id: str) -> dict[str, dict]:
    entries = projection.exposure_entries(seat_id, ROSTERS_DIR)
    return {entry["name"]: entry for entry in entries}


def test_every_advertised_schema_is_the_implementation_schema() -> None:
    specs_by_transport = {
        projection.transport_name(spec.name): spec
        for spec in projection.implementation_specs().values()
    }
    for seat_id in EXPECTED_SEAT_IDS:
        for entry in projection.exposure_entries(seat_id, ROSTERS_DIR):
            spec = specs_by_transport[entry["name"]]
            assert entry["inputSchema"] == spec.input_json_schema(), (seat_id, entry["name"])


def test_market_price_advertises_required_curve_account() -> None:
    schema = _entries_by_name("bot-06-exit")["market_price"]["inputSchema"]
    assert "curve_account" in schema["properties"]
    assert "curve_account" in schema["required"]
    # Dispatch accepts a payload built from the advertised required fields.
    PriceIn.model_validate({"mint": MINT, "curve_account": CURVE})


def test_exec_place_does_not_require_rollback_plan_it_rejects() -> None:
    schema = _entries_by_name("bot-04-sniper")["exec_place"]["inputSchema"]
    assert "rollback_plan" not in schema["properties"]
    assert "rollback_plan" not in schema["required"]
    assert schema["additionalProperties"] is False
    # PlaceIn forbids rollback_plan, so a payload without it must be accepted.
    PlaceIn.model_validate(
        {
            "ticket_id": "SOL-20260101-001",
            "mint": MINT,
            "side": "buy",
            "decision_id": ULID,
            "size_lamports": 1_000_000,
            "max_slippage_bps": 100,
            "approval_id": APPROVAL,
        }
    )


def test_desk_brief_advertises_implementation_schema_with_required_task_id() -> None:
    # The roster's desk.brief schema has no task_id requirement and no
    # correlation_id; BriefIn (what tools/call validates) has both.
    schema = _entries_by_name("bot-00-chief")["desk_brief"]["inputSchema"]
    assert schema == BRIEF_SPEC.input_json_schema()
    assert schema["required"] == ["task_id"]
    assert "correlation_id" in schema["properties"]
    assert schema["additionalProperties"] is False
    # A payload built from the advertised required fields dispatches cleanly.
    BriefIn.model_validate({"task_id": "t-1"})
