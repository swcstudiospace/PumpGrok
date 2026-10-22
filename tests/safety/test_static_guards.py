"""Static guards for virtual time, seeded randomness and identity.

ROADMAP SC5, paper-engine 4.1-4.2.

AST walk over src/pumpgrok. Comments and docstrings are not call sites in the AST, so
prose never counts as a violation. Import aliases are resolved first, so
`import asyncio as aio` cannot hide `aio.sleep`.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"

# The only module allowed to read wall time or sleep on a real loop (paper-engine 4.1).
CLOCK_ALLOWLIST = frozenset({"replay/clock.py"})
# The only module allowed to construct random.Random (paper-engine 4.2, make_rng).
RNG_ALLOWLIST = frozenset({"replay/rng.py"})

_CLOCK_PRIMITIVES = frozenset(
    {
        "asyncio.sleep",
        "asyncio.timeout",
        "asyncio.wait_for",
        "time.time",
        "time.monotonic",
        "datetime.now",
        "datetime.utcnow",
        "datetime.today",
        "date.today",
    }
)


def _is_ambient_random(resolved: str) -> bool:
    """Every attribute of the random module except the seeded Random class (paper-engine 4.2)."""
    return resolved.startswith("random.") and resolved != "random.Random"


_BANNED_MODULES = frozenset({"uuid", "secrets"})


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
    clock_ok = rel in CLOCK_ALLOWLIST
    rng_ok = rel in RNG_ALLOWLIST
    found: list[tuple[int, str]] = []

    def flag(line: int, reason: str) -> None:
        found.append((line, reason))

    def check_module(module: str, line: int) -> None:
        root = module.split(".", maxsplit=1)[0]
        if root in _BANNED_MODULES:
            flag(line, f"import of {root} is banned")
        elif root == "time" and not clock_ok:
            flag(line, "time module used outside replay/clock.py")

    def check_reference(resolved: str, line: int) -> None:
        head = resolved.split(".", maxsplit=1)[0]
        tail = ".".join(resolved.split(".")[-2:])
        if head in _BANNED_MODULES:
            flag(line, f"use of {head} is banned")
        elif (head == "time" or tail in _CLOCK_PRIMITIVES) and not clock_ok:
            flag(line, f"{tail} used outside replay/clock.py")
        elif _is_ambient_random(resolved):
            flag(line, f"ambient randomness {resolved} is banned")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                check_module(alias.name, node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            check_module(node.module, node.lineno)
            for alias in node.names:
                qualified = f"{node.module}.{alias.name}"
                if qualified in _CLOCK_PRIMITIVES and not clock_ok:
                    flag(node.lineno, f"{qualified} imported outside replay/clock.py")
                if _is_ambient_random(qualified):
                    flag(node.lineno, f"ambient randomness {qualified} is banned")
        elif isinstance(node, (ast.Attribute, ast.Name)):
            resolved = _resolve(node, aliases)
            if resolved is not None:
                check_reference(resolved, node.lineno)
        elif isinstance(node, ast.Call) and _resolve(node.func, aliases) == "random.Random":
            if not rng_ok:
                flag(node.lineno, "random.Random constructed outside replay/rng.py")
            if not node.args and not node.keywords:
                flag(node.lineno, "unseeded random.Random() is banned")

    return [f"{rel}:{line}: {reason}" for line, reason in sorted(found)]


def find_violations(package_root: Path) -> list[str]:
    """Return one `path:line: reason` entry per forbidden code use under `package_root`."""
    found: list[str] = []
    for path in sorted(package_root.rglob("*.py")):
        found.extend(_scan_file(path, path.relative_to(package_root).as_posix()))
    return found


def test_src_pumpgrok_has_no_forbidden_primitives() -> None:
    assert find_violations(SRC) == []


def test_clock_allowlist_is_exactly_the_replay_clock_module() -> None:
    assert frozenset({"replay/clock.py"}) == CLOCK_ALLOWLIST
    assert (SRC / "replay" / "clock.py").is_file()


PROBES: list[tuple[str, str, bool]] = [
    ("core/probe.py", "import time\n\nSTAMP = time.time()\n", True),
    ("core/probe.py", "import asyncio\n\nasync def f():\n    await asyncio.sleep(1)\n", True),
    (
        "core/probe.py",
        "import asyncio\n\nasync def f():\n    async with asyncio.timeout(1):\n        pass\n",
        True,
    ),
    (
        "core/probe.py",
        "import asyncio as aio\n\nasync def f(c):\n    await aio.wait_for(c, 1)\n",
        True,
    ),
    ("core/probe.py", "from asyncio import sleep\n\nasync def f():\n    await sleep(1)\n", True),
    ("core/probe.py", "from datetime import datetime\n\nNOW = datetime.now()\n", True),
    ("core/probe.py", "import uuid\n\nIDENT = uuid.uuid4()\n", True),
    ("core/probe.py", "import secrets\n\nTOKEN = secrets.token_hex(8)\n", True),
    ("core/probe.py", "import random\n\nX = random.random()\n", True),
    ("core/probe.py", "import random\n\nX = random.randint(1, 6)\n", True),
    ("core/probe.py", "import random\n\nX = random.choice([1, 2])\n", True),
    ("core/probe.py", "from random import randint\n\nX = randint(1, 6)\n", True),
    ("core/probe.py", "from datetime import datetime\n\nNOW = datetime.utcnow()\n", True),
    ("core/probe.py", "from datetime import datetime\n\nNOW = datetime.today()\n", True),
    ("core/probe.py", "from datetime import date\n\nTODAY = date.today()\n", True),
    (
        "core/probe.py",
        "from random import Random\n\ndef f(r: Random) -> int:\n    return r.getrandbits(8)\n",
        False,
    ),
    ("core/probe.py", "import random\n\nRNG = random.Random()\n", True),
    ("core/probe.py", "import random\n\nRNG = random.Random(7)\n", True),
    (
        "replay/rng.py",
        "import random\n\ndef make_rng(seed: int = 1) -> random.Random:\n"
        "    return random.Random(seed)\n",
        False,
    ),
    ("replay/rng.py", "import random\n\nRNG = random.Random()\n", True),
    ("replay/clock.py", "import time\n\nSTAMP = time.time()\n", False),
    (
        "core/probe.py",
        "import random\n\ndef f(rng: random.Random) -> int:\n    return rng.getrandbits(8)\n",
        False,
    ),
    ("core/probe.py", "# time.time() and asyncio.sleep() and uuid are banned\nVALUE = 1\n", False),
    (
        "core/probe.py",
        '"""Never call random.random() or datetime.now() here."""\nVALUE = 1\n',
        False,
    ),
    (
        "core/probe.py",
        "from pumpgrok.replay.clock import Clock\n\nCLOCK: Clock | None = None\n",
        False,
    ),
]


@pytest.mark.parametrize(("rel", "source", "flagged"), PROBES)
def test_probe_is_classified(tmp_path: Path, rel: str, source: str, flagged: bool) -> None:
    package = tmp_path / "pumpgrok"
    target = package / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    found = find_violations(package)
    assert bool(found) is flagged, found


def test_smuggled_wall_clock_in_scratch_copy_is_caught(tmp_path: Path) -> None:
    package = tmp_path / "pumpgrok"
    shutil.copytree(SRC, package, ignore=shutil.ignore_patterns("__pycache__"))
    ids = package / "core" / "ids.py"
    ids.write_text(ids.read_text(encoding="utf-8") + "\nimport time\n\n_SMUGGLED = time.time()\n")
    found = find_violations(package)
    assert any(entry.startswith("core/ids.py:") for entry in found), found

def _imports_prometheus_client(path: Path) -> list[str]:
    """Return `rel:line` entries for prometheus_client imports in one file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(SRC).as_posix()
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "prometheus_client" or alias.name.startswith(
                    "prometheus_client."
                ):
                    found.append(f"{rel}:{node.lineno}: imports prometheus_client")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "prometheus_client" or module.startswith("prometheus_client."):
                found.append(f"{rel}:{node.lineno}: imports {module}")
    return found


def test_no_prometheus_client_outside_supervisor() -> None:
    """Only the supervisor writes metrics; core/ and risk/ never import the client."""
    offenders: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        if path.relative_to(SRC).as_posix().startswith("supervisor/"):
            continue
        offenders.extend(_imports_prometheus_client(path))
    assert offenders == []
