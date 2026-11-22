"""HOST-06: failed final writes exit non-zero and are recorded."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.supervisor.health_server import shutdown_exit_code


def attempt_final_write(path: str, payload: dict | None) -> tuple[int, dict]:
    """Simulate a final health write; returns (exit_code, final_output)."""
    try:
        if payload is None:
            raise OSError("simulated write failure")
        Path(path).write_text(str(payload), encoding="utf-8")
    except OSError as exc:
        return shutdown_exit_code(True), {"shutdown": "failed", "error": type(exc).__name__}
    return shutdown_exit_code(False), {"shutdown": "ok"}


def test_failed_write_exits_non_zero(tmp_path: Path) -> None:
    code, out = attempt_final_write(str(tmp_path / "health.json"), None)
    assert code != 0
    assert out["shutdown"] == "failed"


def test_successful_write_exits_zero(tmp_path: Path) -> None:
    target = tmp_path / "health.json"
    code, out = attempt_final_write(str(target), {"ok": True})
    assert code == 0
    assert out["shutdown"] == "ok"
    assert target.exists()


def test_failure_recorded_in_output_shape() -> None:
    code, out = attempt_final_write("/nonexistent-dir/health.json", {"ok": True})
    assert code != 0
    assert "error" in out
