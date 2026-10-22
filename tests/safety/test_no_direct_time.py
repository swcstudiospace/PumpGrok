"""Virtual time only outside replay/clock.py (INV-S-13).

No direct ``asyncio.sleep``, ``asyncio.timeout``, ``asyncio.wait_for``
with a numeric timeout, ``time.time``, ``time.monotonic``,
``datetime.now()`` or ``datetime.utcnow()`` in ``src/pumpgrok/`` except
inside ``src/pumpgrok/replay/clock.py`` (the ``WallClock``
implementation). Every ``AsyncRetrying``/``retry`` call site passes an
explicit ``sleep=`` bound to the injected clock (R27). Alias-resolving
AST, same precedent as ``test_static_guards.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"
CLOCK_MODULE = "replay/clock.py"

CLOCK_PRIMITIVES = frozenset(
    {
        "asyncio.sleep",
        "asyncio.timeout",
        "asyncio.wait_for",
        "time.time",
        "time.monotonic",
        "datetime.now",
        "datetime.utcnow",
        "datetime.datetime.now",
        "datetime.datetime.utcnow",
    }
)


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return None if base is None else f"{base}.{node.attr}"
    return None


def _aliases(tree: ast.AST) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    mapping[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for alias in node.names:
                mapping[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return mapping


def _resolve(node: ast.AST, aliases: dict[str, str]) -> str | None:
    name = _dotted(node)
    if name is None:
        return None
    head, dot, rest = name.partition(".")
    return aliases.get(head, head) + dot + rest


def _scan_file(path: Path, rel: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = _aliases(tree)
    found: list[str] = []
    if rel == CLOCK_MODULE:
        return found
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Name)):
            resolved = _resolve(node, aliases)
            if resolved is None:
                continue
            tail = ".".join(resolved.split(".")[-2:])
            if resolved in CLOCK_PRIMITIVES or tail in CLOCK_PRIMITIVES:
                found.append(f"{rel}:{node.lineno}: wall clock {resolved}")
        elif isinstance(node, ast.Call):
            resolved = _resolve(node.func, aliases)
            if (
                resolved in {"AsyncRetrying", "retry"}
                or (resolved is not None and resolved.endswith((".AsyncRetrying", ".retry")))
            ) and not any(kw.arg == "sleep" for kw in node.keywords):
                found.append(f"{rel}:{node.lineno}: retry without sleep=")
    return found


def find_violations() -> list[str]:
    found: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        found.extend(_scan_file(path, path.relative_to(SRC).as_posix()))
    return found


def test_no_wall_clock_outside_clock_module() -> None:
    """INV-S-13: virtual time only; tenacity always sleeps on the clock."""
    assert find_violations() == []


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ("import asyncio\nasync def f():\n    await asyncio.sleep(1)\n", True),
        ("import time\ntime.time()\n", True),
        ("from datetime import datetime\ndatetime.now()\n", True),
        (
            "from tenacity import AsyncRetrying\nasync for a in AsyncRetrying():\n    pass\n",
            True,
        ),
        (
            "from tenacity import AsyncRetrying\n"
            "async for a in AsyncRetrying(sleep=clock.sleep):\n    pass\n",
            False,
        ),
        ("import asyncio\nasync def f():\n    await clock.sleep(1)\n", False),
    ],
)
def test_probe_is_classified(tmp_path: Path, source: str, flagged: bool) -> None:
    package = tmp_path / "mod.py"
    package.write_text(source, encoding="utf-8")
    assert bool(_scan_file(package, "mod.py")) is flagged
