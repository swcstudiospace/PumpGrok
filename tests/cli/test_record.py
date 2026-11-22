"""Record/replay CLI verbs: sealed datasets and byte-identical reruns (REC-03)."""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.cli import main as cli_main
from pumpgrok.cli.serve_feed import FeedServer, health_probe
from pumpgrok.replay.fixtures import load_dataset

SMOKE = Path("tests/fixtures/replay/smoke")
FROM_TS = "2026-01-01T00:00:00.000Z"
TO_TS = "2026-01-01T00:00:01.250Z"


def test_record_seals_dataset(tmp_path: Path) -> None:
    target = tmp_path / "recorded"
    code = cli_main(["run", "--record", str(target), "--replay", str(SMOKE)])
    assert code == 0
    dataset = load_dataset(target)
    assert dataset.manifest.dataset == "recorded"
    assert len(dataset.events) == len(load_dataset(SMOKE).events)


def test_serve_health_probe(tmp_path: Path) -> None:

    server = FeedServer(SMOKE, 0)
    server.start()
    try:
        probe = health_probe(server.port)
        assert probe["ok"] is True
        assert probe["dataset"] == "smoke"
    finally:
        server.stop()


def test_replay_verbs_rerun_identical(tmp_path: Path) -> None:
    # trim: two runs produce byte-equal dataset trees
    first = tmp_path / "trim-a"
    second = tmp_path / "trim-b"
    args = ["replay", "trim", "--from", str(SMOKE), "--name", "trimmed"]
    tail = ["--from-ts", FROM_TS, "--to-ts", TO_TS]
    assert cli_main([*args, "--to", str(first), *tail]) == 0
    assert cli_main([*args, "--to", str(second), *tail]) == 0
    for name in ("manifest.json", "events.jsonl"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    # rebuild-ticks: two runs produce a byte-equal tick file
    ticks_a = tmp_path / "ticks-a.json"
    ticks_b = tmp_path / "ticks-b.json"
    base = ["replay", "rebuild-ticks", "--from", str(SMOKE)]
    assert cli_main([*base, "--to", str(ticks_a)]) == 0
    assert cli_main([*base, "--to", str(ticks_b)]) == 0
    assert ticks_a.read_bytes() == ticks_b.read_bytes()
    # import: byte-equal for the same external tick file
    ticks_file = tmp_path / "ticks.json"
    source = load_dataset(SMOKE)
    ticks_file.write_bytes(
        b"\n".join(
            json.dumps(event, sort_keys=True).encode() for event in source.events
        )
        + b"\n"
    )
    i1 = tmp_path / "imp-a"
    i2 = tmp_path / "imp-b"
    imp = ["replay", "import", "--source", str(ticks_file), "--name", "imported"]
    assert cli_main([*imp, "--to", str(i1)]) == 0
    assert cli_main([*imp, "--to", str(i2)]) == 0
    for name in ("manifest.json", "events.jsonl"):
        assert (i1 / name).read_bytes() == (i2 / name).read_bytes()
    load_dataset(i1)  # sealed, loadable
