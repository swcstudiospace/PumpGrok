"""``scripts/measure_grok_calls.py``: the before/after Grok call measurement and its gate.

Every test builds its own small dataset under ``tmp_path``, so the tests never depend on the
shipped evidence-50 or soak-3d fixtures, except the soak-3d regression test. Admission and request
keys come from the production prefilter, gateway and narrative agent; nothing here fakes a count.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from pumpgrok.config.settings import GrokSettings
from pumpgrok.engine.agents.narrative import NarrativeAgent
from pumpgrok.grok.gateway import GrokGateway, _request_key, prefilter, sanitize
from pumpgrok.replay.clock import FixtureClock, parse_ts_utc

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "measure_grok_calls.py"
_SPEC = importlib.util.spec_from_file_location("measure_grok_calls", SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
measure_mod = importlib.util.module_from_spec(_SPEC)
# Registered before exec so the script's dataclasses can resolve their module.
sys.modules[_SPEC.name] = measure_mod
_SPEC.loader.exec_module(measure_mod)

BASE_TS = 1767225600.0  # 2026-01-01T00:00:00Z
CADENCE_S = 90
SOAK_DATASET = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "replay" / "soak-3d-tokens"
)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _row(index: int, *, ts: float, buyers: int = 10) -> dict[str, Any]:
    """A candidate tick that the real prefilter admits unless ``buyers`` is too low."""
    return {
        "ts_utc": _iso(ts),
        "kind": "tick",
        "mint": f"{index:044d}",
        "name": f"Token {index}",
        "image_uri": "https://example.invalid/token.png",
        "created_ts_utc": _iso(ts - 600),
        "first_trade_ts_utc": _iso(ts - 300),
        "unique_buyers": buyers,
        "prerank": "0.90",
    }


def _ten_rows() -> list[dict[str, Any]]:
    """Ten candidates: indices 0-3 admitted, 4-9 rejected for too few buyers."""
    return [
        _row(index, ts=BASE_TS + CADENCE_S * index, buyers=10 if index < 4 else 2)
        for index in range(10)
    ]


def _llm_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One recorded ``ok`` outcome per distinct request the real prefilter admits."""
    clock = FixtureClock(start=parse_ts_utc(rows[0]["ts_utc"]))
    agent = NarrativeAgent(GrokSettings(), gateway=cast(GrokGateway, None), clock=clock)
    records: dict[str, dict[str, Any]] = {}
    last_admitted: dict[str, float] = {}
    for number, row in enumerate(rows, 1):
        clock.advance_to(parse_ts_utc(row["ts_utc"]))
        request = measure_mod.request_for_row(
            number, row, agent=agent, clock=clock, last_admitted=last_admitted
        )
        if not prefilter(request.candidate, now=clock.now()).admit:
            continue
        last_admitted[row["mint"]] = clock.now()
        key = _request_key(request, sanitize(request.text))
        records.setdefault(
            key,
            {
                "request_hash": key,
                "outcome": "ok",
                "latency_s": 1.2,
                "response": {"model": request.model, "content": "{}"},
            },
        )
    return list(records.values())


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return "".join(json.dumps(row) + "\n" for row in rows).encode("utf-8")


def _write_dataset(
    root: Path,
    rows: list[dict[str, Any]],
    llm_rows: list[dict[str, Any]] | None,
) -> Path:
    root.mkdir(parents=True)
    files = {"events.jsonl": _jsonl(rows)}
    if llm_rows is not None:
        files["llm.jsonl"] = _jsonl(llm_rows)
    for name, data in files.items():
        (root / name).write_bytes(data)
    manifest = {
        "dataset": "unit",
        "provenance": "synthetic",
        "recorded_from_utc": _iso(BASE_TS),
        "recorded_to_utc": _iso(BASE_TS + CADENCE_S * len(rows)),
        "seed_hint": 1,
        "sources": {},
        "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()},
        "notes": "unit test dataset",
    }
    (root / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    return root


def _dataset(tmp_path: Path, rows: list[dict[str, Any]]) -> Path:
    return _write_dataset(tmp_path / "unit", rows, _llm_rows(rows))


def test_missing_dataset_fails_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = measure_mod.main(["--dataset", str(tmp_path / "absent"), "--max-ratio", "0.2"])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "dataset directory not found" in captured.err


def test_zero_denominator_fails_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [{"ts_utc": _iso(BASE_TS), "kind": "trade", "mint": "x"}]
    dataset = _write_dataset(tmp_path / "unit", rows, None)
    code = measure_mod.main(["--dataset", str(dataset), "--max-ratio", "0.2"])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "no raw candidate rows" in captured.err


def test_rows_without_candidate_facts_fail_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A price-tick dataset (soak-style) carries no token facts; it must fail, never be skipped.
    rows = [
        {"ts_utc": _iso(BASE_TS + CADENCE_S * i), "kind": "tick", "mint": "x"} for i in range(3)
    ]
    dataset = _write_dataset(tmp_path / "unit", rows, None)
    code = measure_mod.main(["--dataset", str(dataset), "--max-ratio", "0.2"])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "candidate row 1 is malformed: missing field 'name'" in captured.err


@pytest.mark.parametrize("damage", ["digest", "not_json", "stray_file"])
def test_invalid_manifest_fails_with_exit_2(
    tmp_path: Path, damage: str, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = _dataset(tmp_path, _ten_rows())
    manifest_path = dataset / "manifest.json"
    if damage == "digest":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["sha256"]["events.jsonl"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif damage == "not_json":
        manifest_path.write_text("{not json", encoding="utf-8")
    else:
        (dataset / "extra.jsonl").write_text("{}\n", encoding="utf-8")

    code = measure_mod.main(["--dataset", str(dataset), "--max-ratio", "0.2"])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err.startswith("measure_grok_calls: error: ")


def test_admitted_candidate_without_recorded_outcome_fails_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _ten_rows()
    llm_rows = _llm_rows(rows)[:1]  # three admitted candidates, one record
    dataset = _write_dataset(tmp_path / "unit", rows, llm_rows)
    code = measure_mod.main(["--dataset", str(dataset), "--max-ratio", "1.0"])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "replay_missing_record" in captured.err


def test_gate_passes_with_exact_counts_and_leaves_dataset_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = _dataset(tmp_path, _ten_rows())
    before = sorted(path.name for path in dataset.iterdir())

    # max-ratio equal to the measured ratio (4 / 10) is inside the gate.
    code = measure_mod.main(
        ["--dataset", str(dataset), "--max-ratio", "0.4", "--min-candidates", "4"]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert json.loads(captured.out) == {
        "dataset": "unit",
        "provenance": "synthetic",
        "raw_candidates": 10,
        "admitted": 4,
        "before_calls": 10,
        "after_calls": 4,
        "ratio": 0.4,
        "gate": "pass",
    }
    assert sorted(path.name for path in dataset.iterdir()) == before


def test_gate_fails_when_ratio_exceeds_max(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = _dataset(tmp_path, _ten_rows())
    code = measure_mod.main(
        ["--dataset", str(dataset), "--max-ratio", "0.2", "--min-candidates", "1"]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 1
    assert result["gate"] == "fail"
    assert result["ratio"] == 0.4
    assert result["admitted"] == 4


def test_gate_fails_when_admitted_below_min_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = _dataset(tmp_path, _ten_rows())
    code = measure_mod.main(
        ["--dataset", str(dataset), "--max-ratio", "1.0", "--min-candidates", "5"]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 1
    assert result["gate"] == "fail"
    assert result["admitted"] == 4
    assert result["ratio"] == 0.4


def test_repeated_admitted_request_is_a_cache_hit_not_a_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = _ten_rows()[:3]
    # Same facts at the same instant under another mint: the request key carries no mint, and the
    # mint cooldown is per mint, so the duplicate is admitted with an identical key.
    rows.insert(1, dict(rows[0], mint=f"{99:044d}"))
    dataset = _dataset(tmp_path, rows)
    code = measure_mod.main(
        ["--dataset", str(dataset), "--max-ratio", "1.0", "--min-candidates", "1"]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["raw_candidates"] == 4
    assert result["admitted"] == 4
    assert result["after_calls"] == 3
    assert result["ratio"] == 0.75


def test_mint_cooldown_uses_last_admitted_decision_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # One mint: admitted at t, skipped at t+60 (inside the 300 s cooldown), admitted at t+400.
    # The third candidate must carry the first admitted decision time, not None. The creation
    # time is pinned so each tick has its own age, and the three requests differ in key.
    rows = [
        {**_row(0, ts=ts), "created_ts_utc": _iso(BASE_TS - 600)}
        for ts in (BASE_TS, BASE_TS + 60, BASE_TS + 400)
    ]
    dataset = _dataset(tmp_path, rows)
    seen: list[tuple[int, float | None]] = []
    original = measure_mod.request_for_row

    def spy(number: int, row: dict[str, Any], **kwargs: Any) -> Any:
        request = original(number, row, **kwargs)
        seen.append((number, request.candidate.last_decision_at))
        return request

    monkeypatch.setattr(measure_mod, "request_for_row", spy)
    code = measure_mod.main(
        ["--dataset", str(dataset), "--max-ratio", "1.0", "--min-candidates", "1"]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert seen == [(1, None), (2, BASE_TS), (3, BASE_TS)]
    assert result["admitted"] == 2
    assert result["after_calls"] == 2


def test_soak_3d_tokens_replays_without_missing_record(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The shipped soak fixture: each mint's cooldown comes from its last admitted decision, so
    # every request the script admits has a recorded outcome and the run is not an input error.
    code = measure_mod.main(
        ["--dataset", str(SOAK_DATASET), "--min-candidates", "1", "--max-ratio", "0.2"]
    )
    captured = capsys.readouterr()
    assert "replay_missing_record" not in captured.err
    assert captured.err == ""
    assert code in (0, 1)
    assert json.loads(captured.out)["gate"] in {"pass", "fail"}
