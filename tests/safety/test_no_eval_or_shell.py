"""No eval/exec/shell-true/list-argv violations (INV-S-04).

Scope: every ``.py`` under ``src/``, ``tools/``, ``scripts/``, ``hermes/``,
``services/``, ``ci/``, plus any ``tools/*.py`` path a ``skills/*/SKILL.md``
references (resolved to the repo-root file; ``pumpgrok <verb>`` subcommands
resolve to ``src/pumpgrok/cli.py``, already in scope).

Rules (AST, alias-resolving, never grep-only):
- ``eval``, ``exec`` and bare ``compile`` calls are forbidden. Dotted uses
  such as ``re.compile`` resolve to ``re.compile`` and are allowed.
- ``os.system`` and ``os.popen`` calls are forbidden.
- Any ``subprocess.*`` call with ``shell=True`` is forbidden.
- Every ``subprocess.*`` call takes a list/tuple argv as its first
  positional, never a bare string or f-string. Element-level interpolation
  inside a list argv (for example ``f"{base}...HEAD"`` or ``str(path)`` in
  ``ci/gates/`` and ``ci/tests/``) stays list-argv: without ``shell=True``
  (proven by the companion assertion) it cannot become a shell, so the
  check asserts the argv shape, not the absence of interpolation.
- ``import subprocess`` appears only in the allowlist: ``ci/gates/*.py``
  plus ``ci/tests/*.py`` (the harness spawns the gates under test with the
  same list-argv pattern as ``ci/gates/run_all.py``).
  (``src/pumpgrok/cli.py`` is a named allowlist member per the invariant
  but currently imports no subprocess; the assertion is a subset check so
  either state passes).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "pumpgrok"

SCOPED_DIRS = ("src", "tools", "scripts", "hermes", "services", "ci")

SKIP_PARTS = frozenset(
    {
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        ".git",
    }
)

SKILL_TOOL_RE = re.compile(r"tools/[a-z_]+\.py")

# Files allowed to import the subprocess module (INV-S-04 allowlist).
SUBPROCESS_IMPORT_ALLOWLIST = frozenset({"src/pumpgrok/cli.py"})

FORBIDDEN_CALLS = frozenset({"eval", "exec", "compile", "os.system", "os.popen"})


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


def _scan_file(path: Path, rel: str, allowed_importers: set[str] | None = None) -> list[str]:
    allowed = _allowed_importers() if allowed_importers is None else allowed_importers
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = _aliases(tree)
    found: list[tuple[int, str]] = []

    def flag(line: int, reason: str) -> None:
        found.append((line, reason))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", maxsplit=1)[0]
                if root == "subprocess" and rel not in allowed:
                    flag(node.lineno, f"subprocess imported outside allowlist ({rel})")
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            root = node.module.split(".", maxsplit=1)[0]
            if root == "subprocess" and rel not in allowed:
                flag(node.lineno, f"subprocess imported outside allowlist ({rel})")
        elif isinstance(node, ast.Call):
            resolved = _resolve(node.func, aliases)
            if resolved in FORBIDDEN_CALLS:
                flag(node.lineno, f"forbidden call {resolved}")
                continue
            if resolved is not None and resolved.startswith("subprocess."):
                for keyword in node.keywords:
                    if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant):
                        if keyword.value.value is True:
                            flag(node.lineno, "subprocess call with shell=True")
                if node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Starred):
                        continue
                    if not isinstance(first, (ast.List, ast.Tuple)):
                        flag(node.lineno, "subprocess argv is not a list/tuple")
            elif resolved == "asyncio.create_subprocess_exec":
                if node.args:
                    first = node.args[0]
                    if not isinstance(first, (ast.Starred, ast.List, ast.Tuple)):
                        flag(node.lineno, "create_subprocess_exec argv is not an unpacked list")
    return [f"{rel}:{line}: {reason}" for line, reason in sorted(found)]


def _allowed_importers() -> set[str]:
    allowed = set(SUBPROCESS_IMPORT_ALLOWLIST)
    for sub in ("ci/gates", "ci/tests"):
        root = REPO_ROOT / sub
        if root.is_dir():
            for path in sorted(root.glob("*.py")):
                allowed.add(path.relative_to(REPO_ROOT).as_posix())
    return allowed


def _scoped_files() -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for dirname in SCOPED_DIRS:
        root = REPO_ROOT / dirname
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            if SKIP_PARTS & set(path.parts):
                continue
            files.append((path, path.relative_to(REPO_ROOT).as_posix()))
    skills = REPO_ROOT / "skills"
    if skills.is_dir():
        for doc in sorted(skills.rglob("SKILL.md")):
            for match in SKILL_TOOL_RE.findall(doc.read_text(encoding="utf-8")):
                candidate = REPO_ROOT / match
                if candidate.is_file():
                    rel = candidate.relative_to(REPO_ROOT).as_posix()
                    if all(rel != seen for _, seen in files):
                        files.append((candidate, rel))
    return files


def find_violations() -> list[str]:
    found: list[str] = []
    for path, rel in _scoped_files():
        found.extend(_scan_file(path, rel))
    return found


def test_no_eval_exec_or_shell_true() -> None:
    """INV-S-04: no eval/exec, no shell=True, list argv only."""
    assert find_violations() == []


PROBES: list[tuple[str, str, bool]] = [
    ("pkg/mod.py", "eval('1 + 1')\n", True),
    ("pkg/mod.py", "exec('x = 1')\n", True),
    ("pkg/mod.py", "compile('1', '<s>', 'eval')\n", True),
    ("pkg/mod.py", "import os\nos.system('ls')\n", True),
    ("pkg/mod.py", "import os\nos.popen('ls').read()\n", True),
    ("pkg/mod.py", "import subprocess\nsubprocess.run('ls -l', shell=True)\n", True),
    ("pkg/mod.py", "import subprocess\nsubprocess.run('ls -l')\n", True),
    (
        "ci/gates/check_x.py",
        "import subprocess\nsubprocess.run(['git', 'diff', f'{base}...HEAD'])\n",
        False,
    ),
    (
        "ci/gates/check_x.py",
        "import subprocess\nsubprocess.run([sys.executable, str(path)])\n",
        False,
    ),
    ("pkg/mod.py", "import asyncio\nasyncio.create_subprocess_exec(*argv)\n", False),
    (
        "pkg/mod.py",
        "async def f():\n    import asyncio\n    await asyncio.create_subprocess_exec('ls')\n",
        True,
    ),
    ("pkg/mod.py", "import re\nre.compile('a+')\n", False),
    ("ci/gates/check_x.py", "import subprocess\nsubprocess.run(['git', 'x'])\n", False),
    ("src/pumpgrok/cli.py", "import subprocess\nsubprocess.run(['git', 'x'])\n", False),
    ("src/pumpgrok/other.py", "import subprocess\nsubprocess.run(['git', 'x'])\n", True),
]
@pytest.mark.parametrize(("rel", "source", "flagged"), PROBES)
def test_probe_is_classified(tmp_path: Path, rel: str, source: str, flagged: bool) -> None:
    package = tmp_path / rel
    package.parent.mkdir(parents=True, exist_ok=True)
    package.write_text(source, encoding="utf-8")
    allowed = {"ci/gates/check_x.py", "src/pumpgrok/cli.py"}
    found = _scan_file(package, rel, allowed)
    assert bool(found) is flagged, found

def test_smuggled_eval_in_scratch_copy_is_caught(tmp_path: Path) -> None:
    package = tmp_path / "pumpgrok" / "core" / "ids.py"
    package.parent.mkdir(parents=True, exist_ok=True)
    package.write_text("import os\nos.system('id')\n", encoding="utf-8")
    found = _scan_file(package, "core/ids.py")
    assert any(entry.startswith("core/ids.py:") for entry in found), found
