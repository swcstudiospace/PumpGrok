"""SKILL-002 tracer: desk-doctor parses to SkillManifest (SKILL-001 shape proof).

Scaffold for tests/test_skill_manifests.py. The full 35-skill suite lands in
the Task 2 RED commit; this file proves the SkillManifest shape first.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.skill import SkillManifest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str) -> tuple[SkillManifest, str]:
    text = (REPO_ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{name}: missing frontmatter"
    end = text.index("\n---\n", 4)
    manifest = SkillManifest.model_validate(yaml.safe_load(text[4:end]))
    return manifest, text[end + 5 :]


def test_desk_doctor_parses_with_matching_name() -> None:
    manifest, _ = _load("desk-doctor")
    assert manifest.name == "desk-doctor"


def test_desk_doctor_permissions_never_live() -> None:
    manifest, _ = _load("desk-doctor")
    assert manifest.permissions.max_side_effect != SideEffect.LIVE_WRITE


def test_desk_doctor_body_shape() -> None:
    _, body = _load("desk-doctor")
    assert body.count("\n") <= 350
    for heading in ("## L1 - Summary", "## L2 - Method", "## Failure modes", "## References"):
        assert heading in body, f"desk-doctor body missing {heading!r}"
