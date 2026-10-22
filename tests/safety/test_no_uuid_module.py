"""The uuid module is banned in src/pumpgrok (INV-S-15).

Ids come from ``src/pumpgrok/core/ids.py`` (ULID from clock plus seeded
rng, R29). Any ``import uuid`` or ``from uuid import ...`` outside that
rule fails.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"


def _scan_file(path: Path, rel: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".", maxsplit=1)[0] == "uuid":
                    found.append(f"{rel}:{node.lineno}: uuid import is banned")
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.level == 0
            and node.module.split(".", maxsplit=1)[0] == "uuid"
        ):
            found.append(f"{rel}:{node.lineno}: uuid import is banned")
    return found


def find_violations() -> list[str]:
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        found.extend(_scan_file(path, path.relative_to(SRC).as_posix()))
    return found


def test_uuid_never_imported() -> None:
    """INV-S-15: no uuid module anywhere in src/pumpgrok."""
    assert find_violations() == []


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ("import uuid\n", True),
        ("from uuid import uuid4\n", True),
        ("import uuid as u\n", True),
        ("from pumpgrok.core.ids import IdFactory\n", False),
    ],
)
def test_probe_is_classified(tmp_path: Path, source: str, flagged: bool) -> None:
    package = tmp_path / "mod.py"
    package.write_text(source, encoding="utf-8")
    assert bool(_scan_file(package, "mod.py")) is flagged
