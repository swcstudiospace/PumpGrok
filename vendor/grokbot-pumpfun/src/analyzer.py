"""REST-анализатор метрик токена. Вторая ступень, тоже без LLM.

Три запроса к провайдеру данных идут параллельно через asyncio.gather:
карточка токена, топ-холдеры, последние сделки. Дальше всё считается кодом —
агенты дорогие, и отдавать им токен, у которого создатель держит половину
предложения, смысла нет.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import statistics
from typing import Any

import httpx

from .models import Config, Holder, Token, TokenMetrics, Trade

log = logging.getLogger(__name__)

# Покупка в первые N секунд жизни токена считается снайпом.
SNIPER_WINDOW_SECONDS = 15.0

# Сколько последних сделок тянем для анализа.
TRADE_LIMIT = 200
HOLDER_LIMIT = 50

# Безусловные вето. Взвешенная сумма их размывает: токен с создателем на
# четверти предложения набирал приемлемый риск за счёт хорошей кривой и
# живых соцсетей. Такие условия не компенсируются ничем, поэтому они
# выставляют максимальный риск, а не прибавляют к нему.
CREATOR_SHARE_VETO = 0.25
TOP5_SHARE_VETO = 0.80


class Analyzer:
    """Тянет сырые данные и сводит их в TokenMetrics."""

    def __init__(self, config: Config, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self.data = config.data
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> Analyzer:
        if self._client is None:
            headers = {"Accept": "application/json"}
            if self.data.key:
                headers["Authorization"] = f"Bearer {self.data.key}"
            self._client = httpx.AsyncClient(
                base_url=self.data.rest_url,
                timeout=self.data.request_timeout,
                headers=headers,
            )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Analyzer используется вне `async with`")
        return self._client

    # -- сеть --------------------------------------------------------------

    async def _get(self, path: str, **params: Any) -> Any:
        try:
            resp = await self.client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning("запрос %s не удался: %s", path, exc)
            return None

    async def fetch(self, mint: str) -> tuple[dict[str, Any], list[Holder], list[Trade]]:
        """Карточка, холдеры и сделки — тремя параллельными запросами."""
        info, holders_raw, trades_raw = await asyncio.gather(
            self._get(f"/coins/{mint}"),
            self._get(f"/coins/{mint}/holders", limit=HOLDER_LIMIT),
            self._get(f"/trades/all/{mint}", limit=TRADE_LIMIT),
        )
        return (
            info or {},
            [parse_holder(h) for h in (holders_raw or []) if isinstance(h, dict)],
            [parse_trade(t) for t in (trades_raw or []) if isinstance(t, dict)],
        )

    async def analyze(self, token: Token) -> TokenMetrics:
        """Полный проход: сходить в сеть и посчитать метрики."""
        info, holders, trades = await self.fetch(token.mint)
        enrich_token(token, info)
        return compute_metrics(token, holders, trades)

    def passes(self, metrics: TokenMetrics) -> tuple[bool, str]:
        """Отсечка по риск-скору. Возвращает (прошёл, причина)."""
        if metrics.trade_count == 0:
            return False, "no_trade_data"
        if metrics.risk_score > self.config.filter.max_risk_score:
            return False, "risk_score_too_high"
        return True, "ok"


# --------------------------------------------------------------------------
# Разбор ответов провайдера
# --------------------------------------------------------------------------


def parse_holder(raw: dict[str, Any]) -> Holder:
    amount = float(raw.get("amount") or raw.get("balance") or 0.0)
    share = raw.get("share")
    if share is None:
        pct = raw.get("percentage")
        share = float(pct) / 100.0 if pct is not None else 0.0
    return Holder(
        address=str(raw.get("address") or raw.get("wallet") or raw.get("owner") or ""),
        amount=amount,
        share=float(share),
        is_creator=bool(raw.get("is_creator") or raw.get("isCreator")),
    )


def parse_trade(raw: dict[str, Any]) -> Trade:
    ts = float(raw.get("timestamp") or 0.0)
    if ts > 1e11:  # миллисекунды
        ts /= 1000.0
    is_buy = raw.get("is_buy")
    if is_buy is None:
        is_buy = str(raw.get("txType", "buy")).lower() == "buy"
    return Trade(
        signature=raw.get("signature") or raw.get("tx"),
        wallet=str(raw.get("user") or raw.get("wallet") or raw.get("traderPublicKey") or ""),
        is_buy=bool(is_buy),
        sol_amount=float(raw.get("sol_amount") or raw.get("solAmount") or 0.0),
        token_amount=float(raw.get("token_amount") or raw.get("tokenAmount") or 0.0),
        timestamp=ts,
        slot=raw.get("slot"),
    )


def enrich_token(token: Token, info: dict[str, Any]) -> Token:
    """Дописать в токен то, чего не было в событии сокета."""
    if not info:
        return token
    token.description = token.description or info.get("description")
    token.image_uri = token.image_uri or info.get("image_uri") or info.get("image")
    token.twitter = token.twitter or info.get("twitter")
    token.telegram = token.telegram or info.get("telegram")
    token.website = token.website or info.get("website")
    token.creator = token.creator or info.get("creator")
    if info.get("market_cap") is not None:
        token.market_cap_sol = float(info["market_cap"])
    if info.get("virtual_sol_reserves") is not None:
        token.sol_in_curve = float(info["virtual_sol_reserves"]) / 1e9
    return token


# --------------------------------------------------------------------------
# Метрики (чистая функция, чтобы её можно было гонять без сети)
# --------------------------------------------------------------------------


def compute_metrics(token: Token, holders: list[Holder], trades: list[Trade]) -> TokenMetrics:
    """Свести сырьё в метрики и риск-скор 0..10."""
    buys = [t for t in trades if t.is_buy]
    sells = [t for t in trades if not t.is_buy]
    wallets = {t.wallet for t in trades if t.wallet}

    top5_share = sum(h.share for h in sorted(holders, key=lambda h: h.share, reverse=True)[:5])
    creator_share = next(
        (
            h.share
            for h in holders
            if h.is_creator or (token.creator and h.address == token.creator)
        ),
        0.0,
    )

    sniper_count = _count_snipers(token, buys)
    diversity = _wallet_diversity(buys)
    socials = _social_signals(token)
    curve_health = _curve_health(buys)

    buy_sell_ratio = len(buys) / len(sells) if sells else float(len(buys))

    risk = _risk_score(
        top5_share=top5_share,
        creator_share=creator_share,
        sniper_count=sniper_count,
        diversity=diversity,
        socials=socials,
        curve_health=curve_health,
        trade_count=len(trades),
    )
    veto = _veto_reason(creator_share, top5_share)
    if veto:
        log.info("%s отсечён безусловно: %s", token.mint[:8], veto)
        risk = 10.0

    return TokenMetrics(
        top5_share=round(min(1.0, top5_share), 4),
        creator_share=round(min(1.0, creator_share), 4),
        sniper_count=sniper_count,
        wallet_diversity=round(diversity, 4),
        social_signals=round(socials, 4),
        curve_health=round(curve_health, 4),
        buy_sell_ratio=round(buy_sell_ratio, 4),
        unique_wallets=len(wallets),
        trade_count=len(trades),
        risk_score=round(risk, 2),
    )


def _count_snipers(token: Token, buys: list[Trade]) -> int:
    if not token.created_timestamp:
        return 0
    cutoff = token.created_timestamp + SNIPER_WINDOW_SECONDS
    return len({t.wallet for t in buys if t.timestamp and t.timestamp <= cutoff})


def _wallet_diversity(buys: list[Trade]) -> float:
    """Доля уникальных кошельков среди покупок, со штрафом за концентрацию
    объёма в одном кошельке."""
    if not buys:
        return 0.0
    wallets = [t.wallet for t in buys if t.wallet]
    if not wallets:
        return 0.0
    uniqueness = len(set(wallets)) / len(wallets)

    volume: dict[str, float] = {}
    for t in buys:
        volume[t.wallet] = volume.get(t.wallet, 0.0) + t.sol_amount
    total = sum(volume.values())
    concentration = max(volume.values()) / total if total else 1.0
    return max(0.0, min(1.0, uniqueness * (1.0 - concentration)))


def _social_signals(token: Token) -> float:
    score = 0.0
    if token.twitter:
        score += 0.4
    if token.telegram:
        score += 0.3
    if token.website:
        score += 0.2
    if token.description and len(token.description) > 20:
        score += 0.1
    return min(1.0, score)


def _curve_health(buys: list[Trade]) -> float:
    """Ровный набор кривой лучше рывка: считаем разброс размеров покупок и
    равномерность интервалов между ними."""
    if len(buys) < 3:
        return 0.0
    amounts = [t.sol_amount for t in buys if t.sol_amount > 0]
    if len(amounts) < 3:
        return 0.0

    mean = statistics.fmean(amounts)
    spread = statistics.pstdev(amounts) / mean if mean else 1.0
    size_health = max(0.0, min(1.0, 1.0 - abs(spread - 0.6)))

    stamps = sorted(t.timestamp for t in buys if t.timestamp)
    if len(stamps) >= 3:
        gaps = [b - a for a, b in itertools.pairwise(stamps) if b > a]
        if gaps:
            gap_mean = statistics.fmean(gaps)
            gap_spread = statistics.pstdev(gaps) / gap_mean if gap_mean else 1.0
            pace_health = max(0.0, min(1.0, 1.0 - gap_spread / 2.0))
        else:
            pace_health = 0.0
    else:
        pace_health = 0.0

    return max(0.0, min(1.0, 0.6 * size_health + 0.4 * pace_health))


def _veto_reason(creator_share: float, top5_share: float) -> str | None:
    """Условие, при котором остальные метрики уже не важны."""
    if creator_share >= CREATOR_SHARE_VETO:
        return f"создатель держит {creator_share:.0%} предложения"
    if top5_share >= TOP5_SHARE_VETO:
        return f"топ-5 кошельков держат {top5_share:.0%}"
    return None


def _risk_score(
    *,
    top5_share: float,
    creator_share: float,
    sniper_count: int,
    diversity: float,
    socials: float,
    curve_health: float,
    trade_count: int,
) -> float:
    """0..10, чем выше — тем хуже. Веса подобраны так, чтобы любой одиночный
    красный флаг (создатель с половиной предложения, топ-5 под 80%) сам по
    себе уводил токен за порог отсечки."""
    risk = 0.0
    risk += min(3.0, top5_share * 3.75)          # >80% топ-5 -> 3.0
    risk += min(3.0, creator_share * 10.0)       # >30% у создателя -> 3.0
    risk += min(2.0, sniper_count * 0.25)        # 8 снайперов -> 2.0
    risk += (1.0 - diversity) * 1.5
    risk += (1.0 - curve_health) * 1.0
    risk += (1.0 - socials) * 0.5
    if trade_count < 10:
        risk += 1.0                              # данных мало, доверия меньше
    return max(0.0, min(10.0, risk))
