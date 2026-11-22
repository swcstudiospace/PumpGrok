"""HOST-02: compose mounts one named volume at the state directory."""

from __future__ import annotations

from pathlib import Path


def test_compose_mounts_named_volume_for_state() -> None:
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "volumes:" in text
    assert "pumpgrok-state" in text
    assert ":/app/var" in text or ":/app/state" in text


def test_no_host_bind_mount_for_state() -> None:
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "./var:/app/var" not in text
    assert "../var:" not in text


def test_no_hosted_run_until_hard07() -> None:
    # Honest precondition: the compose desk service still runs the fixture
    # replay command; no hosted live run starts until HARD-07 passes.
    text = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "tests/fixtures/replay/smoke" in text
    assert "--serve" in text
