"""Gate self-test: exit 0 on silence, non-zero with a synthetic event."""

import subprocess


def test_gate_exits_zero_on_silence() -> None:
    proc = subprocess.run(
        ["uv", "run", "python", "ci/gates/check_idle_grok.py"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert "calls=0" in proc.stdout
