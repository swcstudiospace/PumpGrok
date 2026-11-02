"""Characterization: the PRE-v4 Settings surface, pinned section by section (QLT-05, CONTEXT D-11).

Each Settings section is pinned by its own digest: sha256 over its name, its pydantic JSON
schema (types, constraints, descriptions) and its default values. The digest does not depend
on the module the section lives in, so the 11-04 move into config/sections keeps it. A later
unit that edits a PRE-v4 section changes a digest here and fails loudly. A new v4 section is
added as a new field and does not touch these pins.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from pydantic import TypeAdapter

from pumpgrok.config.settings import Settings

PRE_V4_FIELDS: tuple[str, ...] = (
    "mode",
    "execution",
    "risk",
    "limits",
    "replay",
    "live",
    "platform",
    "wallet",
    "data",
    "rpc",
    "grok",
    "jupiter",
    "filter",
    "safety",
    "scoring",
    "exits",
    "ops",
    "notify",
    "health",
)

PINNED_SECTION_DIGESTS: dict[str, str] = {
    "execution": "717144ed733a9c81a960bc445d94f19a79e7677cdc6b0070847d659e51f5fb2c",
    "risk": "7b73f8ebece3612a00b973f1f402c9174c6b43bcaa4cb367bf6acf0eb3ee723e",
    "limits": "005a5d70a24265958cef1441c5aa0d0ced919986defa941091361598e51c5557",
    "replay": "4e949265d09c7f086f0568a752a46ffc91eafba9541f0cdf453eb53db5d230ba",
    "live": "d06968acdda3fe67966ab7d79cfac8cf03cb7c60bf803972a661296ff021bfe2",
    "platform": "ffec8c9d9df99d776e4188e75abbae89acd4fe967e45e5a7d4b7b3fc6213cc22",
    "wallet": "a3f771e706717d5b4865571cee9eee8478711d68d76ad3f3a2a659325fe8536b",
    "data": "cea8148bc8779c7347e700c0beca94434562c9811ce3b2521279f98d68e9e44f",
    "rpc": "d0e8d2cd69a3d9c5bbcd3de13cd295599d2cc4311f01f0e9248133812c21d29d",
    "grok": "2e4c9dc6ad91eb80b07531dd3ad66ca5386430bc3c56ee3cba0407903747b00b",
    "jupiter": "e31754b27eae6e4697ea81a6dc9cf0f9570cd034b5c52c78b7a8eaaf675a043b",
    "filter": "72883161750cfff0c4689337fd3b1814ddee7e64ccf3844b49dde34b7520ef66",
    "safety": "7f5fe1b95a23f9c84038b31fb66d18b2bf71b81e9139b82b01f7bf03e9e6728e",
    "scoring": "402e94eb3d94528d8823e3682ad940df7f9abc18800edd8da3ac86d5856cde08",
    "exits": "71ec150216dbc1ff0105b35e104b7dae4a64ce3845bb06c88f5c3599e22bfff9",
    "ops": "bb1a378d59815ba72e2fc99571cb1e87732b7bee7e14af1e0373344a78679f7a",
    "notify": "c5b4befdfaeb1a71533fbc2011c77862f2774263ac60a16b074a53078c32dc7a",
    "health": "c88a6d6abdcf0ee28c1ae470e1fcec57c4579ab2ea866fce7f9d1f6a02f4cf95",
}


def section_digest(name: str) -> str:
    """sha256 over the section name, its JSON schema and its default values."""
    field = Settings.model_fields[name]
    annotation: Any = field.annotation
    schema = TypeAdapter(annotation).json_schema(mode="validation")
    default = field.get_default(call_default_factory=True)
    defaults = TypeAdapter(annotation).dump_python(default, mode="json")
    text = json.dumps(
        {"name": name, "schema": schema, "defaults": defaults},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _all_digests() -> dict[str, str]:
    return {name: section_digest(name) for name in PINNED_SECTION_DIGESTS}


def test_top_level_fields_are_pinned_in_order() -> None:
    assert tuple(Settings.model_fields) == PRE_V4_FIELDS


def test_every_pre_v4_section_matches_its_pinned_digest() -> None:
    assert _all_digests() == PINNED_SECTION_DIGESTS


def test_pinned_sections_are_every_field_except_mode() -> None:
    assert tuple(name for name in PRE_V4_FIELDS if name != "mode") == tuple(PINNED_SECTION_DIGESTS)


def test_digests_do_not_move_under_a_mode_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_MODE", "live")
    assert _all_digests() == PINNED_SECTION_DIGESTS


def test_mode_defaults_to_unset_and_execution_defaults_to_paper() -> None:
    assert Settings.model_fields["mode"].default is None
    execution = Settings.model_fields["execution"].get_default(call_default_factory=True)
    assert execution.mode == "paper"
