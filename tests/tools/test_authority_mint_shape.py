"""check_mint must only report authorities for accounts shaped like a token mint."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from harness import NetworkBlocked
from pumpgrok.tools.onchain.authorities import check_mint

MINT = "So11111111111111111111111111111111111111112"


class _FakeRpc:
    """Returns one canned ``getAccountInfo`` result; records nothing else."""

    def __init__(self, result: Any) -> None:
        self._result = result

    async def call(self, method: str, params: list[Any]) -> Any:
        assert method == "getAccountInfo"
        return self._result


def _account(info: dict[str, Any]) -> dict[str, Any]:
    return {"value": {"data": {"parsed": {"type": "account", "info": info}}}}


def test_non_mint_account_is_not_ok() -> None:
    # A token account carries owner/mint/amount but no decimals or isInitialized.
    token_account = {
        "mint": MINT,
        "owner": "11111111111111111111111111111111",
        "tokenAmount": {"amount": "1", "decimals": 0},
    }
    result = asyncio.run(check_mint(MINT, _FakeRpc(_account(token_account))))

    assert result["ok"] is False
    assert "hasMintAuthority" not in result


def test_mint_shaped_account_reports_authorities() -> None:
    mint_info = {
        "mintAuthority": None,
        "freezeAuthority": None,
        "decimals": 6,
        "supply": "1000",
        "isInitialized": True,
    }
    result = asyncio.run(check_mint(MINT, _FakeRpc(_account(mint_info))))

    assert result["ok"] is True
    assert result["decimals"] == 6
    assert result["hasMintAuthority"] is False
    assert result["hasFreezeAuthority"] is False


def test_network_blocked_propagates_through_except_exception() -> None:
    class _BlockingRpc:
        async def call(self, method: str, params: list[Any]) -> Any:
            raise NetworkBlocked("blocked")

    # check_mint's broad handler must not swallow the offline guard.
    with pytest.raises(NetworkBlocked):
        asyncio.run(check_mint(MINT, _BlockingRpc()))
