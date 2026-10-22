"""Gateway projection: roster YAML projected to MCP exposure (TOOL-010, B4).

Single source of truth shared by the desk-gateway service and the root
``-k gateway`` suite. Pure projection, no tool logic: entry
name/description/input come verbatim from the roster files, transport
names are derived at exposure time only (dots to underscores, R19), and
the transport-to-dotted map is built forward from the roster entries,
never by reversing a string replace (``desk.memory_retain`` would be
ambiguous in reverse).
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

import yaml

import pumpgrok.tools as tools_pkg
from pumpgrok.core.manifests import (
    effective_roster as _effective_roster,
)
from pumpgrok.core.manifests import (
    transport_map as _transport_map,
)
from pumpgrok.core.manifests import (
    transport_name,
)
from pumpgrok.core.tool import ToolSpec

__all__ = [
    "default_contracts_dir",
    "effective_roster",
    "exposure_entries",
    "seat_to_short",
    "short_to_seat",
    "transport_map",
    "transport_name",
]


def default_contracts_dir() -> Path:
    """Repo ``contracts/tool-rosters`` dir (service derives it, never hardcodes)."""
    return Path(__file__).resolve().parents[3] / "contracts" / "tool-rosters"


def effective_roster(seat_id: str, contracts_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """Raw tool entries for one seat: its own tools plus the core eight."""
    base = Path(contracts_dir) if contracts_dir is not None else default_contracts_dir()
    return _effective_roster(base, seat_id)


def transport_map(seat_id: str, contracts_dir: Path | str | None = None) -> dict[str, str]:
    """Map transport names back to dotted ids, built forward from the roster."""
    base = Path(contracts_dir) if contracts_dir is not None else default_contracts_dir()
    return _transport_map(base, seat_id)


def short_to_seat(contracts_dir: Path | str | None = None) -> dict[str, str]:
    """Map roster ``short`` (chief, scout, ...) to seat id (bot-00-chief, ...)."""
    base = Path(contracts_dir) if contracts_dir is not None else default_contracts_dir()
    mapping: dict[str, str] = {}
    for path in sorted(base.glob("bot-*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and doc.get("seat") and doc.get("short"):
            mapping[str(doc["short"])] = str(doc["seat"])
    return mapping


def seat_to_short(contracts_dir: Path | str | None = None) -> dict[str, str]:
    """Inverse of :func:`short_to_seat`."""
    return {seat: short for short, seat in short_to_seat(contracts_dir).items()}


def implementation_specs() -> dict[str, ToolSpec]:
    """Every catalog ``ToolSpec`` keyed by dotted name, read from the tool modules.

    The implementation models are what ``tools/call`` validates against, so
    they are the single source for the advertised input schema (the roster
    YAML is a second, drifting copy and is not used for ``inputSchema``).
    """
    specs: dict[str, ToolSpec] = {}
    for module_info in pkgutil.walk_packages(tools_pkg.__path__, prefix="pumpgrok.tools."):
        module = importlib.import_module(module_info.name)
        for value in vars(module).values():
            if isinstance(value, ToolSpec):
                if value.name in specs and specs[value.name] is not value:
                    raise ValueError(f"duplicate ToolSpec name: {value.name}")
                specs[value.name] = value
    return specs


def exposure_entries(seat_id: str, contracts_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """MCP ``tools/list`` entries: roster name and description, implementation input schema."""
    specs = implementation_specs()
    entries: list[dict[str, Any]] = []
    for entry in effective_roster(seat_id, contracts_dir):
        spec = specs.get(entry["name"])
        if spec is None:
            raise KeyError(f"roster tool without implementation: {entry['name']}")
        entries.append(
            {
                "name": transport_name(entry["name"]),
                "description": entry["description"],
                "inputSchema": spec.input_json_schema(),
            }
        )
    return entries
