"""Engine domain models: tokens, metrics, agent results, scores, exits.

Port of the domain half of ``vendor/grokbot-pumpfun/src/models.py`` (the
config half lives in ``pumpgrok/config/settings.py``). All prose is English;
the vendor text is Russian.

Deliberate divergences from the oracle:

- Every model uses ``extra="forbid"`` (the vendor ``Token`` allows extras).
- ``Token.unique_buyers`` is ``int | None = None``. ``None`` means no trade
  evidence reached the filter; without a trade subscription (R45/R46) there
  is no other way to learn the buyer count, so ``None`` fails closed with
  ``data_unavailable`` instead of collapsing into ``0``.
- ``Token.age_seconds`` and ``ExitPosition`` take ``now`` explicitly. ``now
  or time.time()`` defaults are banned: ``0.0`` is falsy and would silently
  become wall time.
- The exit position is named ``ExitPosition``, not ``Position``: ``Position``
  already means integer base units plus marks in ``core/adapter.py``, and
  the two must never be confused at a call site.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Token(BaseModel):
    """A new token on the pump.fun bonding curve."""

    model_config = ConfigDict(extra="forbid")

    mint: str
    name: str | None = None
    symbol: str | None = None
    description: str | None = None
    image_uri: str | None = None
    metadata_uri: str | None = None
    twitter: str | None = None
    telegram: str | None = None
    website: str | None = None

    creator: str | None = None
    created_timestamp: float = 0.0

    # Buyer evidence. None means no evidence (fail closed); an int, even 0,
    # means the count was observed.
    unique_buyers: int | None = None
    curve_progress: float = 0.0  # 0..1, share of the curve already bought
    market_cap_sol: float = 0.0
    sol_in_curve: float = 0.0

    def age_seconds(self, now: float) -> float:
        if not self.created_timestamp:
            return 0.0
        return max(0.0, now - self.created_timestamp)

    @property
    def has_metadata(self) -> bool:
        return bool(self.name) and bool(self.image_uri)

    @property
    def has_socials(self) -> bool:
        return any([self.twitter, self.telegram, self.website])


class Holder(BaseModel):
    """One token holder."""

    model_config = ConfigDict(extra="forbid")

    address: str
    amount: float = 0.0
    share: float = 0.0  # share of total supply, 0..1
    is_creator: bool = False


class Trade(BaseModel):
    """One bonding-curve trade."""

    model_config = ConfigDict(extra="forbid")

    signature: str | None = None
    wallet: str
    is_buy: bool = True
    sol_amount: float = 0.0
    token_amount: float = 0.0
    timestamp: float = 0.0
    slot: int | None = None


class TokenMetrics(BaseModel):
    """Metrics computed by analyzer code. No LLM."""

    model_config = ConfigDict(extra="forbid")

    top5_share: float = 0.0  # top-5 wallet share, 0..1
    creator_share: float = 0.0  # creator share, 0..1
    sniper_count: int = 0  # buys in the first seconds of life
    wallet_diversity: float = 0.0  # 0..1, higher is more diverse
    social_signals: float = 0.0  # 0..1, presence and quality of links
    curve_health: float = 0.0  # 0..1, smoothness of curve accumulation
    buy_sell_ratio: float = 0.0
    unique_wallets: int = 0
    trade_count: int = 0
    risk_score: float = 10.0  # 0..10, higher is worse

    @property
    def quality(self) -> float:
        """Summary metric quality 0..1: the `metrics` scoring component."""
        return max(0.0, min(1.0, 1.0 - self.risk_score / 10.0))


class AuditResult(BaseModel):
    """Auditor agent: patterns invisible in aggregate metrics."""

    model_config = ConfigDict(extra="forbid")

    coordinated_buying: bool = True
    wash_trading: bool = True
    creator_dump_prep: bool = True
    bundled_launch: bool = True
    organic_buyer_share: float = 0.0  # 0..1
    confidence: float = 0.0  # 0..1
    flags: list[str] = Field(default_factory=list)
    reasoning: str = ""

    @property
    def score(self) -> float:
        """0..1: organic share minus a penalty per triggered flag."""
        penalties = sum(
            0.25
            for flag in (
                self.coordinated_buying,
                self.wash_trading,
                self.creator_dump_prep,
                self.bundled_launch,
            )
            if flag
        )
        return max(0.0, min(1.0, self.organic_buyer_share - penalties))

    @classmethod
    def pessimistic(cls, reason: str) -> AuditResult:
        """Fallback on agent failure: everything bad, no organic share."""
        return cls(
            coordinated_buying=True,
            wash_trading=True,
            creator_dump_prep=True,
            bundled_launch=True,
            organic_buyer_share=0.0,
            confidence=0.0,
            flags=["agent_failure"],
            reasoning=reason,
        )


class NarrativeResult(BaseModel):
    """Narrative agent: meme potential."""

    model_config = ConfigDict(extra="forbid")

    trend_fit: float = 0.0  # 0..1
    virality: float = 0.0  # 0..1
    community_signals: float = 0.0  # 0..1
    launch_timing: float = 0.0  # 0..1
    reasoning: str = ""

    @property
    def score(self) -> float:
        return max(
            0.0,
            min(
                1.0,
                (self.trend_fit + self.virality + self.community_signals + self.launch_timing)
                / 4.0,
            ),
        )

    @classmethod
    def pessimistic(cls, reason: str) -> NarrativeResult:
        return cls(reasoning=reason)


class TimingResult(BaseModel):
    """Timing agent: market state, not a specific token."""

    model_config = ConfigDict(extra="forbid")

    market_sentiment: float = 0.0  # 0..1
    meme_season: float = 0.0  # 0..1
    volume_level: float = 0.0  # 0..1
    anomalies: list[str] = Field(default_factory=list)
    reasoning: str = ""
    fetched_at: float = 0.0

    @property
    def score(self) -> float:
        base = (self.market_sentiment + self.meme_season + self.volume_level) / 3.0
        penalty = 0.1 * len(self.anomalies)
        return max(0.0, min(1.0, base - penalty))

    @classmethod
    def pessimistic(cls, reason: str) -> TimingResult:
        return cls(anomalies=["agent_failure"], reasoning=reason)


class CheckerResult(BaseModel):
    """Adversarial checker: looks for reasons NOT to buy."""

    model_config = ConfigDict(extra="forbid")

    approve: bool = False
    reason: str = ""
    flags: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    @classmethod
    def pessimistic(cls, reason: str) -> CheckerResult:
        """A failed check is a rejection, never a silent pass."""
        return cls(approve=False, reason=reason, flags=["agent_failure"], confidence=0.0)


class Scores(BaseModel):
    """Decomposed scoring: components plus total."""

    model_config = ConfigDict(extra="forbid")

    audit: float = 0.0
    narrative: float = 0.0
    timing: float = 0.0
    metrics: float = 0.0
    total: float = 0.0


class Analysis(BaseModel):
    """Everything the pipeline learned about a token before deciding."""

    model_config = ConfigDict(extra="forbid")

    token: Token
    metrics: TokenMetrics = Field(default_factory=TokenMetrics)
    audit: AuditResult | None = None
    narrative: NarrativeResult | None = None
    timing: TimingResult | None = None
    scores: Scores = Field(default_factory=Scores)
    checker: CheckerResult | None = None


class ExitPosition(BaseModel):
    """An open position as the exit rules see it.

    Named apart from ``core/adapter.py`` ``Position`` on purpose: the
    adapter tracks integer base units and ledger marks, while this tracks
    the entry/peak prices the trailing stop needs.
    """

    model_config = ConfigDict(extra="forbid")

    mint: str
    symbol: str | None = None
    creator: str | None = None
    entry_price: float = 0.0
    peak_price: float = 0.0  # max since entry, for the trailing stop
    sol_spent: float = 0.0
    token_amount: float = 0.0
    opened_at: float = 0.0
    tx_hash: str = ""
    score: float = 0.0
