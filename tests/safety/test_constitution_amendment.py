"""Amendment oracle: 2026-10-25 constitution wording matches frozen text (UPG-06).

Compares the amended clauses in rules/pumpgrok-team.mdc (clauses 2 and 8
with the ten-role correction), agents/risk.md clauses 3 and 10,
docs/RISK_POLICY.md row 8 and section 2.4, and .planning/PROJECT.md BLIND
constraint against tests/safety/amendment_2026_10_25_frozen.txt, then proves
every verbatim copy matches: clause 8 is identical in rules and RISK_POLICY,
the clause 10 exception is present in every regenerated seat file, and only
the RISK seat carries the amended clause 3.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN = REPO_ROOT / "tests" / "safety" / "amendment_2026_10_25_frozen.txt"
RULES = REPO_ROOT / "rules" / "pumpgrok-team.mdc"
SKILL = REPO_ROOT / "skills" / "desk-operating-model" / "SKILL.md"
CORE = REPO_ROOT / "prompts" / "_shared" / "core-directives.xml"
RISK_AGENT = REPO_ROOT / "agents" / "risk.md"
RISK_POLICY = REPO_ROOT / "docs" / "RISK_POLICY.md"
PROJECT = REPO_ROOT / ".planning" / "PROJECT.md"
SEATS = ("chief", "exit", "journal", "risk", "rug", "scout", "shill", "signal", "sniper", "whale")
EXPECTED_SECTIONS = (
    "rules-line-8-roles",
    "rules-signal-bullet",
    "rules-journal-bullet",
    "rules-clause-2-append",
    "rules-clause-8",
    "clause-8-body",
    "skill-l24",
    "skill-l31",
    "skill-l32-roles",
    "core-clause-10",
    "core-clause-10-exception",
    "risk-clause-3",
    "risk-policy-row-8-quote",
    "risk-policy-2.4-heading",
    "risk-policy-2.4-paragraph",
    "project-blind-constraint",
    "project-strategy-row",
)

OLD_CLAUSE_3 = (
    "3. Human must explicitly approve the exact ticket (token CA + size + max slippage)"
    " for every spend until the human writes a higher autonomy level in the journal."
)


def _load_frozen() -> dict[str, str]:
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if current is not None:
            sections[current] = "\n".join(buf)

    for raw in FROZEN.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            flush()
            current = None
            buf = []
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            flush()
            current = stripped[1:-1]
            buf = []
            continue
        if current is None:
            raise AssertionError(f"frozen oracle content outside section: {raw!r}")
        buf.append(raw)
    flush()
    return sections


def _frozen() -> dict[str, str]:
    sections = _load_frozen()
    missing = [name for name in EXPECTED_SECTIONS if name not in sections]
    assert not missing, f"frozen oracle missing sections: {missing}"
    return sections


def _rule_clause(prefix: str) -> str:
    for line in RULES.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line
    raise AssertionError(f"rules file has no line starting with {prefix!r}")


def test_frozen_oracle_covers_every_amended_clause() -> None:
    sections = _frozen()
    assert sections["clause-8-body"] in sections["rules-clause-8"]
    assert sections["core-clause-10-exception"] in sections["core-clause-10"]


def test_rules_ten_role_correction_matches_frozen() -> None:
    sections = _frozen()
    assert _rule_clause("Use the ten definitions") == sections["rules-line-8-roles"]
    text = RULES.read_text(encoding="utf-8")
    assert sections["rules-signal-bullet"] in text
    assert sections["rules-journal-bullet"] in text


def test_rules_clause_2_append_matches_frozen() -> None:
    sections = _frozen()
    clause2 = _rule_clause("2. **Human approval required.**")
    assert clause2.endswith(sections["rules-clause-2-append"]), clause2


def test_rules_clause_8_matches_frozen() -> None:
    sections = _frozen()
    assert _rule_clause("8. **No live strategies") == sections["rules-clause-8"]


def test_skill_constitution_copies_match_frozen() -> None:
    sections = _frozen()
    lines = SKILL.read_text(encoding="utf-8").splitlines()
    assert sections["skill-l24"] in lines, "SKILL.md L24 wording drifted"
    assert sections["skill-l31"] in lines, "SKILL.md L31 wording drifted"
    assert sections["skill-l32-roles"] in lines, "SKILL.md L32 roles drifted"


def _core_section_text(section_id: str) -> str:
    root = ET.parse(CORE).getroot()
    for section in root.findall("section"):
        if section.get("id") == section_id:
            return section.text or ""
    raise AssertionError(f"core-directives.xml has no section {section_id!r}")


def test_core_clause_10_matches_frozen() -> None:
    sections = _frozen()
    for section_id in ("security-constitution", "security-constitution-risk"):
        matches = [
            line
            for line in _core_section_text(section_id).splitlines()
            if line.startswith("10. If you cannot obtain live data")
        ]
        assert len(matches) == 1, (section_id, matches)
        assert matches[0] == sections["core-clause-10"], section_id


def test_clause_10_exception_in_every_seat_file() -> None:
    sections = _frozen()
    exception = sections["core-clause-10-exception"]
    for seat in SEATS:
        text = (REPO_ROOT / "agents" / f"{seat}.md").read_text(encoding="utf-8")
        assert exception in text, f"agents/{seat}.md lost the clause 10 exception"
    risk_lines = [
        line
        for line in RISK_AGENT.read_text(encoding="utf-8").splitlines()
        if line.startswith("10. If you cannot obtain live data")
    ]
    assert len(risk_lines) == 1, risk_lines
    assert risk_lines[0] == sections["core-clause-10"]


def test_clause_8_identical_across_rules_and_risk_policy() -> None:
    sections = _frozen()
    body = sections["clause-8-body"]
    rules_text = RULES.read_text(encoding="utf-8")
    policy_text = RISK_POLICY.read_text(encoding="utf-8")
    assert body in rules_text, "clause 8 body missing from rules file"
    assert body in policy_text, "clause 8 body missing from RISK_POLICY row 8"
    row8 = next(line for line in policy_text.splitlines() if line.startswith("| 8 |"))
    quote = row8.split("|")[2].strip()
    assert quote == sections["risk-policy-row-8-quote"], quote
    assert quote == f'"No live strategies and no return claims. {body}"'


def test_risk_policy_section_24_matches_frozen() -> None:
    sections = _frozen()
    lines = RISK_POLICY.read_text(encoding="utf-8").splitlines()
    assert sections["risk-policy-2.4-heading"] in lines
    assert sections["risk-policy-2.4-paragraph"] in lines


def test_project_blind_constraint_and_strategy_row_match_frozen() -> None:
    sections = _frozen()
    lines = PROJECT.read_text(encoding="utf-8").splitlines()
    assert any(sections["project-blind-constraint"] in line for line in lines), (
        "PROJECT.md BLIND constraint drifted"
    )
    assert f"- {sections['project-strategy-row']}" in lines


def test_risk_clause_3_matches_frozen_amendment() -> None:
    sections = _frozen()
    risk_lines = RISK_AGENT.read_text(encoding="utf-8").splitlines()
    assert sections["risk-clause-3"] in risk_lines
    assert OLD_CLAUSE_3 not in risk_lines, "agents/risk.md kept the shared clause 3"


def test_other_seats_keep_shared_clause_3() -> None:
    new_clause_3 = _frozen()["risk-clause-3"]
    for seat in SEATS:
        if seat == "risk":
            continue
        lines = (REPO_ROOT / "agents" / f"{seat}.md").read_text(encoding="utf-8").splitlines()
        assert OLD_CLAUSE_3 in lines, f"agents/{seat}.md lost the shared clause 3"
        assert new_clause_3 not in lines, f"agents/{seat}.md gained the risk clause 3"
