"""Shared loader for the seat prompt sources under prompts/.

Used by scripts/assemble-prompts.sh (prompts-assembled/<SEAT>.xml) and by
scripts/generate-templates.py (agents/<seat>.md). Standard library only, plus pyyaml for the
tool rosters. Nothing here writes files.

A seat source is prompts/bot-0N-<seat>.xml:

    <seat-prompt id name title seat writes_to_exchange description>
      <skills><skill load="always">...</skill></skills>
      <tools contract="contracts/tool-rosters/<seat>.yaml"/>
      <body>
        <markdown><![CDATA[ ...markdown... ]]></markdown>
        <core ref="security-constitution"/>        include a shared section here, once
        <markdown><![CDATA[ ...markdown... ]]></markdown>
      </body>
    </seat-prompt>

Shared sections live in prompts/_shared/core-directives.xml. A section is included only when its
audience is one of the seat's audiences: every seat has "trading-seats"; CHIEF also has "chief";
RISK also has "risk".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from defusedxml import ElementTree as ET

# defusedxml does not re-export Element. The loader only reads parsed trees, so Any suffices.
Element = Any

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "prompts"
CORE_PATH = PROMPTS_DIR / "_shared" / "core-directives.xml"
ROSTERS_DIR = REPO_ROOT / "contracts" / "tool-rosters"
CORE_ROSTER = "_core.yaml"
AGENTS_DIR = REPO_ROOT / "agents"
SKILLS_DIR = REPO_ROOT / "skills"
ASSEMBLED_DIR = REPO_ROOT / "prompts-assembled"

AUDIENCES = ("trading-seats", "chief", "risk")
SEAT_RE = re.compile(r"^bot-0[0-9]-[a-z-]+$")
PLACEHOLDER_RE = re.compile(r"\{\{[^{}\n]*\}\}")
CHANNELS = ("Trading Floor", "DM")


class PromptError(Exception):
    """A prompt source, roster or shared section is malformed. The message names the file."""


@dataclass(frozen=True)
class SeatSource:
    path: Path
    seat: str
    name: str
    title: str
    description: str
    channel: str
    writes_to_exchange: bool
    skills: tuple[str, ...]
    tools_contract: str
    parts: tuple[tuple[str, str], ...]  # ("markdown", text) or ("core", section id)

    @property
    def short(self) -> str:
        """Agent file stem and roster short name: CHIEF -> chief."""
        return self.name.lower()

    @property
    def audiences(self) -> frozenset[str]:
        extra = {"chief": "chief", "risk": "risk"}.get(self.short)
        return frozenset({"trading-seats"} | ({extra} if extra else set()))


@dataclass(frozen=True)
class CoreSection:
    audience: str
    text: str


def _attr(el: Element, key: str, path: Path) -> str:
    value = el.get(key)
    if value is None or not value.strip():
        raise PromptError(f"{path.name}: <{el.tag}> is missing attribute '{key}'")
    return value


def load_core(path: Path = CORE_PATH) -> dict[str, CoreSection]:
    if not path.exists():
        raise PromptError(f"{path}: shared directives not found")
    # Repo-owned prompt sources reviewed under G-1/G-3, not untrusted input.
    root = ET.parse(path).getroot()
    if root.tag != "core-directives":
        raise PromptError(f"{path.name}: root must be <core-directives>")
    sections: dict[str, CoreSection] = {}
    for el in root.findall("section"):
        sid = _attr(el, "id", path)
        audience = _attr(el, "audience", path)
        if audience not in AUDIENCES:
            raise PromptError(
                f"{path.name}: section '{sid}' audience '{audience}' not in {AUDIENCES}"
            )
        if sid in sections:
            raise PromptError(f"{path.name}: section '{sid}' is declared twice")
        sections[sid] = CoreSection(audience=audience, text=el.text or "")
    return sections


def _seat_id(root: Element, path: Path) -> str:
    seat = _attr(root, "id", path)
    if not SEAT_RE.match(seat):
        raise PromptError(f"{path.name}: id {seat!r} does not match {SEAT_RE.pattern}")
    if path.stem != seat:
        raise PromptError(f"{path.name}: id {seat!r} must equal the file name")
    return seat


def _writes_to_exchange(root: Element, path: Path) -> bool:
    writes = _attr(root, "writes_to_exchange", path)
    if writes not in ("true", "false"):
        raise PromptError(f"{path.name}: writes_to_exchange must be 'true' or 'false'")
    return writes == "true"


def _channel(root: Element, path: Path) -> str:
    channel = _attr(root, "seat", path)
    if channel not in CHANNELS:
        raise PromptError(f"{path.name}: seat {channel!r} must be one of {CHANNELS}")
    return channel


def _skills(root: Element, path: Path) -> tuple[str, ...]:
    skills: list[str] = []
    for el in root.findall("skills/skill"):
        if not el.text:
            continue
        load = el.get("load", "always")
        if load != "always":
            raise PromptError(
                f"{path.name}: skill {el.text.strip()!r} load {load!r} must be 'always'"
            )
        skills.append(el.text.strip())
    if not skills:
        raise PromptError(f"{path.name}: <skills> lists no skill")
    return tuple(skills)


def _tools_contract(root: Element, seat: str, path: Path) -> str:
    tools_el = root.find("tools")
    if tools_el is None:
        raise PromptError(f"{path.name}: missing <tools contract=.../>")
    contract = (tools_el.get("contract") or "").strip()
    if not contract:
        raise PromptError(f"{path.name}: <tools> is missing attribute 'contract'")
    expected = f"contracts/tool-rosters/{seat}.yaml"
    if contract != expected:
        raise PromptError(f"{path.name}: <tools> contract {contract!r} must be {expected!r}")
    if not (REPO_ROOT / contract).exists():
        raise PromptError(f"{path.name}: <tools> contract {contract} not found")
    return contract


def _body_parts(root: Element, path: Path) -> tuple[tuple[str, str], ...]:
    parts: list[tuple[str, str]] = []
    body = root.find("body")
    if body is None:
        raise PromptError(f"{path.name}: missing <body>")
    for el in body:
        if el.tag == "markdown":
            parts.append(("markdown", el.text or ""))
        elif el.tag == "core":
            parts.append(("core", _attr(el, "ref", path)))
        else:
            raise PromptError(f"{path.name}: unknown element <{el.tag}> in <body>")
    if not parts:
        raise PromptError(f"{path.name}: <body> is empty")
    return tuple(parts)


def load_seat(path: Path) -> SeatSource:
    root = ET.parse(path).getroot()
    if root.tag != "seat-prompt":
        raise PromptError(f"{path.name}: root must be <seat-prompt>")
    seat = _seat_id(root, path)
    writes = _writes_to_exchange(root, path)
    channel = _channel(root, path)
    skills = _skills(root, path)
    tools_contract = _tools_contract(root, seat, path)
    parts = _body_parts(root, path)
    return SeatSource(
        path=path,
        seat=seat,
        name=_attr(root, "name", path),
        title=_attr(root, "title", path),
        description=_attr(root, "description", path),
        channel=channel,
        writes_to_exchange=writes,
        skills=skills,
        tools_contract=tools_contract,
        parts=parts,
    )


def load_seats(prompts_dir: Path = PROMPTS_DIR) -> list[SeatSource]:
    paths = sorted(prompts_dir.glob("bot-0*.xml"))
    if not paths:
        raise PromptError(f"{prompts_dir}: no seat prompt sources (bot-0N-<seat>.xml)")
    return [load_seat(p) for p in paths]


def expand(seat: SeatSource, core: dict[str, CoreSection]) -> str:
    """The seat's markdown body with every <core> include replaced in place."""
    out: list[str] = []
    for kind, value in seat.parts:
        if kind == "markdown":
            out.append(value)
            continue
        section = core.get(value)
        if section is None:
            raise PromptError(f"{seat.path.name}: <core ref='{value}'/> names no shared section")
        if section.audience not in seat.audiences:
            raise PromptError(
                f"{seat.path.name}: shared section '{value}' has audience "
                f"'{section.audience}', which {seat.short} does not have"
            )
        out.append(section.text)
    return "".join(out)


def _scalar(key: str, value: object) -> str:
    """One `key: value` line. Plain when YAML reads it back unchanged, quoted otherwise."""
    line = yaml.safe_dump({key: value}, allow_unicode=True, width=10**9, sort_keys=False)
    return line.rstrip("\n")


def frontmatter(seat: SeatSource) -> str:
    """Agent frontmatter, in the key order the agents have always used."""
    lines = [
        _scalar("name", seat.name),
        _scalar("title", seat.title),
        _scalar("description", seat.description),
        _scalar("seat", seat.channel),
        "skills:",
        *[f"  - {s}" for s in seat.skills],
        _scalar("writes_to_exchange", seat.writes_to_exchange),
    ]
    return "\n".join(lines) + "\n"


def load_roster(seat: SeatSource) -> dict:
    """The seat's roster file, checked against its prompt source. Raises on mismatch."""
    path = ROSTERS_DIR / f"{seat.seat}.yaml"
    if not path.exists():
        raise PromptError(f"{seat.seat}: roster {path.relative_to(REPO_ROOT)} not found")
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if doc.get("seat") != seat.seat:
        raise PromptError(f"{path.name}: seat {doc.get('seat')!r} != {seat.seat!r}")
    if doc.get("short") != seat.short:
        raise PromptError(f"{path.name}: short {doc.get('short')!r} != {seat.short!r}")
    if doc.get("endpoint") != f"/mcp/{seat.short}":
        raise PromptError(f"{path.name}: endpoint must be /mcp/{seat.short}")
    if doc.get("core") is not True:
        raise PromptError(f"{path.name}: core must be true")
    return doc


def effective_tools(seat: SeatSource) -> list[dict]:
    """core eight plus the seat's own tools, in roster order (the list the gateway serves)."""
    core_doc = yaml.safe_load((ROSTERS_DIR / CORE_ROSTER).read_text(encoding="utf-8"))
    own = load_roster(seat)["tools"]
    return [*core_doc["tools"], *own]


def check_skills(seat: SeatSource) -> list[str]:
    """Skill names that have no directory under skills/. Empty when every skill exists."""
    if not SKILLS_DIR.is_dir():
        return []
    return [s for s in seat.skills if not (SKILLS_DIR / s / "SKILL.md").exists()]
