"""Исполнение сделок на Solana.

ЗАГЛУШКА ПО ЗАМЫСЛУ. Код, который подписывает и отправляет транзакции
приватным ключом пользователя, здесь не сгенерирован: `LiveExecutor`
поднимает NotImplementedError, а рядом лежит список шагов, которые нужно
дописать руками.

Всё остальное настоящее:
  * `DryRunExecutor` проходит тот же интерфейс и пишет tx_hash "dry_run";
  * чтение цены с бондинговой кривой — общее для обоих режимов и работает,
    поэтому стоп-лосс в dry-run считается по реальным котировкам.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel

from .models import Config, Position, Token

log = logging.getLogger(__name__)

# Полный выпуск токена pump.fun.
TOTAL_SUPPLY = 1_000_000_000.0

DRY_RUN_TX = "dry_run"


class ExecutionResult(BaseModel):
    """Итог попытки исполнения."""

    ok: bool
    tx_hash: str = ""
    price: float = 0.0
    token_amount: float = 0.0
    sol_amount: float = 0.0
    error: str = ""


class BaseExecutor:
    """Общая часть: котировки и расчёт цены по кривой."""

    def __init__(self, config: Config, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> BaseExecutor:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.data.rest_url,
                timeout=self.config.data.request_timeout,
            )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def price(self, mint: str) -> float:
        """Цена одного токена в SOL по резервам кривой. 0.0, если неизвестна."""
        if self._client is None:
            return 0.0
        try:
            resp = await self._client.get(f"/coins/{mint}")
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.warning("цена %s недоступна: %s", mint, exc)
            return 0.0
        return price_from_reserves(data)

    async def buy(self, token: Token, size_sol: float) -> ExecutionResult:
        raise NotImplementedError

    async def sell(self, position: Position) -> ExecutionResult:
        raise NotImplementedError


def price_from_reserves(data: dict[str, Any]) -> float:
    """SOL за токен из виртуальных резервов бондинговой кривой."""
    sol_reserves = data.get("virtual_sol_reserves")
    token_reserves = data.get("virtual_token_reserves")
    if sol_reserves and token_reserves:
        try:
            return (float(sol_reserves) / 1e9) / (float(token_reserves) / 1e6)
        except ZeroDivisionError:
            return 0.0
    market_cap = data.get("market_cap") or data.get("usd_market_cap")
    if market_cap:
        return float(market_cap) / TOTAL_SUPPLY
    return 0.0


class DryRunExecutor(BaseExecutor):
    """Проходит весь путь, кроме отправки транзакции."""

    async def buy(self, token: Token, size_sol: float) -> ExecutionResult:
        price = await self.price(token.mint)
        if price <= 0:
            price = token.market_cap_sol / TOTAL_SUPPLY if token.market_cap_sol else 0.0
        if price <= 0:
            # Позиция с нулевой ценой входа неуправляема: ни одно правило
            # выхода на ней не срабатывает, и она висит открытой вечно.
            # Отказ от сделки — единственный правильный исход.
            log.warning("покупка %s отменена: цена входа неизвестна", token.mint[:8])
            return ExecutionResult(ok=False, error="цена входа неизвестна")

        log.info("[dry-run] покупка %s на %.4f SOL по %.12f", token.mint, size_sol, price)
        return ExecutionResult(
            ok=True,
            tx_hash=DRY_RUN_TX,
            price=price,
            token_amount=size_sol / price,
            sol_amount=size_sol,
        )

    async def sell(self, position: Position) -> ExecutionResult:
        price = await self.price(position.mint)
        proceeds = position.token_amount * price if price > 0 else 0.0
        log.info("[dry-run] продажа %s по %.12f, выручка %.4f SOL",
                 position.mint, price, proceeds)
        return ExecutionResult(
            ok=True,
            tx_hash=DRY_RUN_TX,
            price=price,
            token_amount=position.token_amount,
            sol_amount=proceeds,
        )


class LiveExecutor(BaseExecutor):
    """Реальная отправка транзакций. Намеренно не реализована.

    Дописывать здесь, руками, с полным пониманием каждого шага.
    """

    def __init__(self, config: Config, client: httpx.AsyncClient | None = None) -> None:
        super().__init__(config, client)
        self.rpc_url = config.solana.rpc_url
        self.jito = config.solana.jito

    async def buy(self, token: Token, size_sol: float) -> ExecutionResult:
        # TODO(live): покупка на бондинговой кривой pump.fun.
        #  1. Загрузить Keypair из config.solana.wallet_private_key (solders.keypair).
        #  2. Получить аккаунты кривой: bonding_curve, associated_bonding_curve,
        #     global, fee_recipient — и создать ATA покупателя, если её нет.
        #  3. Посчитать max_sol_cost с учётом проскальзывания и собрать
        #     инструкцию `buy` программы 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P.
        #  4. Добавить ComputeBudget: цену за юнит и лимит.
        #  5. При config.solana.jito.enabled — добавить перевод чаевых
        #     (jito.tip_lamports) на tip-аккаунт и отправить бандл на
        #     jito.block_engine_url; иначе send_transaction через RPC.
        #  6. Дождаться подтверждения, вернуть ExecutionResult с реальными
        #     tx_hash, ценой исполнения и полученным количеством токенов.
        raise NotImplementedError(
            "LiveExecutor.buy не реализован намеренно: допишите отправку "
            "транзакций сами, прежде чем включать mode: live"
        )

    async def sell(self, position: Position) -> ExecutionResult:
        # TODO(live): продажа. Та же схема, что и buy, но инструкция `sell`,
        #  min_sol_output вместо max_sol_cost и закрытие ATA после выхода.
        raise NotImplementedError(
            "LiveExecutor.sell не реализован намеренно: допишите отправку "
            "транзакций сами, прежде чем включать mode: live"
        )


def build_executor(config: Config, client: httpx.AsyncClient | None = None) -> BaseExecutor:
    """Исполнитель по режиму из конфига."""
    if config.is_live:
        log.warning("режим live: используется LiveExecutor")
        return LiveExecutor(config, client)
    return DryRunExecutor(config, client)


def new_position(token: Token, result: ExecutionResult, score: float) -> Position:
    return Position(
        mint=token.mint,
        symbol=token.symbol,
        creator=token.creator,
        entry_price=result.price,
        peak_price=result.price,
        sol_spent=result.sol_amount,
        token_amount=result.token_amount,
        opened_at=time.time(),
        tx_hash=result.tx_hash,
        score=score,
    )
