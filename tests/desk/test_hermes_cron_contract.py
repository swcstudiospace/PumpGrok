"""Hermes cron can never trade (INV-S-10).

Asserts over ``hermes/cron/jobs.yaml`` and ``hermes/profiles.yaml``:

- ``forbidden_owners`` keeps ``[sniper, exit]`` and ``forbidden_actions``
  contains ``send_transaction``, ``sign``, ``store_key``,
  ``raise_engagement``;
- every job's effective ``engagement_required`` is a subset of
  ``[research, paper]`` (job-level value or the file defaults);
- ``profiles.yaml`` ``forbidden_env_keys`` is non-empty and
  ``copy_provider_env`` is ``allowlist-only``;
- every cron prompt body contains the ``[SILENT]`` gate;
- no instruction surface under ``skills/``, ``agents/``, ``hermes/``,
  ``SETUP.md``, ``README.md`` or ``ARCHITECTURE.md`` contains
  ``micro-live`` (R16 markdown quarantine).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
JOBS = REPO_ROOT / "hermes" / "cron" / "jobs.yaml"
PROFILES = REPO_ROOT / "hermes" / "profiles.yaml"
PROMPTS = REPO_ROOT / "hermes" / "cron" / "prompts"

ENGAGEMENT_LEVELS = frozenset({"research", "paper"})

REQUIRED_FORBIDDEN_ACTIONS = frozenset(
    {"send_transaction", "sign", "store_key", "raise_engagement"}
)

INSTRUCTION_SURFACES = (
    "skills",
    "agents",
    "hermes",
    "SETUP.md",
    "README.md",
    "ARCHITECTURE.md",
)


def _jobs_doc() -> dict:
    return yaml.safe_load(JOBS.read_text(encoding="utf-8"))


def test_cron_never_trades() -> None:
    """INV-S-10: cron owners, actions, engagement and prompts are trade-free."""
    assert JOBS.is_file(), "hermes/cron/jobs.yaml is missing"
    assert PROFILES.is_file(), "hermes/profiles.yaml is missing"
    doc = _jobs_doc()
    assert list(doc.get("forbidden_owners", [])) == ["sniper", "exit"]
    assert REQUIRED_FORBIDDEN_ACTIONS <= set(doc.get("forbidden_actions", []))

    defaults = doc.get("defaults", {})
    default_engagement = set(defaults.get("engagement_required", []))
    assert default_engagement <= ENGAGEMENT_LEVELS, default_engagement
    problems: list[str] = []
    for job in doc.get("jobs", []):
        engagement = set(job.get("engagement_required", default_engagement))
        if not engagement <= ENGAGEMENT_LEVELS:
            problems.append(f"{job.get('id')}: engagement {sorted(engagement)}")
        if str(job.get("owner", "")) in ("sniper", "exit"):
            problems.append(f"{job.get('id')}: forbidden owner {job.get('owner')}")
    assert problems == []

    profiles = yaml.safe_load(PROFILES.read_text(encoding="utf-8"))
    forbidden = profiles.get("isolation", {}).get("forbidden_env_keys", [])
    assert forbidden, "forbidden_env_keys is empty"
    assert profiles.get("isolation", {}).get("copy_provider_env") == "allowlist-only"

    prompts = sorted(PROMPTS.glob("*.md"))
    assert prompts, "no cron prompts found"
    missing = [p.name for p in prompts if "[SILENT]" not in p.read_text(encoding="utf-8")]
    assert missing == [], f"prompts without the [SILENT] gate: {missing}"


def test_no_micro_live_in_instruction_surfaces() -> None:
    """INV-S-10: the R16 markdown quarantine holds."""
    offenders: list[str] = []
    for surface in INSTRUCTION_SURFACES:
        root = REPO_ROOT / surface
        if root.is_file():
            haystacks = [root]
        elif root.is_dir():
            haystacks = sorted(p for p in root.rglob("*.md") if ".venv" not in p.parts)
        else:
            continue
        for path in haystacks:
            if "micro-live" in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


@pytest.mark.parametrize(
    ("job", "owner", "bad"),
    [
        ({"id": "x", "owner": "scout"}, "scout", False),
        ({"id": "x", "owner": "sniper"}, "sniper", True),
        ({"id": "x", "owner": "exit"}, "exit", True),
    ],
)
def test_owner_is_classified(job: dict, owner: str, bad: bool) -> None:
    assert (owner in ("sniper", "exit")) is bad
