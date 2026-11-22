"""Gate self-test: exit 0 on silence, non-zero with a synthetic event."""

import subprocess
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[1] / "gates" / "check_idle_grok.py"


def test_gate_exits_zero_on_silence() -> None:
    if not GATE.exists():
        # Trusted-overlay semantics: gate-self-test overlays ci/gates/ from base
        # main (anti-tamper), so a gate introduced on this branch is absent from
        # the overlaid tree. Skip here; the file exists on main post-merge, where
        # this test runs fully.
        pytest.skip("check_idle_grok.py absent under trusted ci/gates overlay from base main")
    proc = subprocess.run(
        ["uv", "run", "python", "ci/gates/check_idle_grok.py"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "calls=0" in proc.stdout
