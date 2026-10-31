"""Live refusal names the nine preconditions in R21 order (LIV-01, D-01, D-02).

A refused live start exits 3 and prints the LIVE GATE header, exactly one
line per precondition in PRECONDITION_IDS order carrying its number, id and
reason, plus the closing paper-mode line. ASCII only, no network use.
"""

from __future__ import annotations

import re
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
    # The count follows the default cap being met (live.notional_cap_lamports).
    assert err.startswith("LIVE GATE: refusing to start in mode=live.")
    total = len(PRECONDITION_IDS)
    header = re.match(
        rf"LIVE GATE: refusing to start in mode=live\. (\d+) of {total} preconditions unmet:\n",
        err,
    )
    assert header is not None
    unmet_rows = [line for line in err.splitlines() if line.startswith("  [ ] ")]
    assert int(header.group(1)) == len(unmet_rows)
    marked = [line for line in err.splitlines() if line.startswith("  [")]
    assert len(marked) == len(PRECONDITION_IDS)
    row = re.compile(r"  \[[ x]\] (\d+) (\S+) ")
    parsed = [row.match(line) for line in marked]
    assert all(parsed), marked
    ids = [m.group(2) for m in parsed if m]
    assert tuple(ids) == PRECONDITION_IDS
    numbers = [m.group(1) for m in parsed if m]
    assert numbers == [str(n) for n in range(1, len(PRECONDITION_IDS) + 1)]
    assert "mode=paper" in err
    assert "No transaction was attempted." in err
