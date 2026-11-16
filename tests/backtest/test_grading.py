"""Evidence grading refuses non-promotion data (BT-10)."""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.backtest.grading import APPROVED_THRESHOLDS, CanaryResult, grade
from pumpgrok.replay.clock import format_ts_utc

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


def test_promotion_eligible_only_when_a_recorded_dataset_exists() -> None:
    """No recorded non-synthetic dataset is in the repo. Do not invent one."""
    candidate = _recorded_candidate()
    if candidate is None:
        return
    result = grade(candidate, _PASS, APPROVED_THRESHOLDS)
    assert result.verdict == "promotion_eligible"
    assert result.reasons == ()


def _recorded_candidate() -> Path | None:
    if not _FIXTURES.is_dir():
        return None
    for manifest_path in sorted(_FIXTURES.glob("*/manifest.json")):
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        name = str(raw.get("dataset", manifest_path.parent.name))
        if name.startswith("smoke"):
            continue
        if raw.get("provenance") != "recorded":
            continue
        return manifest_path.parent
    return None


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