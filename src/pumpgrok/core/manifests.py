"""Seat manifest loading: roster YAML files become BotManifests (B6a, SKILL-003).

Each ``bot-*.yaml`` roster carries an additive ``manifest:`` block with the
ROSTER section 5 fields. ``allowed_tools`` is never written in the block:
the loader derives it from the roster's own ``tools:`` list plus the
desk.* core eight in ``_core.yaml`` (``ToolGrant`` name plus side_effect),
so tool names stay in exactly one place. The loader fails closed: a missing
manifest block, an unknown seat file, or anything other than exactly the ten
expected seats raises instead of skipping.

``effective_roster`` and ``transport_map`` are the gateway projection
helpers (TOOL-010): the effective tool list for one seat and the
transport-name map built from the roster entries (never by reversing a
string replace, since names contain underscores).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pumpgrok.core.bot import BotManifest, ToolGrant

EXPECTED_SEAT_IDS: tuple[str, ...] = (
    "bot-00-chief",
    "bot-01-scout",
    "bot-02-risk",
    "bot-03-whale",
    "bot-04-sniper",
    "bot-05-rug",
    "bot-06-exit",
    "bot-07-shill",
    "bot-08-signal",
    "bot-09-journal",
)

_CORE_FILE = "_core.yaml"


def _read_doc(path: Path) -> dict:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{path.name}: roster is not valid YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError(f"{path.name}: roster must be a YAML mapping")
    return doc


def _tool_entries(doc: dict, path: Path) -> list[dict]:
    tools = doc.get("tools")
    if not isinstance(tools, list) or not tools:
        raise ValueError(f"{path.name}: roster must list a non-empty 'tools'")
    for entry in tools:
        if not isinstance(entry, dict) or not entry.get("name"):
            raise ValueError(f"{path.name}: every tool entry needs a name")
    return tools


def _grants(entries: list[dict], path: Path) -> list[ToolGrant]:
    grants = []
    for entry in entries:
        try:
            grants.append(
                ToolGrant(name=entry["name"], side_effect=entry["side_effect"])
            )
        except Exception as exc:
            raise ValueError(
                f"{path.name}: tool {entry.get('name')!r} needs a valid side_effect: {exc}"
            ) from exc
    return grants


def load_bot_manifests(contracts_dir: Path) -> dict[str, BotManifest]:
    """Load exactly the ten seat manifests, merging _core into allowed_tools."""
    contracts_dir = Path(contracts_dir)
    core_doc = _read_doc(contracts_dir / _CORE_FILE)
    core_entries = _tool_entries(core_doc, contracts_dir / _CORE_FILE)

    manifests: dict[str, BotManifest] = {}
    for path in sorted(contracts_dir.glob("bot-*.yaml")):
        doc = _read_doc(path)
        seat = doc.get("seat")
        block = doc.get("manifest")
        if not isinstance(block, dict):
            raise ValueError(f"{path.name}: roster needs an additive 'manifest' block (B6a)")
        if seat != block.get("id"):
            raise ValueError(
                f"{path.name}: roster seat {seat!r} != manifest id {block.get('id')!r}"
            )
        own_entries = _tool_entries(doc, path)
        grants = _grants(own_entries, path) + _grants(core_entries, path)
        try:
            manifests[seat] = BotManifest.model_validate({**block, "allowed_tools": grants})
        except Exception as exc:
            raise ValueError(f"{path.name}: manifest does not validate: {exc}") from exc

    missing = [sid for sid in EXPECTED_SEAT_IDS if sid not in manifests]
    if missing:
        raise ValueError(f"seat manifests missing (no silent skip): {missing}")
    extra = [sid for sid in manifests if sid not in EXPECTED_SEAT_IDS]
    if extra:
        raise ValueError(f"unknown seat manifests (no silent skip): {extra}")
    return {sid: manifests[sid] for sid in EXPECTED_SEAT_IDS}


def effective_roster(contracts_dir: Path, seat_id: str) -> list[dict]:
    """Raw tool entries for one seat: its own tools plus the core eight."""
    contracts_dir = Path(contracts_dir)
    doc = _read_doc(contracts_dir / f"{seat_id}.yaml")
    core_doc = _read_doc(contracts_dir / _CORE_FILE)
    own = _tool_entries(doc, contracts_dir / f"{seat_id}.yaml")
    core = _tool_entries(core_doc, contracts_dir / _CORE_FILE)
    if doc.get("core") is True:
        return [dict(entry) for entry in own + core]
    return [dict(entry) for entry in own]


def transport_name(dotted: str) -> str:
    """Exposure-time transport name: dots become underscores (R19)."""
    return dotted.replace(".", "_")


def transport_map(contracts_dir: Path, seat_id: str) -> dict[str, str]:
    """Map transport names back to dotted ids from the roster entries.

    Built forward from the seat roster, never by reversing a string replace:
    names contain underscores (``onchain.token_metadata``), so the reverse
    mapping is ambiguous.
    """
    mapping: dict[str, str] = {}
    for entry in effective_roster(contracts_dir, seat_id):
        mapping[transport_name(entry["name"])] = entry["name"]
    return mapping
