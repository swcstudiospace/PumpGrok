#!/usr/bin/env python3
"""Gate G-7 — desk integrity.

The desk is only as trustworthy as the files that describe it. A roster with a tool that has no
input schema is a tool the gateway cannot validate; a g5 tool whose schema does not require a
rollback plan is a deployment the rollback gate never sees; a prompt source with a hardcoded
channel id is a desk that cannot be installed for a second team; a template with a token shape
or a tailnet name is a secret published to every recipient.

Each check reads the repo as it is. There is no diff and no receipt: a bad roster is bad on every
commit, not only on the one that introduced it.

    python3 ci/gates/check_desk_integrity.py
    python3 ci/gates/check_desk_integrity.py --repo /path/to/checkout
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("check_desk_integrity: pyyaml is required (pip install pyyaml)")

REPO_ROOT = Path(__file__).resolve().parents[2]

ROSTERS_DIR = "contracts/tool-rosters"
PACKS_DIR = "contracts/tool-packs"
PROMPTS_DIR = "prompts"
ASSEMBLED_DIR = "prompts-assembled"
TEMPLATES_DIR = "grokbot/templates"

CORE_ROSTER = "_core.yaml"

# A seat sees the core eight plus its own tools, so eight is the floor (R19: the core alone is a
# valid DM roster). More than fifteen is past what a bot can hold in one tools/list (R19).
ROSTER_MIN_TOOLS = 8
ROSTER_MAX_TOOLS = 15
PACK_MIN_TOOLS = 1
PACK_MAX_TOOLS = 5

# Dotted <namespace>.<verb> names only (R19). The gateway's ns_verb transport name is derived at
# exposure time and is never stored in a roster, catalog or ownership file.
TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
# No seat may resolve a live-write tool (D3). Matched by name prefix.
LIVE_TOOL_PREFIX = "exec.live"
SEAT_RE = re.compile(r"^bot-0[0-9]-[a-z-]+$")
APP_RE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
PLACEHOLDER_RE = re.compile(r"\{\{[^{}\r\n]+\}\}")

KINDS = {"read", "write"}
GATES = {"g5", "g6"}
# What each gate tag demands of the tool's input schema. Approval gating (G-6) applies
# only where declared: a tool whose roster entry lists gates: [g6] must demand
# approval_id and rollback_plan in input.required (R57; docs/TOOL_CATALOG.md
# section 10: exec.place and exec.cancel). A paper-write tool with no g6 declaration
# needs no approval fields. Live-write tools never appear in a roster at all —
# check_roster refuses them outright (invariant I1).
GATE_REQUIRED_FIELDS: dict[str, list[str]] = {
    "g5": ["rollback_plan", "approval_id"],
    "g6": ["approval_id", "rollback_plan"],
}

# Assembled prompts are also written to these aliases under prompts/. They are output, not
# source, so the placeholder check applies to them rather than the UUID check.
ASSEMBLED_ALIASES = [
    "CHIEF",
    "SCOUT",
    "RISK",
    "WHALE",
    "SNIPER",
    "RUG",
    "EXIT",
    "SHILL",
    "SIGNAL",
    "JOURNAL",
]

# Nothing in a Grok Bot template may point at the desk's own infrastructure or credentials.
# (pattern, description)
TEMPLATE_FORBIDDEN: list[tuple[str, str]] = [
    (r"sk-[A-Za-z0-9]{16,}", "API key shape (sk-...)"),
    (r"ghp_[A-Za-z0-9]{20,}", "GitHub token shape (ghp_...)"),
    (r"xox[abp]-", "Slack token shape (xox?-...)"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key shape (AKIA...)"),
    (r"-----BEGIN", "key block (-----BEGIN)"),
    (r"tailscale-forwarder", "tailnet name (tailscale-forwarder)"),
    (r"\.ts\.net", "tailnet domain (.ts.net)"),
    (r"100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.", "tailnet address (100.64/10)"),
    (UUID_RE.pattern, "literal UUID"),
    (r"railway\.internal", "Railway private hostname (railway.internal)"),
    (r"[1-9A-HJ-NP-Za-km-z]{86,88}", "Solana 64-byte secret key shape (base58)"),
    (r"helius(?:-rpc)?\.com/[^\s\"']*api-key=", "Helius keyed RPC URL"),
    (r"solana-mainnet\.quiknode\.pro/[A-Za-z0-9]{20,}", "QuickNode keyed endpoint"),
    (r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b", "Telegram bot token shape"),
    (r"\bxai-[A-Za-z0-9]{32,}\b", "x.ai API key shape"),
    (
        r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b(?=.*(?:mint|wallet))",
        "literal Solana address beside mint or wallet",
    ),
]


def _rel(path: Path, repo: Path) -> str:
    try:
        return str(path.relative_to(repo))
    except ValueError:
        return str(path)


def load_yaml(path: Path) -> tuple[dict | None, str | None]:
    """Return (document, error). A roster that does not parse is a roster with no tools."""
    try:
        with path.open() as fh:
            doc = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        return None, f"not valid YAML: {exc}"
    if not isinstance(doc, dict):
        return None, "top level is not a mapping"
    return doc, None


# ---------------------------------------------------------------------------
# per-tool rules, shared by rosters and packs
# ---------------------------------------------------------------------------


def _gate_field_problems(label: str, gates: list, required: list) -> list[str]:
    """Every declared gate tag must be backed by the fields its enforcement needs."""
    problems = []
    for gate in gates:
        for field in GATE_REQUIRED_FIELDS[gate]:
            if field not in required:
                problems.append(
                    f"{label} is tagged {gate} but input.required lacks '{field}' — "
                    "the gate cannot enforce a field the schema does not demand"
                )
    return problems


def check_tool(tool: object, index: int) -> list[str]:
    """Rules every tool obeys wherever it is declared."""
    if not isinstance(tool, dict):
        return [f"tools[{index}] is not a mapping"]

    name = tool.get("name")
    label = f"tool '{name}'" if isinstance(name, str) and name else f"tools[{index}]"
    problems: list[str] = []

    if not isinstance(name, str) or not TOOL_NAME_RE.match(name):
        problems.append(f"{label} name {name!r} does not match {TOOL_NAME_RE.pattern}")

    if tool.get("kind") not in KINDS:
        problems.append(f"{label} kind {tool.get('kind')!r} is not one of {sorted(KINDS)}")

    gates = tool.get("gates")
    if not isinstance(gates, list) or not set(gates) <= GATES:
        problems.append(f"{label} gates {gates!r} must be a list drawn from {sorted(GATES)}")
        gates = [g for g in (gates if isinstance(gates, list) else []) if g in GATES]

    description = tool.get("description")
    if not isinstance(description, str) or not description.strip():
        problems.append(f"{label} has no description")

    schema = tool.get("input")
    if not isinstance(schema, dict):
        problems.append(f"{label} has no input schema — the gateway cannot validate its calls")
        return problems
    if schema.get("type") != "object":
        problems.append(f"{label} input schema type is {schema.get('type')!r}, not 'object'")
    if schema.get("additionalProperties") is not False:
        problems.append(f"{label} input schema must set additionalProperties: false")

    required = schema.get("required") or []
    if not isinstance(required, list):
        problems.append(f"{label} input.required must be a list")
        required = []
    properties = schema.get("properties")
    declared = properties if isinstance(properties, dict) else {}
    for field in required:
        if not isinstance(field, str) or field not in declared:
            problems.append(
                f"{label} requires {field!r} but input.properties does not declare it — "
                "additionalProperties: false would reject every call"
            )
    problems.extend(_gate_field_problems(label, gates, required))
    return problems


def _tools_of(doc: dict, what: str) -> tuple[list, list[str]]:
    tools = doc.get("tools")
    if not isinstance(tools, list):
        return [], [f"{what} has no 'tools' list"]
    return tools, []


def _names(tools: list) -> list[str]:
    return [t.get("name") for t in tools if isinstance(t, dict) and isinstance(t.get("name"), str)]


# ---------------------------------------------------------------------------
# rosters
# ---------------------------------------------------------------------------


def load_core_tools(rosters_dir: Path) -> tuple[list, list[str]]:
    core_path = rosters_dir / CORE_ROSTER
    if not core_path.exists():
        return [], [f"{CORE_ROSTER} not found in {rosters_dir}"]
    doc, err = load_yaml(core_path)
    if err:
        return [], [f"{CORE_ROSTER}: {err}"]
    tools, problems = _tools_of(doc, CORE_ROSTER)
    for i, tool in enumerate(tools):
        problems.extend(f"{CORE_ROSTER}: {p}" for p in check_tool(tool, i))
    return tools, problems


def check_roster(path: Path, core_tools: list) -> list[str]:
    doc, err = load_yaml(path)
    if err:
        return [err]
    problems: list[str] = []

    seat = doc.get("seat")
    if not isinstance(seat, str) or not SEAT_RE.match(seat):
        problems.append(f"seat {seat!r} does not match {SEAT_RE.pattern}")

    short = doc.get("short")
    endpoint = doc.get("endpoint")
    if not isinstance(short, str) or not short:
        problems.append("'short' is missing")
    elif endpoint != f"/mcp/{short}":
        problems.append(f"endpoint {endpoint!r} must be '/mcp/{short}'")

    own_tools, tool_problems = _tools_of(doc, "roster")
    problems.extend(tool_problems)
    for i, tool in enumerate(own_tools):
        problems.extend(check_tool(tool, i))

    has_core = doc.get("core") is True
    effective = list(own_tools) + (list(core_tools) if has_core else [])
    n = len(effective)
    if not ROSTER_MIN_TOOLS <= n <= ROSTER_MAX_TOOLS:
        breakdown = (
            f"{len(own_tools)} own + {len(core_tools)} core"
            if has_core
            else f"{len(own_tools)} own, core: false"
        )
        problems.append(
            f"{n} effective tool(s) ({breakdown}) — "
            f"must be within [{ROSTER_MIN_TOOLS}, {ROSTER_MAX_TOOLS}]"
        )

    seen: set[str] = set()
    for name in _names(effective):
        if name in seen:
            problems.append(f"tool name '{name}' is declared twice in the effective roster")
        seen.add(name)
    for name in _names(effective):
        if name.startswith(LIVE_TOOL_PREFIX):
            problems.append(f"tool '{name}' is a live-write tool; no seat may resolve it (D3)")

    return problems


# ---------------------------------------------------------------------------
# packs
# ---------------------------------------------------------------------------


def check_pack(path: Path) -> list[str]:
    doc, err = load_yaml(path)
    if err:
        return [err]
    problems: list[str] = []

    app = doc.get("app")
    if not isinstance(app, str) or not APP_RE.match(app):
        problems.append(f"app {app!r} does not match {APP_RE.pattern}")
        app = None

    tools, tool_problems = _tools_of(doc, "pack")
    problems.extend(tool_problems)
    for i, tool in enumerate(tools):
        problems.extend(check_tool(tool, i))

    n = len(tools)
    if not PACK_MIN_TOOLS <= n <= PACK_MAX_TOOLS:
        problems.append(f"{n} tool(s) — a pack holds {PACK_MIN_TOOLS} to {PACK_MAX_TOOLS}")

    if app:
        prefix = app.replace("-", "_") + "_"
        for name in _names(tools):
            if not name.startswith(prefix):
                problems.append(f"tool '{name}' is not prefixed '{prefix}'")

    seen: set[str] = set()
    for name in _names(tools):
        if name in seen:
            problems.append(f"tool name '{name}' is declared twice")
        seen.add(name)

    return problems


# ---------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------


def _lines_matching(text: str, pattern: re.Pattern) -> list[int]:
    return [i for i, line in enumerate(text.splitlines(), start=1) if pattern.search(line)]


def check_prompt_source(path: Path) -> list[str]:
    """A source may only refer to a channel or seat through a placeholder."""
    text = path.read_text(errors="replace")
    lines = _lines_matching(text, UUID_RE)
    if not lines:
        return []
    where = ", ".join(str(n) for n in lines[:5]) + (", ..." if len(lines) > 5 else "")
    return [
        f"literal UUID at line(s) {where} — use {{{{DESK_CHANNEL_ID}}}} / {{{{SEAT_UUID:...}}}}"
    ]


def check_assembled_prompt(path: Path) -> list[str]:
    """Assembled output is what gets installed: every placeholder must have been filled."""
    text = path.read_text(errors="replace")
    if not text.strip():
        return ["assembled prompt is empty"]
    problems: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in PLACEHOLDER_RE.findall(line):
            problems.append(f"unfilled placeholder {match} at line {line_no}")
    return problems


def prompt_files(prompts_dir: Path, assembled_dir: Path) -> tuple[list[Path], list[Path]]:
    """Split prompt XML into (sources, assembled). The aliases under prompts/ are assembled."""
    alias_names = {f"{name}.xml" for name in ASSEMBLED_ALIASES}
    sources: list[Path] = []
    assembled: list[Path] = []
    if prompts_dir.is_dir():
        for path in sorted(prompts_dir.rglob("*.xml")):
            if path.parent == prompts_dir and path.name in alias_names:
                assembled.append(path)
            else:
                sources.append(path)
    if assembled_dir.is_dir():
        assembled.extend(sorted(assembled_dir.glob("*.xml")))
    return sources, assembled


# ---------------------------------------------------------------------------
# templates
# ---------------------------------------------------------------------------


def check_template(path: Path) -> list[str]:
    text = path.read_text(errors="replace")
    problems: list[str] = []
    for pattern, why in TEMPLATE_FORBIDDEN:
        lines = _lines_matching(text, re.compile(pattern))
        if lines:
            where = ", ".join(str(n) for n in lines[:5]) + (", ..." if len(lines) > 5 else "")
            # The match itself is never printed: a template that leaks a token must not have the
            # gate re-leak it into CI logs.
            problems.append(f"contains {why} at line(s) {where}")
    return problems


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def _check_rosters_dir(repo: Path, rosters_dir: Path, counts: dict[str, int]) -> list[str]:
    problems = []
    if not rosters_dir.is_dir():
        return [f"{_rel(rosters_dir, repo)}: roster directory not found"]
    core_tools, core_problems = load_core_tools(rosters_dir)
    problems.extend(f"{_rel(rosters_dir / CORE_ROSTER, repo)}: {p}" for p in core_problems)
    for path in sorted(rosters_dir.glob("*.yaml")):
        if path.name == CORE_ROSTER:
            continue
        counts["rosters"] += 1
        problems.extend(f"{_rel(path, repo)}: {p}" for p in check_roster(path, core_tools))
    return problems


def _check_packs_dir(repo: Path, packs_dir: Path, counts: dict[str, int]) -> list[str]:
    problems = []
    if packs_dir.is_dir():
        for path in sorted(packs_dir.glob("*.yaml")):
            counts["packs"] += 1
            problems.extend(f"{_rel(path, repo)}: {p}" for p in check_pack(path))
    else:
        print(f"  NOTE: {_rel(packs_dir, repo)}/ not found — pack check skipped")
    return problems


def _check_prompt_dirs(
    repo: Path, prompts_dir: Path, assembled_dir: Path, counts: dict[str, int]
) -> list[str]:
    problems = []
    sources, assembled = prompt_files(prompts_dir, assembled_dir)
    if not prompts_dir.is_dir():
        print(f"  NOTE: {_rel(prompts_dir, repo)}/ not found — prompt source check skipped")
    if not assembled_dir.is_dir():
        print(f"  NOTE: {_rel(assembled_dir, repo)}/ not found — assembled prompt check skipped")
    for path in sources:
        counts["prompts"] += 1
        problems.extend(f"{_rel(path, repo)}: {p}" for p in check_prompt_source(path))
    for path in assembled:
        counts["prompts"] += 1
        problems.extend(f"{_rel(path, repo)}: {p}" for p in check_assembled_prompt(path))
    return problems


def _check_templates_dir(repo: Path, templates_dir: Path, counts: dict[str, int]) -> list[str]:
    problems = []
    if templates_dir.is_dir():
        for path in sorted(templates_dir.glob("*.md")):
            counts["templates"] += 1
            problems.extend(f"{_rel(path, repo)}: {p}" for p in check_template(path))
    else:
        print(f"  NOTE: {_rel(templates_dir, repo)}/ not found — template check skipped")
    return problems


def run(
    repo: Path,
    rosters_dir: Path,
    *,
    packs_dir: Path,
    prompts_dir: Path,
    assembled_dir: Path,
    templates_dir: Path,
) -> tuple[list[str], dict[str, int]]:
    """Run every check. Returns (problems, counts); each problem is '<file>: <reason>'."""
    counts = {"rosters": 0, "packs": 0, "prompts": 0, "templates": 0}
    problems: list[str] = []
    problems.extend(_check_rosters_dir(repo, rosters_dir, counts))
    problems.extend(_check_packs_dir(repo, packs_dir, counts))
    problems.extend(_check_prompt_dirs(repo, prompts_dir, assembled_dir, counts))
    problems.extend(_check_templates_dir(repo, templates_dir, counts))
    return problems, counts


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate G-7: desk integrity")
    ap.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository checkout to check (default: current directory)",
    )
    ap.add_argument("--rosters-dir", type=Path, help=f"Override {ROSTERS_DIR}/")
    ap.add_argument("--packs-dir", type=Path, help=f"Override {PACKS_DIR}/")
    ap.add_argument("--prompts-dir", type=Path, help=f"Override {PROMPTS_DIR}/")
    ap.add_argument("--assembled-dir", type=Path, help=f"Override {ASSEMBLED_DIR}/")
    ap.add_argument("--templates-dir", type=Path, help=f"Override {TEMPLATES_DIR}/")
    args = ap.parse_args()

    repo = args.repo.resolve()
    problems, counts = run(
        repo,
        rosters_dir=(args.rosters_dir or repo / ROSTERS_DIR).resolve(),
        packs_dir=(args.packs_dir or repo / PACKS_DIR).resolve(),
        prompts_dir=(args.prompts_dir or repo / PROMPTS_DIR).resolve(),
        assembled_dir=(args.assembled_dir or repo / ASSEMBLED_DIR).resolve(),
        templates_dir=(args.templates_dir or repo / TEMPLATES_DIR).resolve(),
    )

    if problems:
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print("  See contracts/README.md and docs/ROSTER.md section 8", file=sys.stderr)
        print(f"G-7 FAIL — desk integrity: {len(problems)} problem(s)", file=sys.stderr)
        return 1

    if counts["templates"]:
        print(f"  {counts['templates']} template(s) clean")
    print(
        f"G-7 PASS — desk integrity: {counts['rosters']} rosters, {counts['packs']} packs, "
        f"{counts['prompts']} prompt files checked"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
