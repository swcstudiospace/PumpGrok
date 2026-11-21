"""Paper start is refused until required inputs are complete."""

from pathlib import Path

from pumpgrok.onboarding.start_gate import check_start


def test_clean_env_refuses() -> None:
    missing = check_start({}, "paper")
    assert "xai_api_key" in missing
    assert any(name.startswith("bot-") for name in missing)


def test_with_inputs_and_access_starts(tmp_path: Path) -> None:
    from pumpgrok.onboarding.access import record_access

    access = tmp_path / "access.jsonl"
    for seat in ("bot-01-scout", "bot-02-risk", "bot-06-exit"):
        record_access(access, seat)
    assert check_start(
        {"PUMPGROK_GROK__API_KEY": "x"}, "paper", access_path=access
    ) == []
