"""Machine-checked doc consistency (DOC-03, Phase 7 plan 07-05).

Asserts:
1. The four plugin manifests carry the same ``version`` as ``pyproject.toml``.
2. ``docs/VENDOR_PIN.md`` carries the historical provenance pin and a
   retirement statement. OVERRIDE-D applies: the Phase 4 tree is gone, so no
   snapshot marker is matched; the pin plus retirement wording is the record.
3. Every ``pumpgrok VERB`` command named in README.md, ARCHITECTURE.md,
   SETUP.md and skills/replay-and-backtest/SKILL.md exists in CLI ``--help``
   output. Help is collected via subprocess with ``--help`` flags only; no
   verb is ever executed.
4. None of the corrected contradiction strings appears in those four docs.

Deterministic, offline, no network, no full suite.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"

PLUGIN_MANIFESTS = (
    REPO_ROOT / "plugin.json",
    REPO_ROOT / ".claude-plugin" / "plugin.json",
    REPO_ROOT / ".cursor-plugin" / "plugin.json",
    REPO_ROOT / ".grok-plugin" / "plugin.json",
)

VENDOR_PIN_DOC = REPO_ROOT / "docs" / "VENDOR_PIN.md"
HISTORICAL_PIN = "409e74c905faa0e9de42e918efe2c604f206856e"

COMMAND_DOCS = (
    REPO_ROOT / "README.md",
    REPO_ROOT / "ARCHITECTURE.md",
    REPO_ROOT / "SETUP.md",
    REPO_ROOT / "skills" / "replay-and-backtest" / "SKILL.md",
)

# A path such as /workspace/pumpgrok must not read as a VERB command, so a
# VERB match rejects a pumpgrok token preceded by a slash or word character.
VERB_RE = re.compile(r"(?<![/\w-])pumpgrok\s+([A-Za-z][A-Za-z0-9_-]*)")

BANNED_FRAGMENTS = (
    "eight-role",
    "Eight specialist",
    "--rpc",
    "Version 1.0.0",
    "same code path as live paper",
    "identical path",
    "no server, queue, or daemon",
)


def _pyproject_version() -> str:
    with PYPROJECT.open("rb") as handle:
        data = tomllib.load(handle)
    return str(data["project"]["version"])


def test_plugin_manifest_versions_match_pyproject() -> None:
    expected = _pyproject_version()
    for manifest in PLUGIN_MANIFESTS:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        name = manifest.relative_to(REPO_ROOT).as_posix()
        assert payload.get("version") == expected, (
            f"{name} version {payload.get('version')!r} != pyproject version {expected!r}"
        )


def test_vendor_pin_carries_pin_and_retirement() -> None:
    text = VENDOR_PIN_DOC.read_text(encoding="utf-8")
    assert HISTORICAL_PIN in text, (
        "docs/VENDOR_PIN.md no longer carries the historical provenance pin"
    )
    assert "retir" in text.lower(), (
        "docs/VENDOR_PIN.md carries no retirement statement"
    )


def _help_text(argv: list[str]) -> str:
    exe = shutil.which("pumpgrok")
    if exe is not None:
        cmd = [exe, *argv]
    else:
        shim = "import sys; from pumpgrok.cli import main; sys.exit(main())"
        cmd = [sys.executable, "-c", shim, *argv]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120, cwd=REPO_ROOT
    )
    assert proc.returncode == 0, f"help call {cmd} exited {proc.returncode}"
    return proc.stdout


def _documented_verbs() -> set[str]:
    verbs: set[str] = set()
    for doc in COMMAND_DOCS:
        verbs.update(VERB_RE.findall(doc.read_text(encoding="utf-8")))
    return verbs


def test_documented_verbs_exist_in_cli_help() -> None:
    top_help = _help_text(["--help"])
    tools_help = _help_text(["tools", "--help"])
    combined = top_help + "\n" + tools_help
    verbs = _documented_verbs()
    assert verbs, "no pumpgrok VERB commands found in the four docs"
    missing = sorted(verb for verb in verbs if verb not in combined)
    assert not missing, f"docs name verbs missing from CLI help: {missing}"


def test_no_contradiction_strings_in_docs() -> None:
    for doc in COMMAND_DOCS:
        lowered = doc.read_text(encoding="utf-8").lower()
        for fragment in BANNED_FRAGMENTS:
            assert fragment.lower() not in lowered, (
                f"{doc.name} still carries {fragment!r}"
            )
