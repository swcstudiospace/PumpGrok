"""Evidence grading refuses non-promotion data (BT-10)."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from pumpgrok.backtest.grading import APPROVED_THRESHOLDS, CanaryResult, grade
from pumpgrok.replay.clock import format_ts_utc
from pumpgrok.replay.live_recorder import seal_directory

_PASS = CanaryResult(passed=True)
_FAIL = CanaryResult(passed=False)
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "replay"


def test_smoke_fixture_is_research_only() -> None:
    result = grade(_FIXTURES / "smoke", _PASS, APPROVED_THRESHOLDS)
    assert result.verdict == "research_only"
    assert "fixture" in result.reasons
    assert result.reasons == tuple(sorted(result.reasons))


def test_tmp_path_traded_only_is_synthetic_and_traded_only(tmp_path: Path) -> None:
    _write_events(
        tmp_path,
        [{"ts": 0.0, "mint": "MintTrade", "traded_only": True, "price": 1}],
    )
    result = grade(tmp_path, _PASS, APPROVED_THRESHOLDS)
    assert result.verdict == "research_only"
    assert "synthetic" in result.reasons
    assert "traded_only" in result.reasons


def test_hand_authored_label_is_research_only(tmp_path: Path) -> None:
    _write_manifest(tmp_path, sources={"rest": "hand-authored"})
    result = grade(tmp_path, _PASS, APPROVED_THRESHOLDS)
    assert result.verdict == "research_only"
    assert "hand_authored" in result.reasons


def test_short_window_is_research_only(tmp_path: Path) -> None:
    start = 1_700_000_000.0
    _write_manifest(
        tmp_path,
        recorded_from_utc=format_ts_utc(start),
        recorded_to_utc=format_ts_utc(start + APPROVED_THRESHOLDS.long_s - 1),
        provenance="recorded",
    )
    result = grade(tmp_path, _PASS, APPROVED_THRESHOLDS)
    assert result.verdict == "research_only"
    assert "short" in result.reasons
    assert "canary" not in result.reasons


def test_gap_heavy_window_is_research_only(tmp_path: Path) -> None:
    start = 1_700_000_000.0
    end = start + APPROVED_THRESHOLDS.long_s
    _write_events(
        tmp_path,
        [
            {"ts": start, "ts_utc": format_ts_utc(start), "mint": "MintGap", "price": 1},
            {"ts": end, "ts_utc": format_ts_utc(end), "mint": "MintGap", "price": 1},
        ],
    )
    _write_manifest(
        tmp_path,
        recorded_from_utc=format_ts_utc(start),
        recorded_to_utc=format_ts_utc(end),
        provenance="recorded",
    )
    result = grade(tmp_path, _PASS, APPROVED_THRESHOLDS)
    assert result.verdict == "research_only"
    assert "gap" in result.reasons


def test_failed_canary_is_research_only(tmp_path: Path) -> None:
    _write_events(tmp_path, [{"ts": 0.0, "mint": "MintCanary", "price": 1}])
    result = grade(tmp_path, _FAIL, APPROVED_THRESHOLDS)
    assert result.verdict == "research_only"
    assert "canary" in result.reasons


def test_promotion_eligible_for_a_synthetic_recorded_long_window() -> None:
    """TEST-T13: build a sealed, recorded, long-window dataset so the positive
    promotion_eligible branch is exercised in CI (no recorded dataset ships in
    the repo). The directory lives under the repo tree, not the temp root:
    grade() marks temp-root datasets synthetic by design."""
    start = 1_700_000_000.0
    duration = APPROVED_THRESHOLDS.long_s + 120.0
    scratch = Path(tempfile.mkdtemp(dir=Path(__file__).resolve().parent))
    dataset = scratch / "recorded-synthetic"
    dataset.mkdir()
    try:
        events = [
            {
                "ts": start + step * 120.0,
                "ts_utc": format_ts_utc(start + step * 120.0),
                "mint": "MintRecorded",
                "price": 1,
            }
            for step in range(int(duration // 120) + 1)
        ]
        (dataset / "events.jsonl").write_text(
            "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n",
            encoding="utf-8",
        )
        seal_directory(
            dataset,
            recorded_from_utc=format_ts_utc(start),
            recorded_to_utc=format_ts_utc(start + duration),
            sources={"rest": "recorded"},
            notes="synthetic test dataset",
            seed_hint=1,
        )
        result = grade(dataset, _PASS, APPROVED_THRESHOLDS)
        assert result.verdict == "promotion_eligible"
        assert result.reasons == ()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _write_events(directory: Path, events: list[dict[str, object]]) -> None:
    lines = [json.dumps(event, sort_keys=True) for event in events]
    (directory / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_manifest(
    directory: Path,
    *,
    sources: dict[str, str] | None = None,
    recorded_from_utc: str = "2026-01-01T00:00:00.000000Z",
    recorded_to_utc: str = "2026-01-01T00:00:01.000000Z",
    provenance: str = "recorded",
) -> None:
    payload = {
        "dataset": directory.name,
        "recorded_from_utc": recorded_from_utc,
        "recorded_to_utc": recorded_to_utc,
        "seed_hint": 1,
        "sources": sources or {"rest": "recorded"},
        "sha256": {"events.jsonl": "0" * 64},
        "notes": "",
        "provenance": provenance,
    }
    (directory / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
