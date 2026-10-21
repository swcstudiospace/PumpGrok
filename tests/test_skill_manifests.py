"""SKILL-002: all 35 skills parse to SkillManifest with granted tools (SC1 file 1).

B10 rule: a skill's bots list is the set of seats whose prompt skills list
contains it AND that hold every required_tools entry. Frontmatter is updated
to match, so this suite asserts required_tools are registered in the catalog
registry and granted by every listed bot, and that no skill may declare
LIVE_WRITE. Companion file: tests/test_bot_manifests.py (SC1 file 2).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, load_bot_manifests
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.skill import SkillManifest

from registry_harness import REPO_ROOT, ROSTERS_DIR, build_full_registry

SKILLS_DIR = REPO_ROOT / "skills"

# interfaces.md 3.2: the 12 new skills this phase delivers.
NEW_TWELVE = [
    "verification-receipts",
    "paper-broker",
    "replay-and-backtest",
    "live-gate-procedure",
    "kill-switch",
    "rpc-hygiene",
    "key-custody",
    "safety-scoring",
    "momentum-signals",
    "portfolio-ledger",
    "daily-report",
    "desk-doctor",
]

# interfaces.md 7.1: DataSource names required_data may reference (R44: never jupiter_lite).
KNOWN_DATA_SOURCES = {"pumpfun_rest", "pumpportal_ws", "jupiter", "solana_rpc", "xai_grok"}

# Phase 2 STRUCT-007 carryover plus R44: banned strings anywhere under skills/.
FORBIDDEN_SKILL_STRINGS = ("jupiter_lite", "lite-api", "--max-micro")

BODY_HEADINGS = ("## L1 - Summary", "## L2 - Method", "## Failure modes", "## References")


def _skill_dirs() -> list[Path]:
    return sorted(d for d in SKILLS_DIR.iterdir() if d.is_dir())


def _load(name: str) -> tuple[SkillManifest, str]:
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{name}: missing frontmatter"
    end = text.index("\n---\n", 4)
    manifest = SkillManifest.model_validate(yaml.safe_load(text[4:end]))
    return manifest, text[end + 5 :]


def _expand(tool: str, roster_names: list[str]) -> list[str]:
    if tool.endswith(".*"):
        prefix = tool[:-2]
        return sorted(n for n in roster_names if n == prefix or n.startswith(prefix + "."))
    return [tool]


def test_skill_count_is_35() -> None:
    assert len(_skill_dirs()) == 35, f"expected 35 skill dirs, got {len(_skill_dirs())}"


def test_new_twelve_skill_names_present() -> None:
    have = {d.name for d in _skill_dirs()}
    assert set(NEW_TWELVE) <= have, f"missing new skills: {set(NEW_TWELVE) - have}"


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_every_skill_frontmatter_parses(path: Path) -> None:
    manifest, body = _load(path.name)
    assert manifest.name == path.name
    assert 1 <= len(manifest.description) <= 1024
    assert body.count("\n") <= 350, f"{path.name}: body over 350 lines"
    for heading in BODY_HEADINGS:
        assert heading in body, f"{path.name}: body missing {heading!r}"


def test_desk_doctor_parses_with_matching_name() -> None:
    manifest, _ = _load("desk-doctor")
    assert manifest.name == "desk-doctor"


def test_desk_doctor_permissions_never_live() -> None:
    manifest, _ = _load("desk-doctor")
    assert manifest.permissions.max_side_effect != SideEffect.LIVE_WRITE


def test_desk_doctor_body_shape() -> None:
    _, body = _load("desk-doctor")
    assert body.count("\n") <= 350
    for heading in BODY_HEADINGS:
        assert heading in body, f"desk-doctor body missing {heading!r}"


def test_skill_required_tools_granted_to_its_bots(tmp_path: Path) -> None:
    reg, _, manifests = build_full_registry(tmp_path)
    registered = set(reg.names())
    for path in _skill_dirs():
        manifest, _ = _load(path.name)
        bots = list(EXPECTED_SEAT_IDS) if manifest.bots == ["all"] else manifest.bots
        assert bots, f"{path.name}: empty bots after 'all' expansion"
        for bot in bots:
            assert bot in manifests, f"{path.name}: unknown bot {bot!r}"
            roster_names = [g.name for g in manifests[bot].allowed_tools]
            for tool in manifest.required_tools:
                expanded = _expand(tool, roster_names)
                assert expanded, f"{path.name}: {tool!r} matches no {bot} roster tool"
                for name in expanded:
                    assert name in registered, f"{path.name}: {name!r} not registered"
                    assert manifests[bot].grant_for(name) is not None, (
                        f"{path.name}: {bot} holds no grant for {name!r}"
                    )


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_skill_permissions_never_live(path: Path) -> None:
    manifest, _ = _load(path.name)
    assert manifest.permissions.max_side_effect != SideEffect.LIVE_WRITE


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_skill_fixtures_exist(path: Path) -> None:
    manifest, _ = _load(path.name)
    for fixture in manifest.fixtures:
        assert (REPO_ROOT / fixture).exists(), f"{path.name}: fixture {fixture!r} missing"


@pytest.mark.parametrize("path", _skill_dirs(), ids=lambda p: p.name)
def test_skill_required_data_uses_known_sources(path: Path) -> None:
    manifest, _ = _load(path.name)
    for source in manifest.required_data:
        assert source in KNOWN_DATA_SOURCES, f"{path.name}: unknown data source {source!r}"


def test_no_forbidden_strings_in_skills() -> None:
    hits = []
    for md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        text = md.read_text(encoding="utf-8")
        for banned in FORBIDDEN_SKILL_STRINGS:
            if banned in text:
                hits.append(f"{md.parent.name}: {banned!r}")
    assert not hits, f"forbidden strings in skills/: {hits}"


def test_journal_ownership_string_present() -> None:
    text = (SKILLS_DIR / "desk-post-trade-review" / "SKILL.md").read_text(encoding="utf-8")
    assert "bot-09-journal" in text
