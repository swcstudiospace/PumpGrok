"""The gateway binds the same desk paths as the CLI when it runs from the repo root (finding 3).

The check runs ``main()`` in-process from the repo root and captures the ``GatewayConfig`` it
would serve, with ``create_server`` replaced by a recorder. Nothing is bound and no data is
written.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from desk_gateway import __main__ as entry
from pumpgrok.ledger.paths import DESK_DATA_DIR, PAPER_LEDGER_PATH

REPO_ROOT = Path(__file__).resolve().parents[3]


class _Captured(Exception):
    """Raised by the recorder to stop ``main()`` before any server is bound."""


def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith(("PUMPGROK_", "DESK_GATEWAY_")):
            monkeypatch.delenv(name)


def test_entrypoint_binds_root_desk_paths_from_repo_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clean_env(monkeypatch)
    monkeypatch.chdir(REPO_ROOT)
    captured: list[Any] = []

    def record(config: Any, **_kwargs: Any) -> None:
        captured.append(config)
        raise _Captured

    monkeypatch.setattr(entry, "create_server", record)
    with pytest.raises(_Captured):
        entry.main()
    config = captured[0]
    assert config.data_dir == REPO_ROOT / DESK_DATA_DIR
    assert config.ledger_path == REPO_ROOT / PAPER_LEDGER_PATH
