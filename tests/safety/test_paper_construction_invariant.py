"""PaperAdapter is constructed only by the verified factory (PAPER-004, Phase 13).

Every production construction of ``PaperAdapter`` in ``src/pumpgrok`` must go through
``src/pumpgrok/execution/paper_factory.py``, which is the only module allowed to call the
constructor. The factory is what binds replay authority to BUY entries, so a second
construction site would silently bypass it. Test helpers live under ``tests/`` and sit
outside this scan. Alias-resolving AST, same precedent as ``test_no_direct_time.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"
FACTORY = "execution/paper_factory.py"
CLASS_NAME = "PaperAdapter"


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
                mapping[alias.asname or alias.name] = alias.name
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


def _constructions(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = _aliases(tree)
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        resolved = _resolve(node.func, aliases)
        if resolved is not None and resolved.rsplit(".", 1)[-1] == CLASS_NAME:
            lines.append(node.lineno)
    return lines


def _scan() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        lines = _constructions(path)
        if lines:
            found[rel] = lines
    return found


def test_factory_is_the_only_paper_adapter_constructor_in_src() -> None:
    found = _scan()
    # Non-vacuity: the scan must see the factory's own construction, or it proves nothing.
    assert FACTORY in found, "the invariant scan no longer sees the factory's construction"
    offenders = {rel: lines for rel, lines in found.items() if rel != FACTORY}
    assert not offenders, (
        f"PaperAdapter constructed outside {FACTORY}; route it through build_paper_adapter: "
        f"{offenders}"
    )
