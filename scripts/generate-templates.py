#!/usr/bin/env python3
"""Generate agents/<seat>.md from the seat prompt sources under prompts/.

Each agent file is the frontmatter contract the repository checks (name, title, description,
seat, skills, writes_to_exchange; see agents/chief.md) followed by the seat body. The body is the
prompt source's markdown with the shared security constitution included in place from
prompts/_shared/core-directives.xml.

Every seat is checked against its tool roster (contracts/tool-rosters/<seat>.yaml) and its skills
(skills/<name>/SKILL.md) before anything is written. Nothing is written if a check fails.

    python3 scripts/generate-templates.py            # write agents/<seat>.md
    python3 scripts/generate-templates.py --check    # exit 1 if any agent file differs
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prompt_sources import (
    AGENTS_DIR,
    PLACEHOLDER_RE,
    PromptError,
    SeatSource,
    check_skills,
    expand,
    frontmatter,
    load_core,
    load_roster,
    load_seats,
)


def render(seat: SeatSource, core: dict) -> str:
    body = expand(seat, core)
    text = f"---\n{frontmatter(seat)}---\n{body}"
    # The frontmatter must parse back to exactly the values it was built from.
    meta = yaml.safe_load(frontmatter(seat))
    same_name = meta["name"] == seat.name
    if not same_name or meta["seat"] != seat.channel or meta["skills"] != list(seat.skills):
        raise PromptError(f"{seat.path.name}: frontmatter does not round-trip")
    match = PLACEHOLDER_RE.search(text)
    if match:
        raise PromptError(f"{seat.path.name}: unfilled placeholder {match.group(0)}")
    return text


def build(core: dict) -> dict[Path, str]:
    """Every agent file, keyed by its path. Raises before returning if anything is inconsistent."""
    seats = load_seats()
    out: dict[Path, str] = {}
    problems: list[str] = []
    for seat in seats:
        try:
            load_roster(seat)
        except PromptError as exc:
            problems.append(str(exc))
            continue
        missing = check_skills(seat)
        if missing:
            problems.append(f"{seat.path.name}: skill(s) not in skills/: {', '.join(missing)}")
            continue
        try:
            out[AGENTS_DIR / f"{seat.short}.md"] = render(seat, core)
        except PromptError as exc:
            problems.append(str(exc))
    if problems:
        raise PromptError("\n".join(problems))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate agents/<seat>.md from prompts/")
    ap.add_argument("--check", action="store_true", help="compare, write nothing, exit 1 on drift")
    args = ap.parse_args()

    try:
        expected = build(load_core())
    except PromptError as exc:
        print(f"generate-templates: {exc}", file=sys.stderr)
        return 1

    if not args.check:
        for path, text in expected.items():
            path.write_text(text, encoding="utf-8")
            print(f"wrote {path.relative_to(AGENTS_DIR.parent)}")
        return 0

    problems: list[str] = []
    for path, text in expected.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current is None:
            problems.append(f"{path.name}: missing (run scripts/generate-templates.py)")
        elif current != text:
            diff = "".join(
                difflib.unified_diff(
                    current.splitlines(keepends=True),
                    text.splitlines(keepends=True),
                    fromfile=f"{path.name} (committed)",
                    tofile=f"{path.name} (generated)",
                    n=2,
                )
            )
            problems.append(f"{path.name}: drift from prompts/\n{diff}")
    generated = set(expected)
    for path in sorted(AGENTS_DIR.glob("*.md")):
        if path.name != "README.md" and path not in generated:
            problems.append(f"{path.name}: stale, no prompt source produces it")

    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        print(f"agent drift: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(f"agents clean: {len(expected)} agent files match prompts/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
