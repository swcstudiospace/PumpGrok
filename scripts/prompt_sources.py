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
from xml.sax.saxutils import escape, quoteattr

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


DESK_CYCLE_PATH = REPO_ROOT / "scripts" / "desk_cycle.xml"
CYCLE_TAGS = (
    "strategy_details",
    "backtesting_params",
    "paper_testing_config",
    "autonomous_execution_steps",
    "rpc_calls",
    "optimization_instructions",
    "grok_bot_integration",
)
CYCLE_STATES = (
    "DISCOVERY",
    "ANALYSIS",
    "STRATEGY_DEVELOPMENT",
    "BACKTESTING",
    "PAPER_TESTING",
    "OPTIMIZATION",
    "FAILURE_RECOVERY",
    "LIVE_TRADING",
)
_CYCLE_FORBIDDEN = re.compile(
    r"https?://|sendTransaction|send_transaction|signTransaction|sign_transaction|\{\{"
)


def load_desk_cycle(path: Path = DESK_CYCLE_PATH) -> Element:
    """The shared paper-cycle contract. Raises PromptError when it would enable a send."""
    if not path.exists():
        raise PromptError(f"{path}: desk cycle not found")
    raw = path.read_text(encoding="utf-8")
    forbidden = _CYCLE_FORBIDDEN.search(raw)
    if forbidden:
        raise PromptError(f"{path.name}: forbidden token {forbidden.group(0)!r}")
    root = ET.parse(path).getroot()
    if root.tag != "desk-cycle":
        raise PromptError(f"{path.name}: root must be <desk-cycle>")
    seen = [child.tag for child in root]
    if seen != list(CYCLE_TAGS):
        raise PromptError(f"{path.name}: children must be {CYCLE_TAGS} in order, got {seen}")
    steps = root.find("autonomous_execution_steps")
    state_ids = [el.get("id") for el in steps.findall("state")]
    if state_ids != list(CYCLE_STATES):
        raise PromptError(f"{path.name}: state ids must be {CYCLE_STATES}, got {state_ids}")
    live = steps.find("state[@id='LIVE_TRADING']")
    live_text = "".join(live.itertext())
    if "gate_denied" not in live_text or "No signer" not in live_text:
        raise PromptError(f"{path.name}: LIVE_TRADING must stay gate_denied with no signer")
    paper = "".join(root.find("paper_testing_config").itertext())
    if "PaperAdapter" not in paper:
        raise PromptError(f"{path.name}: paper_testing_config must name PaperAdapter")
    grok = "".join(root.find("grok_bot_integration").itertext())
    if "must not be called" not in grok:
        raise PromptError(f"{path.name}: grok_bot_integration must refuse unregistered modules")
    return root


def _emit_cycle(el: Element, indent: str) -> list[str]:
    attrs = "".join(f" {key}={quoteattr(value)}" for key, value in el.attrib.items())
    children = list(el)
    text = (el.text or "").strip()
    if not children:
        body = escape(text)
        return [f"{indent}<{el.tag}{attrs}>{body}</{el.tag}>"]
    lines = [f"{indent}<{el.tag}{attrs}>"]
    if text:
        lines.append(f"{indent}  {escape(text)}")
    for child in children:
        lines.extend(_emit_cycle(child, indent + "  "))
    lines.append(f"{indent}</{el.tag}>")
    return lines


def desk_cycle_xml(path: Path = DESK_CYCLE_PATH) -> str:
    """Indented desk-cycle element for an assembled prompt. No CDATA."""
    text = "\n".join(_emit_cycle(load_desk_cycle(path), "  "))
    if "]]>" in text:
        raise PromptError(f"{path.name}: cycle contains ']]>'")
    return text


def desk_cycle_markdown(path: Path = DESK_CYCLE_PATH) -> str:
    """Readable copy of the cycle, appended after the seat body. Does not replace it."""
    root = load_desk_cycle(path)
    lines = [
        "",
        "## Desk cycle",
        "",
        "Shared paper-cycle contract. Live send is refused. No seat may sign or broadcast.",
        "",
    ]
    for child in root:
        lines.append(f"### {child.tag}")
        lines.append("")
        text = (child.text or "").strip()
        if text:
            lines.append(text)
            lines.append("")
        for sub in child:
            label = sub.get("id") or sub.tag
            lines.append(f"#### {label}")
            lines.append("")
            sub_text = (sub.text or "").strip()
            if sub_text:
                lines.append(sub_text)
                lines.append("")
    rendered = "\n".join(lines)
    if not rendered.endswith("\n"):
        rendered += "\n"
    if "]]>" in rendered:
        raise PromptError(f"{path.name}: cycle markdown contains ']]>'")
    return rendered
