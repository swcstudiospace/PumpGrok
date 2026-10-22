"""Layered application settings.

Precedence, highest wins: CLI init kwargs > ``PUMPGROK_*`` env vars >
``PUMPGROK_CONFIG`` operator TOML > overlay TOML selected by
``PUMPGROK_PROFILE`` (default ``paper``) > builtin defaults.

Effective mode precedence: init ``mode`` > ``PUMPGROK_MODE`` env >
TOML ``execution.mode``.

Startup guards (pydantic-settings does not provide these): unknown
``PUMPGROK_*`` names are refused, ``PUMPGROK_EXECUTION`` /
``PUMPGROK_EXECUTION__MODE`` are refused outright, env names carrying
forbidden secret-like substrings are refused, key-bearing URL values are
refused, and pydantic ``ValidationError`` details are reformatted to
(location, type) pairs so rejected values never reach logs. Every failure
raises :class:`ConfigError`; the CLI maps it to exit 1.

There is intentionally no wallet key field and no Jito field anywhere in
this model (STRUCT-008). Secrets arrive only as ``PUMPGROK_*`` env vars at
run time; ``.env`` files are never read (compose ``env_file`` injects into
the process environment instead).
"""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.risk.limits import EngineLimits


class DataSettings(BaseModel):
    """Pump.fun REST plus PumpPortal websocket ingress (D8)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rest_url: str = "https://frontend-api.pump.fun"
    ws_url: str = "wss://pumpportal.fun/api/data"
    ws_max_queue: int = Field(default=16, ge=1)
    request_timeout: float = 10.0


class RpcSettings(BaseModel):
    """Solana JSON-RPC failover list. Endpoints are keyless URLs only.

    Paid-provider keys travel in ``api_key`` and are sent as a header;
    key-bearing endpoint values are refused at startup (T-02-01).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    endpoints: list[str] = Field(default_factory=lambda: ["https://api.mainnet-beta.solana.com"])
    api_key: SecretStr = SecretStr("")


class GrokSettings(BaseModel):
    """x.ai chat completions (R48). Secrets arrive via env only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str = "https://api.x.ai/v1"
    strong_model: str = "grok-4.3"
    strong_effort: str = "low"
    fast_model: str = "grok-4.20-0309-non-reasoning"
    api_key: SecretStr = SecretStr("")


class JupiterSettings(BaseModel):
    """Jupiter Swap V2 quote endpoint, informational only (R44, R38)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    quote_url: str = "https://api.jup.ag/swap/v2/order"


class FilterSettings(BaseModel):
    """Launch-monitor admission gates (vendor FilterConfig, ASCII codes)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    min_unique_buyers: int = Field(default=5, ge=0)
    max_curve_progress: float = Field(default=0.40, ge=0)
    require_metadata: bool = True
    min_age_seconds: float = Field(default=120.0, ge=0)
    max_risk_score: float = Field(default=7.0, ge=0)
    min_total_score: float = Field(default=0.65, ge=0)
    block_creator_after_rugs: int = Field(default=1, ge=0)
    rug_loss_pct: float = Field(default=60.0, ge=0)
    one_position_per_creator: bool = True
    forget_creators_after_days: float = Field(default=30.0, ge=0)


class ScoringWeights(BaseModel):
    """Component weights; must sum to 1 downstream (vendor ScoringWeights)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    audit: float = 0.30
    narrative: float = 0.25
    timing: float = 0.15
    metrics: float = 0.30


class ScoringSettings(BaseModel):
    """Engine scoring knobs (vendor ScoringConfig)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    timing_cache_seconds: float = Field(default=900.0, ge=0)


class ExitsSettings(BaseModel):
    """Exit-rule thresholds. Separate from ``risk`` (Pitfall 15, R20)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stop_loss_pct: float = Field(default=30.0, ge=0)
    take_profit_pct: float = Field(default=120.0, ge=0)
    trailing_stop_pct: float = Field(default=35.0, ge=0)
    max_hold_seconds: float = Field(default=3600.0, ge=0)
    stop_loss_poll_seconds: float = Field(default=15.0, ge=0)


class SafetyThresholds(BaseModel):
    """Score-report check thresholds (TOOL-003; REVIEW defaults from agents/risk.md)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transfer_tax_hard_fail_pct: float = Field(default=10.0, ge=0)
    transfer_tax_warn_pct: float = Field(default=5.0, ge=0)
    top10_concentration_warn_pct: float = Field(default=20.0, ge=0)
    top10_concentration_fail_pct: float = Field(default=25.0, ge=0)
    liquidity_multiple_min: float = Field(default=10.0, ge=0)
    liquidity_multiple_recommended: float = Field(default=20.0, ge=0)
    lp_lock_min_days: float = Field(default=180.0, ge=0)
    creator_share_veto: float = Field(default=0.25, ge=0)
    top5_share_veto: float = Field(default=0.80, ge=0)
    kill_below_score: float = Field(default=40.0, ge=0)
    conditional_below_score: float = Field(default=70.0, ge=0)


class SafetySettings(BaseModel):
    """Safety scoring knobs (TOOL-003). Secrets never live here (STRUCT-008)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    thresholds: SafetyThresholds = Field(default_factory=SafetyThresholds)


class OpsSettings(BaseModel):
    """Process-lifetime state paths (vendor OpsConfig subset, Phase 2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reputation_path: str = "var/reputation.json"


class NotifySettings(BaseModel):
    """Human alert destinations (TOOL-006, R39).

    ``allowlist`` holds Telegram chat ids and webhook URLs; empty means
    stdout and file only. The Telegram token travels via env
    ``PUMPGROK_TELEGRAM_TOKEN`` only, never TOML and never this model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    allowlist: list[str] = Field(default_factory=list)


Mode = Literal["paper", "live"]

OVERLAY_PROFILES: tuple[str, str, str] = ("dev", "paper", "live")
DEFAULT_PROFILE = "paper"

# Mirrors hermes/profiles.yaml forbidden_env_keys, extended with the
# vendor GROKBOT_WALLET_PRIVATE_KEY shape and common KEYPAIR names.
# Matched case-insensitively against the full env name.
FORBIDDEN_SUBSTRINGS = (
    "PRIVATE_KEY",
    "SECRET_KEY",
    "SEED",
    "MNEMONIC",
    "PHANTOM",
    "WALLET_SECRET",
    "KEYPAIR",
)

# The one env name allowed to contain a forbidden substring.
EXEMPT_ENV_NAMES = frozenset({"PUMPGROK_REPLAY__SEED"})

# Declared setting paths that must never be set via env: mode flows only
# through init kwargs (CLI --mode), top-level PUMPGROK_MODE, or TOML.
REFUSED_ENV_NAMES = frozenset({"PUMPGROK_EXECUTION", "PUMPGROK_EXECUTION__MODE"})

# A value shaped like a URL carrying a secret (api-key=, token=, key=).
# The key= alternative requires a non-identifier char before it so that
# innocent words containing "key" (e.g. monkey=) do not match.
KEY_BEARING_VALUE_RE = re.compile(r"(?i)(?:api-key=|token=|(?<![A-Za-z_-])key=)")


class ConfigError(RuntimeError):
    """Settings are not fit to start. The list of problems is the argument."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__(
            "settings are not fit to start:\n"
            + "\n".join(f"- {problem}" for problem in self.problems)
        )


def mask(secret: str) -> str:
    """How a secret may appear in logs: its length, never any of its characters."""
    if not secret:
        return "<empty>"
    return f"*** ({len(secret)} chars)"


class ExecutionSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Mode = "paper"


class ReplaySettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int = 20260101


class LiveSettings(BaseModel):
    """Marker only: enabling live requires the live gate (separate module)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False

class HealthSettings(BaseModel):
    """Health server bind port (INV-C-11).

    Default 0 (disabled: never bind a socket under test or --once/--replay).
    The container sets PUMPGROK_HEALTH__PORT=8080 via compose (plan 07);
    --once/--replay forces 0 through health_port() regardless of this value.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    port: int = 0


class Settings(BaseSettings):
    """Merged application settings. Build via load_settings(), not directly."""

    model_config = SettingsConfigDict(
        env_prefix="PUMPGROK_",
        env_nested_delimiter="__",
        extra="forbid",
    )

    # Top-level PUMPGROK_MODE. None means "not set"; resolution order is
    # handled by effective_mode (init kwarg > env > TOML execution.mode).
    mode: Mode | None = Field(default=None)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)
    risk: RiskBudget = Field(default_factory=RiskBudget)
    limits: EngineLimits = Field(default_factory=EngineLimits)
    replay: ReplaySettings = Field(default_factory=ReplaySettings)
    live: LiveSettings = Field(default_factory=LiveSettings)
    data: DataSettings = Field(default_factory=DataSettings)
    rpc: RpcSettings = Field(default_factory=RpcSettings)
    grok: GrokSettings = Field(default_factory=GrokSettings)
    jupiter: JupiterSettings = Field(default_factory=JupiterSettings)
    filter: FilterSettings = Field(default_factory=FilterSettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)
    scoring: ScoringSettings = Field(default_factory=ScoringSettings)
    exits: ExitsSettings = Field(default_factory=ExitsSettings)
    ops: OpsSettings = Field(default_factory=OpsSettings)
    notify: NotifySettings = Field(default_factory=NotifySettings)
    health: HealthSettings = Field(default_factory=HealthSettings)

    @property
    def effective_mode(self) -> Mode:
        """Resolve the mode: init kwarg (CLI) > PUMPGROK_MODE > TOML."""
        if os.environ.get("PUMPGROK_MODE", "").strip():
            # Env is set, so pydantic parsed it into self.mode already.
            assert self.mode is not None
            return self.mode
        if self.mode is not None:
            # No env: a non-default value can only come from init (CLI).
            return self.mode
        return self.execution.mode

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Source order: init > env > TOML files (later file wins).

        TOML files are [overlay(PUMPGROK_PROFILE, default paper),
        PUMPGROK_CONFIG file]. dotenv/file-secret sources are
        intentionally excluded: secrets arrive via the environment.
        """
        files = [overlay_path(current_profile())]
        config_file = os.environ.get("PUMPGROK_CONFIG", "").strip()
        if config_file:
            files.append(Path(config_file))
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=files),
        )


def current_profile(environ: Mapping[str, str] | None = None) -> str:
    """Overlay profile name from the environment; defaults to paper."""
    env = os.environ if environ is None else environ
    return env.get("PUMPGROK_PROFILE", "").strip() or DEFAULT_PROFILE


def overlay_path(profile: str) -> Path:
    """In-package overlay for a profile; raises ConfigError when unknown."""
    name = profile.strip() or DEFAULT_PROFILE
    if name not in OVERLAY_PROFILES:
        raise ConfigError(
            [f"unknown PUMPGROK_PROFILE: {name} (expected one of: {', '.join(OVERLAY_PROFILES)})"]
        )
    return Path(__file__).resolve().parent / "overlays" / f"{name}.toml"


def _nested_model(annotation: Any) -> type[BaseModel] | None:
    """Unwrap Optional[...] to the BaseModel subclass, if there is one."""
    candidates: list[Any] = [annotation, *get_args(annotation)]
    for candidate in candidates:
        if isinstance(candidate, type) and issubclass(candidate, BaseModel):
            return candidate
    return None


# PUMPGROK_* names read outside the Settings model: PUMPGROK_LOG_JSON by the
# logging setup (honoured only under the dev profile), PUMPGROK_LIVE_ENABLE
# by the live gate (precondition 2; env-only, never a TOML key), and
# PUMPGROK_KILLSWITCH by the kill switch (read once at process start, R22).
NON_SETTING_ENV_NAMES = frozenset(
    {
        "PUMPGROK_PROFILE",
        "PUMPGROK_CONFIG",
        "PUMPGROK_LOG_JSON",
        "PUMPGROK_LIVE_ENABLE",
        "PUMPGROK_KILLSWITCH",
        "PUMPGROK_CONFIRMATION_KEY",
    }
)


def allowed_env_names() -> set[str]:
    """Every PUMPGROK_* name the loader accepts, upper-cased."""
    names = set(NON_SETTING_ENV_NAMES)

    def visit(model: type[BaseModel], prefix: str) -> None:
        for field_name, field in model.model_fields.items():
            env_name = f"{prefix}{field_name}".upper()
            names.add(env_name)
            sub = _nested_model(field.annotation)
            if sub is not None:
                visit(sub, env_name + "__")

    visit(Settings, "PUMPGROK_")
    return names


def refuse_forbidden_env(environ: Mapping[str, str]) -> list[str]:
    """Report env names (never values) carrying forbidden substrings."""
    bad: list[str] = []
    for name in environ:
        if name.upper() in EXEMPT_ENV_NAMES:
            continue
        if any(fragment in name.upper() for fragment in FORBIDDEN_SUBSTRINGS):
            bad.append(f"forbidden environment variable name: {name}")
    return bad


def find_unknown_env(environ: Mapping[str, str], allowed: set[str]) -> list[str]:
    """Report PUMPGROK_* names with no declared setting (typos fail loudly)."""
    bad: list[str] = []
    for name in environ:
        upper = name.upper()
        if not upper.startswith("PUMPGROK_"):
            continue
        if upper in allowed:
            continue
        bad.append(f"unknown setting: {name}")
    return bad


def find_key_bearing_env(environ: Mapping[str, str]) -> list[str]:
    """Report PUMPGROK_* values shaped like key-bearing URLs (names only)."""
    bad: list[str] = []
    for name, value in environ.items():
        if not name.upper().startswith("PUMPGROK_"):
            continue
        if KEY_BEARING_VALUE_RE.search(value):
            bad.append(f"key-bearing value refused: {name}")
    return bad


def _walk_texts(data: Any, prefix: str) -> Iterator[tuple[str, str]]:
    """Yield (dotted path, value) for every string leaf in decoded TOML."""
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _walk_texts(value, path)
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from _walk_texts(value, f"{prefix}[{index}]")
    elif isinstance(data, str):
        yield prefix, data


def find_key_bearing_toml(files: Sequence[Path]) -> list[str]:
    """Report key-bearing URL values inside TOML files (paths only)."""
    bad: list[str] = []
    for file in files:
        try:
            with file.open("rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            bad.append(f"unreadable config file: {file} ({type(exc).__name__})")
            continue
        for path, value in _walk_texts(data, ""):
            if KEY_BEARING_VALUE_RE.search(value):
                bad.append(f"key-bearing value refused: {file.name}:{path}")
    return bad


def collect_startup_problems(environ: Mapping[str, str]) -> list[str]:
    """Run every startup guard; return problem strings (names, never values)."""
    problems: list[str] = []
    problems.extend(refuse_forbidden_env(environ))

    present = {name.upper(): name for name in environ}
    for refused in sorted(REFUSED_ENV_NAMES):
        if refused in present:
            problems.append(
                f"refused environment variable: {present[refused]} "
                "(mode is set via PUMPGROK_MODE or --mode, never via execution.* env)"
            )

    allowed = allowed_env_names()
    problems.extend(find_key_bearing_env(environ))
    problems.extend(find_unknown_env(environ, allowed))

    profile = environ.get("PUMPGROK_PROFILE", "").strip() or DEFAULT_PROFILE
    if profile not in OVERLAY_PROFILES:
        problems.append(
            f"unknown PUMPGROK_PROFILE: {profile} (expected one of: {', '.join(OVERLAY_PROFILES)})"
        )
        return problems  # no valid overlay to scan further

    files = [overlay_path(profile)]
    config_file = environ.get("PUMPGROK_CONFIG", "").strip()
    if config_file:
        candidate = Path(config_file)
        if not candidate.is_file():
            problems.append(f"operator overlay not found: {config_file}")
        else:
            files.append(candidate)
    problems.extend(find_key_bearing_toml(files))
    return problems


def _format_validation_error(exc: ValidationError) -> list[str]:
    """Map pydantic errors to (location, type) pairs; inputs are dropped."""
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_context=False, include_input=False):
        loc = ".".join(str(part) for part in error["loc"]) or "<root>"
        problems.append(f"{loc}: {error['type']}")
    return problems


def load_settings(**kwargs: Any) -> Settings:
    """Build Settings after running every startup guard.

    Raises ConfigError (names/locations only, never values) when any guard
    or validation fails. A live effective mode is not refused here: the CLI
    runs the live gate (execution/live/live_gate.py) before any other work.
    """
    problems = collect_startup_problems(os.environ)
    if problems:
        raise ConfigError(problems)
    try:
        return Settings(**kwargs)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from exc


def health_port(settings: Settings, *, once: bool = False, replay: str | None = None) -> int:
    """Effective health server port (INV-C-11).

    ``--once`` and ``--replay`` force 0 (disabled: CI never binds a socket);
    otherwise the configured ``health.port`` applies (container sets
    PUMPGROK_HEALTH__PORT=8080 via compose in plan 07).
    """
    if once or replay:
        return 0
    return settings.health.port


def refuse_cli_secrets(argv: Sequence[str]) -> None:
    """Refuse CLI arguments carrying key-bearing values (flags only).

    Raises ConfigError naming the offending flag, never the value.
    """
    problems: list[str] = []
    for index, arg in enumerate(argv):
        if not KEY_BEARING_VALUE_RE.search(arg):
            continue
        if arg.startswith("-"):
            label = arg.split("=", 1)[0]
        elif index > 0 and argv[index - 1].startswith("-"):
            label = argv[index - 1]
        else:
            label = f"argv[{index}]"
        problems.append(f"key-bearing value refused on CLI: {label}")
    if problems:
        raise ConfigError(problems)
