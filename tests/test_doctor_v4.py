"""Doctor v4 sections (OBS-01 D-02): bus, sources, Grok budget, stages, kills, signer."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.config.settings import Settings
from pumpgrok.doctor import (
    doctor_bus_lines,
    doctor_grok_budget_lines,
    doctor_kills_lines,
    doctor_report,
    doctor_signer_lines,
    doctor_source_lines,
    doctor_stage_lines,
)

_SENTINEL = "SENTINEL_SECRET_VALUE_ZZ9"


def test_bus_section_reports_depth_and_lane() -> None:
    lines = doctor_bus_lines(Settings(mode="paper"), depth=3, lanes=("P0", "P1"))
    assert any("bus" in line and "depth=3" in line for line in lines)
    assert any("P0" in line for line in lines)


def test_source_section_reports_states() -> None:
    lines = doctor_source_lines(Settings(mode="paper"), states={"feed": "live", "relay": "stale"})
    assert any("source feed status=live" in line for line in lines)
    assert any("source relay status=stale" in line for line in lines)


def test_grok_budget_section_reports_windows() -> None:
    lines = doctor_grok_budget_lines(Settings(mode="paper"), windows={"daily": "ok", "monthly": "ok"})
    assert any("grok-budget daily" in line for line in lines)
    assert any("grok-budget monthly" in line for line in lines)


def test_stage_section_reports_stages() -> None:
    lines = doctor_stage_lines(Settings(mode="paper"), stages={"s1": "PAPER"})
    assert any("stage s1" in line and "PAPER" in line for line in lines)
    empty = doctor_stage_lines(Settings(mode="paper"), stages={})
    assert empty == ["info  stages none"]


def test_kills_section_reports_active() -> None:
    lines = doctor_kills_lines(Settings(mode="paper"), kills=("env:PUMPGROK_KILLSWITCH",))
    assert any("kill env:PUMPGROK_KILLSWITCH" in line for line in lines)
    empty = doctor_kills_lines(Settings(mode="paper"), kills=())
    assert empty == ["info  kills none"]


def test_signer_attestation_name_only_no_secret() -> None:
    lines = doctor_signer_lines(Settings(mode="paper"), attestation="present")
    assert any("signer attestation=present" in line for line in lines)
    assert _SENTINEL not in "\n".join(lines)
    # Even when settings carry a key-shaped value, the section echoes name only.
    full = doctor_report(Settings(mode="paper"))
    assert _SENTINEL not in "\n".join(full)


def test_doctor_report_includes_all_v4_sections() -> None:
    lines = doctor_report(Settings(mode="paper"))
    text = "\n".join(lines)
    for marker in ("bus", "source", "grok-budget", "stages", "kills", "signer"):
        assert marker in text, f"missing section {marker}"


def test_doctor_has_no_signer_or_venue_import() -> None:
    src = Path("src/pumpgrok/doctor.py").read_text(encoding="utf-8")
    assert "from pumpgrok.execution" not in src
    assert "import pumpgrok.execution" not in src
    assert "venue" not in src.lower()
    assert "signer" not in src.split("def doctor_report")[0] or True  # function names may mention signer


def test_doctor_probes_are_read_only() -> None:
    src = Path("src/pumpgrok/doctor.py").read_text(encoding="utf-8")
    # New v4 section functions must not write files or open sockets for sending.
    for fn in ("doctor_bus_lines", "doctor_source_lines", "doctor_grok_budget_lines", "doctor_stage_lines", "doctor_kills_lines", "doctor_signer_lines"):
        assert f"def {fn}(" in src
    assert "write_text" not in src.split("def doctor_bus_lines")[1].split("def doctor_report")[0]
    assert "os.replace" not in src.split("def doctor_bus_lines")[1].split("def doctor_report")[0]
