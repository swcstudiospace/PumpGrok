#!/usr/bin/env python3
"""Generate contracts/events/<snake>.schema.json for the 18 R32 ledger event types.

The pydantic models in src/pumpgrok/ledger/events.py are the only vocabulary. Each schema is
the JSON Schema of one model, written byte-stably. Never hand-edit the output: change the model
and regenerate.

    uv run python scripts/generate-event-schemas.py            # write contracts/events/
    uv run python scripts/generate-event-schemas.py --check    # exit 1 on drift or stale files
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pumpgrok.ledger.events import event_json_schemas  # noqa: E402

OUT_DIR = REPO_ROOT / "contracts" / "events"
SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"


def render(schema: dict) -> str:
    doc = {"$schema": SCHEMA_DRAFT, **schema}
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate contracts/events/*.schema.json")
    ap.add_argument("--check", action="store_true", help="compare, write nothing, exit 1 on drift")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR, help=f"default: {OUT_DIR}")
    args = ap.parse_args()

    expected = {f"{name}.schema.json": render(s) for name, s in event_json_schemas().items()}
    out_dir: Path = args.out_dir

    if not args.check:
        out_dir.mkdir(parents=True, exist_ok=True)
        for filename, text in expected.items():
            (out_dir / filename).write_text(text, encoding="utf-8")
        print(f"wrote {len(expected)} event schemas to {out_dir}")
        return 0

    problems: list[str] = []
    for filename, text in expected.items():
        path = out_dir / filename
        if not path.exists():
            problems.append(f"{filename}: missing (run scripts/generate-event-schemas.py)")
            continue
        current = path.read_text(encoding="utf-8")
        if current != text:
            diff = "".join(
                difflib.unified_diff(
                    current.splitlines(keepends=True),
                    text.splitlines(keepends=True),
                    fromfile=f"{filename} (committed)",
                    tofile=f"{filename} (generated)",
                    n=2,
                )
            )
            problems.append(f"{filename}: drift from ledger/events.py\n{diff}")
    if out_dir.is_dir():
        for path in sorted(out_dir.glob("*.schema.json")):
            if path.name not in expected:
                problems.append(f"{path.name}: stale, no model produces it")

    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        print(f"event schema drift: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(f"event schemas clean: {len(expected)} schemas match ledger/events.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
