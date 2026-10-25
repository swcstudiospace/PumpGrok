"""Live refusal names the nine preconditions in R21 order (LIV-01, D-01, D-02).

A refused live start exits 3 and prints the LIVE GATE header, exactly one
line per precondition in PRECONDITION_IDS order carrying its number, id and
reason, plus the closing paper-mode line. ASCII only, no network use.
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.cli import EXIT_LIVE, main
from pumpgrok.execution.live.live_gate import PRECONDITION_IDS


def test_live_refusal_lists_nine_preconditions_in_order(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """LIV-01: stderr names all nine ids in R21 order, one line each."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PUMPGROK_LIVE_ENABLE", raising=False)
    code = main(["run", "--mode", "live", "--once"])
    assert code == EXIT_LIVE
    err = capsys.readouterr().err
    assert err.startswith("LIVE GATE: refusing to start in mode=live. 9 of 9")
    marked = [line for line in err.splitlines() if line.startswith("  [")]
    assert len(marked) == len(PRECONDITION_IDS)
    ids = [line.split()[3] for line in marked]
    assert tuple(ids) == PRECONDITION_IDS
    numbers = [line.split()[2] for line in marked]
    assert numbers == [str(n) for n in range(1, len(PRECONDITION_IDS) + 1)]
    assert "mode=paper" in err
    assert "No transaction was attempted." in err
