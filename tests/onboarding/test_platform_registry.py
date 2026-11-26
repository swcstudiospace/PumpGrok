"""Platform registry selects only evidenced platforms for backtest/paper."""

from pathlib import Path

import pytest

from pumpgrok.onboarding.platforms import (
    BY_ID,
    list_platforms,
    record_platform_choice,
    recorded_platform,
    select_platform,
)


def test_registry_lists_evidenced_platforms() -> None:
    ids = {platform.platform_id for platform in list_platforms()}
    assert ids == {
        "paper-execution",
        "solana-rpc",
        "pumpfun",
        "jupiter-quote",
        "xai-grok",
        "disabled-live-stub",
    }


def test_registry_inputs_are_inventory_names() -> None:
    allowed = {
        "xai_api_key",
        "wallet_public_address",
        "rpc_endpoint",
        "seat_tool_access",
        "hmac_confirmation_key",
    }
    for platform in list_platforms():
        assert set(platform.required_inputs) <= allowed


@pytest.mark.parametrize("mode", ["backtest", "paper"])
def test_selectable_platforms_allow_backtest_and_paper(mode: str) -> None:
    for platform in list_platforms():
        if platform.platform_id == "disabled-live-stub":
            assert not platform.can_select(mode)
        else:
            assert platform.can_select(mode)


def test_live_and_unknown_are_refused() -> None:
    with pytest.raises(KeyError):
        select_platform("paper-execution", "live")
    with pytest.raises(KeyError):
        select_platform("disabled-live-stub", "paper")
    with pytest.raises(KeyError):
        select_platform("binance-spot", "paper")


def test_choice_records_and_reads_back(tmp_path: Path) -> None:
    path = tmp_path / "choice-records.jsonl"
    row = record_platform_choice(path, "pumpfun", "paper")
    assert row == {"name": "platform", "value": "pumpfun", "source": "operator-choice"}
    assert recorded_platform(path) == "pumpfun"


def test_invalid_choice_is_not_recorded(tmp_path: Path) -> None:
    path = tmp_path / "choice-records.jsonl"
    with pytest.raises(KeyError):
        record_platform_choice(path, "disabled-live-stub", "paper")
    assert recorded_platform(path) is None


def test_registry_keys_match_listing() -> None:
    assert set(BY_ID) == {platform.platform_id for platform in list_platforms()}
