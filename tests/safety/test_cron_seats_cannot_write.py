"""R63/B2 cron-seat guard: cron-owned seats cannot resolve paper-write (safety).

A cron-owned invocation of sniper or exit resolves with
max_side_effect=READ. Under that ceiling no paper-write tool resolves
(reason exceeds_requested_max); the same resolution with PAPER_WRITE
succeeds (non-vacuity: the refusal comes from the ceiling, not the roster).
The CLI half pins R63 end to end: a paper buy with a well-formed but
unknown approval_id exits 1 and writes no OrderPlaced row, regardless of
--seat; a missing approval_id is rejected by argparse (exit 1).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from pumpgrok.core.errors import PermissionDenied
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.ledger.store import LedgerStore
from registry_harness import build_full_registry, resolve

TICKET = "SOL-20260101-001"
MINT = "So11111111111111111111111111111111111111112"
APPROVAL = "apr-01ARZ3NDEKTSV4RRFFQ69G5FAV"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip PUMPGROK_* and secret-shaped names so each test sets exactly what it needs."""
    import os

    for name in list(os.environ):
        if name.startswith("PUMPGROK_") or any(
            frag in name.lower()
            for frag in ("secret", "password", "token", "api_key", "auth", "credential")
        ):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def root_handlers() -> Iterator[None]:
    """main() installs a handler bound to the test's stderr; remove it afterwards."""
    import logging

    root = logging.getLogger()
    level = root.level
    yield None
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:  # pragma: no cover - best effort cleanup
            pass
    root.setLevel(level)


def _trade_flags(seat: str, approval: str | None = APPROVAL) -> list[str]:
    flags = [
        "paper",
        "buy",
        "--ticket",
        TICKET,
        "--mint",
        MINT,
        "--size-sol",
        "0.5",
        "--slippage-bps",
        "100",
    ]
    if approval is not None:
        flags += ["--approval-id", approval]
    return flags + ["--seat", seat]


def test_cron_owned_seats_cannot_resolve_paper_write(tmp_path: Path) -> None:
    reg, _, manifests = build_full_registry(tmp_path)
    paper_write_names = [
        name
        for name in reg.names()
        if reg.spec(name).side_effect is SideEffect.PAPER_WRITE
    ]
    assert paper_write_names, "registry must hold paper-write tools or the guard is vacuous"
    for seat_id in ("bot-04-sniper", "bot-06-exit"):
        bot = manifests[seat_id]
        for name in paper_write_names:
            with pytest.raises(PermissionDenied):
                resolve(reg, bot, name, max_side_effect=SideEffect.READ)
        # read tools still resolve under the READ ceiling (ceiling, not roster)
        assert resolve(reg, bot, "desk.brief", max_side_effect=SideEffect.READ)


def test_cron_ceiling_refusal_reason_is_requested_max(tmp_path: Path) -> None:
    reg, _, manifests = build_full_registry(tmp_path)
    for seat_id in ("bot-04-sniper", "bot-06-exit"):
        bot = manifests[seat_id]
        granted = [
            name
            for name in reg.names()
            if reg.spec(name).side_effect is SideEffect.PAPER_WRITE
            and bot.grant_for(name) is not None
        ]
        assert granted, f"{seat_id} must hold paper-write grants or the test is vacuous"
        for name in granted:
            with pytest.raises(PermissionDenied) as excinfo:
                resolve(reg, bot, name, max_side_effect=SideEffect.READ)
            assert excinfo.value.fields["reason"] == "exceeds_requested_max", name


def test_paper_write_resolves_with_paper_write_ceiling_non_vacuous(
    tmp_path: Path,
) -> None:
    reg, _, manifests = build_full_registry(tmp_path)
    for seat_id in ("bot-04-sniper", "bot-06-exit"):
        resolved = resolve(
            reg, manifests[seat_id], "exec.place", max_side_effect=SideEffect.PAPER_WRITE
        )
        assert resolved.spec.name == "exec.place"


@pytest.mark.parametrize("seat", ["sniper", "exit", "desk"])
def test_cli_paper_buy_without_valid_approval_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seat: str
) -> None:
    from pumpgrok.cli import main
    monkeypatch.chdir(tmp_path)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    assert store.count() == 0
    code = main(_trade_flags(seat))
    assert code == 1
    assert store.count() == 0, "rejected paper buy must write no OrderPlaced row"
    store.close()


def test_cli_paper_buy_missing_approval_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from pumpgrok.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(_trade_flags("desk", approval=None)) == 1
    assert "approval" in capsys.readouterr().err.lower()
