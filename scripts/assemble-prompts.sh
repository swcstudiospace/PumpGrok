#!/usr/bin/env bash
# Assemble each seat prompt source under prompts/ into prompts-assembled/<SEAT>.xml.
# The shared security constitution is included in place from prompts/_shared/core-directives.xml
# (see scripts/prompt_sources.py). Each assembled prompt also lists the seat's effective tool
# roster (core eight plus the seat's own tools) from contracts/tool-rosters/.
# Any {{...}} left after assembly is an error: an assembled prompt is what gets installed.
#
#   scripts/assemble-prompts.sh [--check]
#
#   --check  Assemble into a temp dir and diff against prompts-assembled/. Writes nothing.
#            Exit 1 on drift or on a stale file.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="write"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)
      MODE="check"; shift ;;
    -h|--help)
      sed -n '2,12p' "$0"; exit 0 ;;
    *)
      echo "assemble-prompts: unknown argument $1" >&2; exit 2 ;;
  esac
done

python3 - "$ROOT" "$MODE" <<'PY'
import difflib, sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

root, mode = Path(sys.argv[1]), sys.argv[2]
sys.path.insert(0, str(root / "scripts"))

from prompt_sources import (  # noqa: E402
    ASSEMBLED_DIR,
    PLACEHOLDER_RE,
    PromptError,
    SeatSource,
    check_skills,
    effective_tools,
    expand,
    load_core,
    load_roster,
    load_seats,
)


def assemble(seat: SeatSource, core: dict) -> str:
    roster = load_roster(seat)
    tools = effective_tools(seat)
    body = expand(seat, core)
    if "]]>" in body:
        raise PromptError(f"{seat.path.name}: body contains ']]>', which ends the CDATA section")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!--",
        f"  Assembled from prompts/{seat.path.name} and prompts/_shared/core-directives.xml by",
        "  scripts/assemble-prompts.sh. Generated: do not edit; change the source and regenerate.",
        "-->",
        f"<prompt seat={quoteattr(seat.seat)} name={quoteattr(seat.name)}"
        f" title={quoteattr(seat.title)} channel={quoteattr(seat.channel)}"
        f" writes_to_exchange={quoteattr('true' if seat.writes_to_exchange else 'false')}>",
        "  <skills>",
        *[f"    <skill>{s}</skill>" for s in seat.skills],
        "  </skills>",
        f"  <instructions><![CDATA[{body}]]></instructions>",
        f"  <roster endpoint={quoteattr(roster['endpoint'])} effective-tools=\"{len(tools)}\" contract={quoteattr(seat.tools_contract)}>",
    ]
    for tool in tools:
        lines.append(
            f"    <tool name={quoteattr(tool['name'])} kind={quoteattr(tool['kind'])}"
            f" side_effect={quoteattr(tool['side_effect'])}"
            f" gates={quoteattr(','.join(tool['gates']))}/>"
        )
    lines += ["  </roster>", "</prompt>"]
    text = "\n".join(lines) + "\n"
    match = PLACEHOLDER_RE.search(text)
    if match:
        raise PromptError(f"{seat.path.name}: unfilled placeholder {match.group(0)} after assembly")
    return text


def build() -> dict[str, str]:
    core = load_core()
    seats = load_seats()
    out: dict[str, str] = {}
    problems: list[str] = []
    for seat in seats:
        try:
            load_roster(seat)
            missing = check_skills(seat)
            if missing:
                raise PromptError(f"{seat.path.name}: skill(s) not in skills/: {', '.join(missing)}")
            out[f"{seat.name}.xml"] = assemble(seat, core)
        except PromptError as exc:
            problems.append(str(exc))
    if problems:
        raise PromptError("\n".join(problems))
    return out


try:
    expected = build()
except PromptError as exc:
    print(f"assemble-prompts: {exc}", file=sys.stderr)
    sys.exit(1)

if mode == "write":
    ASSEMBLED_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in expected.items():
        (ASSEMBLED_DIR / name).write_text(text, encoding="utf-8")
    for path in sorted(ASSEMBLED_DIR.glob("*.xml")):
        if path.name not in expected:
            path.unlink()
            print(f"removed stale {path.relative_to(root)}")
    print(f"assembled {len(expected)} prompts into {ASSEMBLED_DIR.relative_to(root)}/")
    sys.exit(0)

problems: list[str] = []
for name, text in expected.items():
    path = ASSEMBLED_DIR / name
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current is None:
        problems.append(f"{name}: missing (run scripts/assemble-prompts.sh)")
    elif current != text:
        diff = "".join(
            difflib.unified_diff(
                current.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile=f"{name} (committed)",
                tofile=f"{name} (assembled)",
                n=2,
            )
        )
        problems.append(f"{name}: drift from prompts/\n{diff}")
if ASSEMBLED_DIR.is_dir():
    for path in sorted(ASSEMBLED_DIR.glob("*.xml")):
        if path.name not in expected:
            problems.append(f"{path.name}: stale, no prompt source produces it")

if problems:
    for p in problems:
        print(p, file=sys.stderr)
    print(f"assembled prompt drift: {len(problems)} problem(s)", file=sys.stderr)
    sys.exit(1)
print(f"assembled prompts clean: {len(expected)} prompts match prompts/")
PY
