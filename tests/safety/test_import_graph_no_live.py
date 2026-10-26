"""LIV-01 import-graph proof: no guarded path reaches the live adapter.

Transitive AST reachability over src/pumpgrok. Guarded roots are the
backtest package, the paper adapter, the upgrade package, the supervisor
package and the CLI. The test resolves the import closure of each root
and asserts no path in the closure reaches the quarantined module
pumpgrok.execution.live.live_adapter or names the LiveAdapterStub
symbol. Imports of the gate module live_gate stay allowed because the
CLI refusal and the weekly report read the gate without reaching an
adapter. Modules under src/pumpgrok/execution/live/ additionally import
no network client and open no socket. Offline only, ASCII only.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "pumpgrok"
LIVE_DIR = SRC / "execution" / "live"

QUARANTINE_MODULE = "pumpgrok.execution.live.live_adapter"
QUARANTINE_SYMBOL = "LiveAdapterStub"
GATE_MODULE = "pumpgrok.execution.live.live_gate"

GUARDED_PREFIXES = (
    "pumpgrok.backtest",
    "pumpgrok.upgrade",
    "pumpgrok.supervisor",
)
GUARDED_MODULES = (
    "pumpgrok.execution.paper_adapter",
    "pumpgrok.cli",
)

NETWORK_ROOTS = frozenset(
    {
        "aiohttp",
        "http",
        "httpx",
        "requests",
        "socket",
        "solana",
        "solders",
        "ssl",
        "urllib",
        "websocket",
        "websockets",
    }
)

SOCKET_ATTRS = frozenset(
    {
        "accept",
        "bind",
        "connect",
        "create_connection",
        "listen",
        "send",
        "sendall",
        "sendto",
        "socket",
        "wrap_bio",
        "wrap_context",
    }
)


def _module_name(path: Path) -> str:
    """Dotted module name for one file under src/pumpgrok."""
    rel = path.relative_to(SRC).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return "pumpgrok." + ".".join(parts)


def _module_map(root: Path = SRC) -> dict[str, Path]:
    """Every module under root by dotted name."""
    found: dict[str, Path] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        found[_module_name(path)] = path
    return found


def _package_of(module: str, path: Path) -> str:
    """Containing package for relative import resolution."""
    if path.name == "__init__.py":
        return module
    return module.rpartition(".")[0]


def _imports_of(module: str, path: Path) -> set[str]:
    """Absolute module dependencies declared by one file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return set()
    package = _package_of(module, path)
    deps: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                deps.add(item.name)
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            base = package
            for _ in range(level - 1):
                base = base.rpartition(".")[0]
            if node.module:
                target = f"{base}.{node.module}" if level else node.module
                deps.add(target)
                # from pkg import child: a child module is an edge; _resolve drops non-modules.
                for item in node.names:
                    if item.name != "*":
                        deps.add(f"{target}.{item.name}")
            elif level:
                for item in node.names:
                    if item.name != "*":
                        deps.add(f"{base}.{item.name}" if base else item.name)
    return deps


def _resolve(dep: str, modules: dict[str, Path]) -> str | None:
    """Known module matching one absolute import, or None when external."""
    if dep in modules:
        return dep
    # from pumpgrok.execution import live names a submodule through its
    # parent; resolve to the submodule when it exists.
    prefix = dep + "."
    candidates = [name for name in modules if name.startswith(prefix)]
    if candidates:
        return sorted(candidates)[0]
    return None


def _edges(modules: dict[str, Path]) -> dict[str, set[str]]:
    """Internal import edges between known modules."""
    graph: dict[str, set[str]] = {}
    for module, path in modules.items():
        targets: set[str] = set()
        for dep in _imports_of(module, path):
            resolved = _resolve(dep, modules)
            if resolved is not None and resolved != module:
                targets.add(resolved)
        graph[module] = targets
    return graph


def _closure(roots: set[str], graph: dict[str, set[str]]) -> dict[str, list[str]]:
    """One witness path per reachable module from the roots."""
    seen: dict[str, list[str]] = {}
    queue: list[tuple[str, list[str]]] = [(root, [root]) for root in sorted(roots)]
    while queue:
        module, trail = queue.pop(0)
        if module in seen:
            continue
        seen[module] = trail
        for target in sorted(graph.get(module, ())):
            if target not in seen:
                queue.append((target, [*trail, target]))
    return seen


def _guarded_roots(modules: dict[str, Path]) -> set[str]:
    """Root modules for the guarded closures."""
    roots = set(GUARDED_MODULES)
    for module in modules:
        if module in GUARDED_PREFIXES or module.startswith(
            tuple(prefix + "." for prefix in GUARDED_PREFIXES)
        ):
            roots.add(module)
    return {root for root in roots if root in modules}


def _stub_references(path: Path) -> list[str]:
    """One entry per LiveAdapterStub name use in the file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == QUARANTINE_SYMBOL:
            found.append(f"{path}:{node.lineno}: names {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr == QUARANTINE_SYMBOL:
            found.append(f"{path}:{node.lineno}: names {node.attr}")
    return found


def _network_references(path: Path) -> list[str]:
    """One entry per network client import or socket open in a live file."""
    try:
        rel = path.relative_to(SRC).as_posix()
    except ValueError:
        rel = path.name
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                root = item.name.split(".")[0]
                if root in NETWORK_ROOTS:
                    found.append(f"{rel}:{node.lineno}: imports {item.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            root = module.split(".")[0]
            if root in NETWORK_ROOTS:
                found.append(f"{rel}:{node.lineno}: from {module} import ...")
        elif isinstance(node, ast.Attribute) and node.attr in SOCKET_ATTRS:
            value = node.value
            if isinstance(value, ast.Name) and value.id in ("socket", "ssl"):
                found.append(f"{rel}:{node.lineno}: opens {value.id}.{node.attr}")
    return found


def _live_files() -> list[Path]:
    return sorted(path for path in LIVE_DIR.rglob("*.py") if "__pycache__" not in path.parts)


def test_guarded_closures_never_reach_live_adapter() -> None:
    """LIV-01: no guarded root gains a transitive path to the live adapter."""
    modules = _module_map()
    assert modules, "no modules found under src/pumpgrok"
    assert QUARANTINE_MODULE in modules, "quarantined adapter module is missing"
    assert GATE_MODULE in modules, "gate module is missing"
    roots = _guarded_roots(modules)
    assert roots == set(GUARDED_MODULES) | {
        module
        for module in modules
        if module in GUARDED_PREFIXES
        or module.startswith(tuple(prefix + "." for prefix in GUARDED_PREFIXES))
    }
    graph = _edges(modules)
    seen = _closure(roots, graph)
    assert QUARANTINE_MODULE not in seen, " -> ".join(
        seen.get(QUARANTINE_MODULE, [QUARANTINE_MODULE])
    )
    offenders = []
    for module in sorted(seen):
        offenders.extend(_stub_references(modules[module]))
    assert offenders == []


def test_gate_module_stays_reachable_but_adapter_free() -> None:
    """G-02: the gate is a legitimate reader dependency, the adapter is not."""
    modules = _module_map()
    graph = _edges(modules)
    cli_seen = _closure({"pumpgrok.cli"}, graph)
    assert GATE_MODULE in cli_seen
    assert QUARANTINE_MODULE not in cli_seen


def test_live_package_holds_no_network_client() -> None:
    """D-04: no module under execution/live/ imports a client or opens a socket."""
    assert LIVE_DIR.is_dir()
    offenders = []
    for path in _live_files():
        offenders.extend(_network_references(path))
    assert offenders == []


IMPORT_PROBES: list[tuple[str, bool]] = [
    ("import pumpgrok.execution.live.live_adapter\n", True),
    ("from pumpgrok.execution.live.live_adapter import LiveAdapterStub\n", True),
    ("from pumpgrok.execution.live import live_adapter as adapter\n", True),
    ("from pumpgrok.execution.live.live_gate import LiveGate\n", False),
    ("from pumpgrok.backtest.evaluate import CandidateParams\n", False),
]

SYMBOL_PROBES: list[tuple[str, bool]] = [
    ("adapter = LiveAdapterStub()\n", True),
    ("gate = LiveGate()\n", False),
    ("live_adapter_note = 'LiveAdapterStub'\n", False),
]

NETWORK_PROBES: list[tuple[str, bool]] = [
    ("import socket\n", True),
    ("from urllib import request\n", True),
    ("x = socket.socket()\n", True),
    ("import json\n", False),
    ("import sqlite3\n", False),
]


@pytest.mark.parametrize(("source", "flagged"), IMPORT_PROBES)
def test_import_probe_resolves_to_quarantine(tmp_path: Path, source: str, flagged: bool) -> None:
    """Import extraction resolves adapter imports, not gate or backtest imports."""
    package = tmp_path / "mod.py"
    package.write_text(source, encoding="utf-8")
    modules = {
        "pumpgrok.execution.live": package,
        "pumpgrok.execution.live.live_adapter": package,
    }
    deps = _imports_of("pumpgrok.guard", package)
    hits = {dep for dep in deps if _resolve(dep, modules) == QUARANTINE_MODULE}
    assert bool(hits) is flagged, deps


@pytest.mark.parametrize(("source", "flagged"), SYMBOL_PROBES)
def test_symbol_probe_is_classified(tmp_path: Path, source: str, flagged: bool) -> None:
    """The symbol scan flags LiveAdapterStub uses, not strings or other names."""
    package = tmp_path / "mod.py"
    package.write_text(source, encoding="utf-8")
    assert bool(_stub_references(package)) is flagged


@pytest.mark.parametrize(("source", "flagged"), NETWORK_PROBES)
def test_network_probe_is_classified(tmp_path: Path, source: str, flagged: bool) -> None:
    """The network scan flags client imports and socket opens, not stdlib IO."""
    package = tmp_path / "live_probe.py"
    package.write_text(source, encoding="utf-8")
    assert bool(_network_references(package)) is flagged
