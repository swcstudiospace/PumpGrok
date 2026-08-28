"""Pydantic-модели пайплайна.

Здесь же живут модели конфига: конфиг читается один раз при старте и
дальше ходит по пайплайну типизированным объектом, а не словарём.

Секреты — SecretStr: они не попадут ни в логи, ни в traceback, ни в дамп
состояния, даже если модель где-то напечатают целиком.
"""

from __future__ import annotations

import copy
import os
import time
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr

# --------------------------------------------------------------------------
# Токен и метрики
# --------------------------------------------------------------------------


class Token(BaseModel):
    """Новый токен на бондинговой кривой pump.fun."""

    model_config = ConfigDict(extra="allow")

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

    unique_buyers: int = 0
    curve_progress: float = 0.0          # 0..1, доля выкупленной кривой
    market_cap_sol: float = 0.0
    sol_in_curve: float = 0.0

    @property
    def age_seconds(self) -> float:
        if not self.created_timestamp:
            return 0.0
        return max(0.0, time.time() - self.created_timestamp)

    @property
    def has_metadata(self) -> bool:
        return bool(self.name) and bool(self.image_uri)

    @property
    def has_socials(self) -> bool:
        return any([self.twitter, self.telegram, self.website])


class Holder(BaseModel):
    """Держатель токена."""

    model_config = ConfigDict(extra="allow")

    address: str
    amount: float = 0.0
    share: float = 0.0                   # доля от общего предложения, 0..1
    is_creator: bool = False


class Trade(BaseModel):
    """Сделка на кривой."""

    model_config = ConfigDict(extra="allow")

    signature: str | None = None
    wallet: str
    is_buy: bool = True
    sol_amount: float = 0.0
    token_amount: float = 0.0
    timestamp: float = 0.0
    slot: int | None = None


class TokenMetrics(BaseModel):
    """Метрики, посчитанные кодом в analyzer.py. Без LLM."""

    top5_share: float = 0.0              # доля топ-5 кошельков, 0..1
    creator_share: float = 0.0           # доля создателя, 0..1
    sniper_count: int = 0                # покупки в первые секунды жизни
    wallet_diversity: float = 0.0        # 0..1, чем выше, тем разнообразнее
    social_signals: float = 0.0          # 0..1, наличие и качество ссылок
    curve_health: float = 0.0            # 0..1, ровность набора кривой
    buy_sell_ratio: float = 0.0
    unique_wallets: int = 0
    trade_count: int = 0
    risk_score: float = 10.0             # 0..10, чем выше, тем хуже

    @property
    def quality(self) -> float:
        """Сводное качество метрик 0..1 — компонент `metrics` в скоринге."""
        return max(0.0, min(1.0, 1.0 - self.risk_score / 10.0))


# --------------------------------------------------------------------------
# Ответы агентов
# --------------------------------------------------------------------------


class AuditResult(BaseModel):
    """Агент-аудитор: паттерны, которые не видно в агрегированных метриках."""

    coordinated_buying: bool = True
    wash_trading: bool = True
    creator_dump_prep: bool = True
    bundled_launch: bool = True
    organic_buyer_share: float = 0.0     # 0..1
    confidence: float = 0.0              # 0..1
    flags: list[str] = Field(default_factory=list)
    reasoning: str = ""

    @property
    def score(self) -> float:
        """0..1: органика минус штраф за каждый сработавший флаг."""
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
        """Фолбэк при ошибке: всё плохо, органики нет."""
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
    """Агент-нарратив: мем-потенциал."""

    trend_fit: float = 0.0               # попадание в тренд, 0..1
    virality: float = 0.0                # виральность, 0..1
    community_signals: float = 0.0       # признаки живого сообщества, 0..1
    launch_timing: float = 0.0           # своевременность запуска, 0..1
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
    """Агент-тайминг: состояние рынка, а не конкретный токен."""

    market_sentiment: float = 0.0        # 0..1
    meme_season: float = 0.0             # 0..1
    volume_level: float = 0.0            # 0..1
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
    """Адверсариальный чекер: ищет причины НЕ покупать."""

    approve: bool = False
    reason: str = ""
    flags: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    @classmethod
    def pessimistic(cls, reason: str) -> CheckerResult:
        """Ошибка проверки равна отказу, а не молчаливому пропуску."""
        return cls(approve=False, reason=reason, flags=["agent_failure"], confidence=0.0)


# --------------------------------------------------------------------------
# Скоринг, решение, позиция
# --------------------------------------------------------------------------


class Scores(BaseModel):
    """Разложенный скоринг: компоненты и итог."""

    audit: float = 0.0
    narrative: float = 0.0
    timing: float = 0.0
    metrics: float = 0.0
    total: float = 0.0


class Analysis(BaseModel):
    """Всё, что пайплайн узнал о токене к моменту решения."""

    token: Token
    metrics: TokenMetrics = Field(default_factory=TokenMetrics)
    audit: AuditResult | None = None
    narrative: NarrativeResult | None = None
    timing: TimingResult | None = None
    scores: Scores = Field(default_factory=Scores)
    checker: CheckerResult | None = None


class Position(BaseModel):
    """Открытая позиция."""

    mint: str
    symbol: str | None = None
    creator: str | None = None
    entry_price: float = 0.0
    peak_price: float = 0.0          # максимум с момента входа, для трейлинга
    sol_spent: float = 0.0
    token_amount: float = 0.0
    opened_at: float = 0.0
    tx_hash: str = ""
    score: float = 0.0


class TradeDecision(BaseModel):
    """Решение риск-гейта."""

    approved: bool
    size_sol: float = 0.0
    reason: str = ""


# --------------------------------------------------------------------------
# Конфиг
# --------------------------------------------------------------------------


class SecretModel(BaseModel):
    """База для секций с секретами: присваивание строки коэрсится в SecretStr."""

    model_config = ConfigDict(validate_assignment=True)


class GrokConfig(SecretModel):
    api_key: SecretStr = SecretStr("")
    base_url: str = "https://api.x.ai/v1/chat/completions"
    fast_model: str = "grok-4-fast"
    checker_model: str = "grok-4"
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_base_delay: float = 1.0

    @property
    def key(self) -> str:
        return self.api_key.get_secret_value()


class JitoConfig(BaseModel):
    enabled: bool = True
    block_engine_url: str = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"
    tip_lamports: int = 1_000_000


class SolanaConfig(SecretModel):
    rpc_url: str = "https://api.mainnet-beta.solana.com"
    wallet_private_key: SecretStr = SecretStr("")
    jito: JitoConfig = Field(default_factory=JitoConfig)

    @property
    def wallet_key(self) -> str:
        return self.wallet_private_key.get_secret_value()


class DataConfig(SecretModel):
    api_key: SecretStr = SecretStr("")
    rest_url: str = "https://frontend-api.pump.fun"
    ws_url: str = "wss://pumpportal.fun/api/data"
    request_timeout: float = 10.0

    @property
    def key(self) -> str:
        return self.api_key.get_secret_value()


class RiskConfig(BaseModel):
    max_sol_per_trade: float = 0.5
    daily_loss_limit_sol: float = 2.0
    max_trades_per_day: int = 20
    max_open_positions: int = 3
    stop_loss_pct: float = 30.0
    stop_loss_poll_seconds: float = 15.0
    # Выходы вверх и по времени. 0 в любом из них выключает правило.
    take_profit_pct: float = 120.0
    trailing_stop_pct: float = 35.0       # откат от пика, считается только выше входа
    max_hold_seconds: float = 3600.0      # мемкоин, который час не поехал, не поедет


class FilterConfig(BaseModel):
    min_unique_buyers: int = 5
    max_curve_progress: float = 0.40
    require_metadata: bool = True
    min_age_seconds: float = 120.0
    max_risk_score: float = 7.0
    min_total_score: float = 0.65
    # Память о создателях. 0 в block_creator_after_rugs выключает правило.
    block_creator_after_rugs: int = 1
    rug_loss_pct: float = 60.0            # убыток от этого уровня считается сливом
    one_position_per_creator: bool = True
    forget_creators_after_days: float = 30.0


class ScoringWeights(BaseModel):
    audit: float = 0.30
    narrative: float = 0.25
    timing: float = 0.15
    metrics: float = 0.30


class ScoringConfig(BaseModel):
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    timing_cache_seconds: float = 900.0


class AlertsConfig(SecretModel):
    """Уведомления наружу. Пустой webhook_url — выключено."""

    # В URL обычно зашит токен, поэтому это секрет, а не строка.
    webhook_url: SecretStr = SecretStr("")
    events: list[str] = Field(
        default_factory=lambda: [
            "started", "buy", "close", "rug", "breaker", "halted", "blind"
        ]
    )
    timeout_seconds: float = 10.0
    max_per_minute: int = 20


class LoggingConfig(BaseModel):
    path: str = "logs/trades.jsonl"
    level: str = "INFO"
    max_bytes: int = 50_000_000          # ротация JSONL, 0 — не ротировать
    backups: int = 5


class OpsConfig(BaseModel):
    """Эксплуатационные настройки: то, что нужно процессу, живущему сутками."""

    state_path: str = "state/pipeline.json"   # переживает рестарт
    reputation_path: str = "state/creators.json"   # память о создателях
    health_port: int = 0                      # 0 — health-эндпоинт выключен
    health_host: str = "127.0.0.1"
    heartbeat_seconds: float = 300.0          # строка живости в лог
    shutdown_grace_seconds: float = 30.0      # сколько ждать токены в работе
    max_grok_calls_per_day: int = 2000        # потолок расхода на агентов
    grok_max_concurrency: int = 4
    grok_calls_per_minute: int = 60
    breaker_failures: int = 8                 # подряд, до размыкания
    breaker_cooldown_seconds: float = 120.0


# --------------------------------------------------------------------------
# Конфиг целиком
# --------------------------------------------------------------------------

# Плейсхолдеры из config.example.yaml. Ловятся до старта, а не в проде.
PLACEHOLDER_MARKERS = ("YOUR", "CHANGEME", "xxx", "<", "example")

# Переменные окружения важнее файла: в контейнере секреты приходят так, а
# не редактированием yaml внутри образа.
ENV_OVERRIDES: dict[str, tuple[str, ...]] = {
    "GROKBOT_MODE": ("mode",),
    "GROKBOT_GROK_API_KEY": ("grok", "api_key"),
    "GROKBOT_DATA_API_KEY": ("data", "api_key"),
    "GROKBOT_WALLET_PRIVATE_KEY": ("solana", "wallet_private_key"),
    "GROKBOT_RPC_URL": ("solana", "rpc_url"),
    "GROKBOT_LOG_PATH": ("logging", "path"),
    "GROKBOT_LOG_LEVEL": ("logging", "level"),
    "GROKBOT_STATE_PATH": ("ops", "state_path"),
    "GROKBOT_HEALTH_PORT": ("ops", "health_port"),
    "GROKBOT_ALERT_WEBHOOK": ("alerts", "webhook_url"),
}


# События, которые пайплайн умеет отправлять в webhook.
ALERT_EVENTS = frozenset(
    {"started", "stopped", "buy", "close", "rug", "breaker", "halted", "stalled", "blind"}
)


class ConfigError(RuntimeError):
    """Конфиг не годится для запуска. Список проблем — в аргументе."""


def is_placeholder(value: str) -> bool:
    """Значение из шаблона, а не настоящий секрет."""
    if not value.strip():
        return True
    return any(marker.lower() in value.lower() for marker in PLACEHOLDER_MARKERS)


def mask(secret: str) -> str:
    """Как секрет выглядит в логах: хвост опознать можно, использовать нельзя."""
    if not secret:
        return "<пусто>"
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}…{secret[-4:]} ({len(secret)} симв.)"


def _deep_set(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    node = target
    for key in path[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    node[path[-1]] = value


class Config(BaseModel):
    mode: Literal["dry-run", "live"] = "dry-run"
    grok: GrokConfig = Field(default_factory=GrokConfig)
    solana: SolanaConfig = Field(default_factory=SolanaConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    filter: FilterConfig = Field(default_factory=FilterConfig)
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    ops: OpsConfig = Field(default_factory=OpsConfig)

    @property
    def is_live(self) -> bool:
        return self.mode == "live"

    # -- загрузка ----------------------------------------------------------

    @classmethod
    def load(
        cls,
        path: str | Path = "config.yaml",
        env: dict[str, str] | None = None,
    ) -> Config:
        """Прочитать yaml и наложить переменные окружения поверх."""
        raw: dict[str, Any] = yaml.safe_load(Path(path).read_text()) or {}
        return cls.from_raw(raw, env)

    @classmethod
    def from_raw(cls, raw: dict[str, Any], env: dict[str, str] | None = None) -> Config:
        environ = os.environ if env is None else env
        # Глубокая копия: наложение env не должно править словарь вызывающего.
        merged = copy.deepcopy(raw)
        for name, path in ENV_OVERRIDES.items():
            value = environ.get(name)
            if value is not None and value != "":
                _deep_set(merged, path, value)
        return cls.model_validate(merged)

    # -- проверки перед стартом -------------------------------------------

    def problems(self) -> tuple[list[str], list[str]]:
        """(ошибки, предупреждения). Ошибка — не стартуем вообще."""
        errors: list[str] = []
        warnings: list[str] = []

        if is_placeholder(self.grok.key):
            errors.append(
                "grok.api_key не задан (или остался плейсхолдером) — "
                "без него не работает ни один агент, включая dry-run"
            )
        for name in ("fast_model", "checker_model"):
            if not getattr(self.grok, name).strip():
                errors.append(f"grok.{name} пустой")
        if self.grok.timeout_seconds <= 0:
            errors.append("grok.timeout_seconds должен быть больше нуля")
        if self.grok.max_retries < 1:
            errors.append("grok.max_retries должен быть не меньше 1")

        risk = self.risk
        if risk.max_sol_per_trade <= 0:
            errors.append("risk.max_sol_per_trade должен быть больше нуля")
        if risk.daily_loss_limit_sol <= 0:
            errors.append("risk.daily_loss_limit_sol должен быть больше нуля")
        if risk.max_trades_per_day < 1:
            errors.append("risk.max_trades_per_day должен быть не меньше 1")
        if risk.max_open_positions < 1:
            errors.append("risk.max_open_positions должен быть не меньше 1")
        if not 0 < risk.stop_loss_pct < 100:
            errors.append("risk.stop_loss_pct должен быть в интервале (0, 100)")
        if risk.stop_loss_poll_seconds <= 0:
            errors.append("risk.stop_loss_poll_seconds должен быть больше нуля")
        if risk.take_profit_pct < 0:
            errors.append("risk.take_profit_pct не может быть отрицательным")
        if not 0 <= risk.trailing_stop_pct < 100:
            errors.append("risk.trailing_stop_pct должен быть в интервале [0, 100)")
        if risk.max_hold_seconds < 0:
            errors.append("risk.max_hold_seconds не может быть отрицательным")
        if risk.take_profit_pct and risk.take_profit_pct <= risk.stop_loss_pct:
            warnings.append(
                f"take_profit_pct ({risk.take_profit_pct}) не больше stop_loss_pct "
                f"({risk.stop_loss_pct}) — на такой асимметрии выигрышная серия "
                "не покроет проигрышную"
            )

        flt = self.filter
        if not 0.0 <= flt.min_total_score <= 1.0:
            errors.append("filter.min_total_score должен быть в интервале [0, 1]")
        if not 0.0 < flt.max_curve_progress <= 1.0:
            errors.append("filter.max_curve_progress должен быть в интервале (0, 1]")
        if not 0.0 <= flt.max_risk_score <= 10.0:
            errors.append("filter.max_risk_score должен быть в интервале [0, 10]")
        if flt.min_age_seconds < 0:
            errors.append("filter.min_age_seconds не может быть отрицательным")
        if not 0 < flt.rug_loss_pct <= 100:
            errors.append("filter.rug_loss_pct должен быть в интервале (0, 100]")
        if flt.block_creator_after_rugs < 0:
            errors.append("filter.block_creator_after_rugs не может быть отрицательным")

        weights = self.scoring.weights
        if sum(max(0.0, w) for w in weights.model_dump().values()) <= 0:
            errors.append("все веса scoring.weights нулевые или отрицательные")

        unknown = [e for e in self.alerts.events if e not in ALERT_EVENTS]
        if unknown:
            errors.append(
                f"alerts.events: неизвестные события {unknown}; "
                f"допустимы {sorted(ALERT_EVENTS)}"
            )
        if self.alerts.max_per_minute < 1:
            errors.append("alerts.max_per_minute должен быть не меньше 1")

        if self.ops.max_grok_calls_per_day < 1:
            errors.append("ops.max_grok_calls_per_day должен быть не меньше 1")
        if self.ops.grok_max_concurrency < 1:
            errors.append("ops.grok_max_concurrency должен быть не меньше 1")

        if self.is_live:
            if is_placeholder(self.solana.wallet_key):
                errors.append("mode: live, но solana.wallet_private_key не задан")
            if not self.solana.rpc_url.startswith("https://"):
                errors.append("solana.rpc_url в live должен быть https")
            if risk.max_sol_per_trade > 5.0:
                warnings.append(
                    f"risk.max_sol_per_trade = {risk.max_sol_per_trade} SOL — "
                    "крупно для мемкоина на кривой, перепроверьте"
                )

        if is_placeholder(self.data.key):
            warnings.append(
                "data.api_key не задан — публичный эндпоинт отдаёт данные с "
                "лимитами, на потоке будут пропуски"
            )
        if flt.min_total_score < 0.5:
            warnings.append(
                f"filter.min_total_score = {flt.min_total_score} — низкий порог, "
                "до чекера дойдёт заметно больше токенов и вырастет расход"
            )
        return errors, warnings

    def check_ready(self) -> list[str]:
        """Бросить ConfigError, если стартовать нельзя. Вернуть предупреждения."""
        errors, warnings = self.problems()
        if errors:
            raise ConfigError(
                "конфиг не годится для запуска:\n  - " + "\n  - ".join(errors)
            )
        return warnings

    # -- вывод -------------------------------------------------------------

    def redacted(self) -> dict[str, Any]:
        """Дамп конфига, безопасный для лога: секреты замаскированы."""
        data = self.model_dump(mode="json")
        data["grok"]["api_key"] = mask(self.grok.key)
        data["data"]["api_key"] = mask(self.data.key)
        data["solana"]["wallet_private_key"] = mask(self.solana.wallet_key)
        data["alerts"]["webhook_url"] = mask(self.alerts.webhook_url.get_secret_value())
        return data

    def summary(self) -> str:
        """Одна строка для стартового лога."""
        return (
            f"mode={self.mode} "
            f"grok={self.grok.fast_model}/{self.grok.checker_model} "
            f"key={mask(self.grok.key)} "
            f"risk={self.risk.max_sol_per_trade}SOL/сделка "
            f"limit={self.risk.daily_loss_limit_sol}SOL/день "
            f"score>={self.filter.min_total_score} "
            f"state={self.ops.state_path}"
        )
