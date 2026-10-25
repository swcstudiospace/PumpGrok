"""REST analyzer for token metrics. Second stage, still no LLM.

Port of the retired oracle ``src/analyzer.py``. All prose is English;
the vendor text is Russian.

Deliberate divergences from the oracle:

- The pump.fun ``Bearer`` header is dropped: no settings field carries a
  pump.fun key, so there is nothing to send.
- Every ``_get`` call records a per-source health flag in
  ``Analyzer.health`` (keyed by endpoint path, ``True`` on success). No
  entry decision may rest solely on pump.fun REST (R47); the flag lets the
  pipeline tell a healthy empty answer from a failed provider.
- ``_veto_reason`` returns ASCII codes (``creator_share_veto``,
  ``top5_share_veto``) instead of Russian free text.
- The analyzer takes the ``data`` and ``filter`` settings sections, not the
  vendor ``Config``. ``max_risk_score`` for ``passes()`` comes from the
  filter section.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
import statistics
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import httpx

from pumpgrok.config.settings import DataSettings, FilterSettings
from pumpgrok.engine.models import Holder, Token, TokenMetrics, Trade

log = logging.getLogger(__name__)

# A buy in the first N seconds of a token's life counts as a snipe.
SNIPER_WINDOW_SECONDS = 15.0

# How many recent trades and holders to pull for the analysis.
TRADE_LIMIT = 200
HOLDER_LIMIT = 50

# Unconditional vetoes. A weighted sum washes them out: a token whose
# creator holds a quarter of supply scored an acceptable risk on the back
# of a good curve and live socials. Such terms are compensated by nothing,
# so they set the maximum risk instead of adding to it.
CREATOR_SHARE_VETO = 0.25
TOP5_SHARE_VETO = 0.80


class Analyzer:
    """Pulls raw data and reduces it to TokenMetrics."""

    def __init__(
        self,
        data: DataSettings,
        filter_cfg: FilterSettings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.data = data
        self.filter_cfg = filter_cfg
        self._client = client
        self._owns_client = client is None
        # Per-source health: endpoint path -> last fetch ok. Empty means
        # the source was never touched, which counts as healthy.
        self.health: dict[str, bool] = {}

    async def __aenter__(self) -> Analyzer:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.data.rest_url,
                timeout=self.data.request_timeout,
                headers={"Accept": "application/json"},
            )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("Analyzer used outside `async with`")
        return self._client

    def source_health(self, path: str) -> bool:
        """Last fetch ok for this endpoint path; True when never fetched."""
        return self.health.get(path, True)

    # -- network -----------------------------------------------------------

    async def _get(self, path: str, **params: Any) -> Any:
        try:
            resp = await self.client.get(path, params=params)
            resp.raise_for_status()
            self.health[path] = True
            return resp.json()
        except Exception as exc:
            log.warning("request %s failed: %s", path, type(exc).__name__)
            self.health[path] = False
            return None

    async def fetch(self, mint: str) -> tuple[dict[str, Any], list[Holder], list[Trade]]:
        """Card, holders, and trades: three parallel requests."""
        info, holders_raw, trades_raw = await asyncio.gather(
            self._get(f"/coins/{mint}"),
            self._get(f"/coins/{mint}/holders", limit=HOLDER_LIMIT),
            self._get(f"/trades/all/{mint}", limit=TRADE_LIMIT),
        )
        if not isinstance(info, dict):
            info = {}
        holders = [
            parsed
            for h in (holders_raw or [])
            if isinstance(h, dict)
            for parsed in [_safe_parse(parse_holder, h)]
            if parsed is not None
        ]
        trades = [
            parsed
            for t in (trades_raw or [])
            if isinstance(t, dict)
            for parsed in [_safe_parse(parse_trade, t)]
            if parsed is not None
        ]
        return (info, holders, trades)

    async def analyze(self, token: Token) -> TokenMetrics:
        """Full pass: hit the network, then compute metrics."""
        info, holders, trades = await self.fetch(token.mint)
        enrich_token(token, info)
        return compute_metrics(token, holders, trades)

    def passes(self, metrics: TokenMetrics) -> tuple[bool, str]:
        """Risk-score cutoff. Returns (passed, reason)."""
        if metrics.trade_count == 0:
            return False, "no_trade_data"
        if metrics.risk_score > self.filter_cfg.max_risk_score:
            return False, "risk_score_too_high"
        return True, "ok"


# --------------------------------------------------------------------------
# Provider response parsing
# --------------------------------------------------------------------------


def _safe_parse[T](parse: Callable[[dict[str, Any]], T], raw: dict[str, Any]) -> T | None:
    """One poisoned row degrades to a skip, never to a lost analysis."""
    try:
        return parse(raw)
    except (ValueError, TypeError):
        return None


def _to_int_units(value: Any, *, per_unit: int) -> int:
    """Provider decimal/float amount to integer units, ROUND_HALF_UP (INT-01).

    Raises ValueError on unparseable input so ``_safe_parse`` skips the row.
    """
    try:
        scaled = Decimal(str(value)) * per_unit
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise ValueError(f"bad amount {value!r}") from exc
    try:
        return int(scaled.to_integral_value(rounding=ROUND_HALF_UP))
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise ValueError(f"bad amount {value!r}") from exc


def _to_lamports(value: Any) -> int:
    """Provider SOL amount to integer lamports (INT-01)."""
    return _to_int_units(value, per_unit=10**9)


def _to_base_units(value: Any) -> int:
    """Provider token amount to integer base units (INT-01)."""
    return _to_int_units(value, per_unit=1)


def parse_holder(raw: dict[str, Any]) -> Holder:
    amount = _to_base_units(raw.get("amount") or raw.get("balance") or 0)
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
    if ts > 1e11:  # milliseconds
        ts /= 1000.0
    is_buy = raw.get("is_buy")
    if is_buy is None:
        is_buy = str(raw.get("txType", "buy")).lower() == "buy"
    return Trade(
        signature=raw.get("signature") or raw.get("tx"),
        wallet=str(raw.get("user") or raw.get("wallet") or raw.get("traderPublicKey") or ""),
        is_buy=bool(is_buy),
        sol_amount=_to_lamports(raw.get("sol_amount") or raw.get("solAmount") or 0),
        token_amount=_to_base_units(raw.get("token_amount") or raw.get("tokenAmount") or 0),
        timestamp=ts,
        slot=raw.get("slot"),
    )


def enrich_token(token: Token, info: dict[str, Any]) -> Token:
    """Fill in what the socket event did not carry."""
    if not info:
        return token
    token.description = token.description or info.get("description")
    token.image_uri = token.image_uri or info.get("image_uri") or info.get("image")
    token.twitter = token.twitter or info.get("twitter")
    token.telegram = token.telegram or info.get("telegram")
    token.website = token.website or info.get("website")
    token.creator = token.creator or info.get("creator")
    if info.get("market_cap") is not None:
        with contextlib.suppress(ValueError, TypeError):
            token.market_cap_sol = _to_lamports(info["market_cap"])
    if info.get("virtual_sol_reserves") is not None:
        with contextlib.suppress(ValueError, TypeError):
            token.sol_in_curve = _to_base_units(info["virtual_sol_reserves"])
    return token


# --------------------------------------------------------------------------
# Metrics (a pure function, so it runs without the network)
# --------------------------------------------------------------------------


def compute_metrics(token: Token, holders: list[Holder], trades: list[Trade]) -> TokenMetrics:
    """Reduce raw inputs to metrics and a 0..10 risk score."""
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
        log.info("%s cut unconditionally: %s", token.mint[:8], veto)
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
    """Share of unique wallets among buys, penalized when one wallet
    concentrates the volume."""
    if not buys:
        return 0.0
    wallets = [t.wallet for t in buys if t.wallet]
    if not wallets:
        return 0.0
    uniqueness = len(set(wallets)) / len(wallets)

    volume: dict[str, int] = {}
    for t in buys:
        volume[t.wallet] = volume.get(t.wallet, 0) + t.sol_amount
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
    """A smooth curve beats a jerky one: measure the spread of buy sizes and
    the evenness of gaps between them."""
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
    """The condition under which the other metrics no longer matter."""
    if creator_share >= CREATOR_SHARE_VETO:
        return "creator_share_veto"
    if top5_share >= TOP5_SHARE_VETO:
        return "top5_share_veto"
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
    """0..10, higher is worse. Weights are set so that any single red flag
    (creator with half the supply, top-5 near 80%) pushes the token past
    the cutoff on its own."""
    risk = 0.0
    risk += min(3.0, top5_share * 3.75)  # >80% top-5 -> 3.0
    risk += min(3.0, creator_share * 10.0)  # >30% with creator -> 3.0
    risk += min(2.0, sniper_count * 0.25)  # 8 snipers -> 2.0
    risk += (1.0 - diversity) * 1.5
    risk += (1.0 - curve_health) * 1.0
    risk += (1.0 - socials) * 0.5
    if trade_count < 10:
        risk += 1.0  # thin data, less trust
    return max(0.0, min(10.0, risk))
