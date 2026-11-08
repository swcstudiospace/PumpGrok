"""EventsSettings stays on cadence and a local sidecar path when TOML omits it."""

from __future__ import annotations

import os

import pytest

from pumpgrok.config.settings import load_settings


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_events_defaults_to_cadence_sidecar(clean_env: None) -> None:
    events = load_settings().events
    assert events.enabled is False
    assert events.allowlist == ()
    assert events.wake_mode == "cadence"
    assert events.sidecar_path == "var/desk/events.sqlite"
