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
import tomllib
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel, Field, SecretStr, ValidationError
from pydantic_settings import (
    BaseSettings,
    EnvSettingsSource,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    SettingsError,
    TomlConfigSettingsSource,
)

from pumpgrok.config.sections.core import (
    KEY_BEARING_VALUE_RE,
    ConfigError,
    DataSettings,
    ExecutionSettings,
    GrokSettings,
    JupiterSettings,
    LiveSettings,
    Mode,
    PlatformSettings,
    ReplaySettings,
    RpcSettings,
    WalletSettings,
)
from pumpgrok.config.sections.engine import (
    ExitsSettings,
    FilterSettings,
    SafetySettings,
    SafetyThresholds,
    ScoringSettings,
    ScoringWeights,
)
from pumpgrok.config.sections.ops import HealthSettings, NotifySettings, OpsSettings
from pumpgrok.config.sections.v4 import (
    BacktestV2Settings,
    DatafeedSettings,
    EventsSettings,
    GrokGatewaySettings,
    PaperFeesSettings,
    PromotionSettings,
    RecorderSettings,
    RiskStrategySettings,
    SignerSettings,
    StrategiesSettings,
)
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.risk.limits import EngineLimits

__all__ = [
    "KEY_BEARING_VALUE_RE",
    "BacktestV2Settings",
    "ConfigError",
    "DataSettings",
    "DatafeedSettings",
    "EventsSettings",
    "ExecutionSettings",
    "ExitsSettings",
    "FilterSettings",
    "GrokGatewaySettings",
    "GrokSettings",
    "HealthSettings",
    "JupiterSettings",
    "LiveSettings",
    "Mode",
    "NotifySettings",
    "OpsSettings",
    "PaperFeesSettings",
    "PlatformSettings",
    "PromotionSettings",
    "RecorderSettings",
    "ReplaySettings",
    "RiskStrategySettings",
    "RpcSettings",
    "SafetySettings",
    "SafetyThresholds",
    "ScoringSettings",
    "ScoringWeights",
    "SignerSettings",
    "StrategiesSettings",
    "WalletSettings",
]


OVERLAY_PROFILES: tuple[str, str, str, str] = ("dev", "paper", "live", "paper-event")
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


def mask(secret: str) -> str:
    """How a secret may appear in logs: its length, never any of its characters."""
    if not secret:
        return "<empty>"
    return f"*** ({len(secret)} chars)"


def _toml_files() -> list[Path]:
    """Overlay for the active profile, then PUMPGROK_CONFIG (later file wins)."""
    files = [overlay_path(current_profile())]
    config_file = os.environ.get("PUMPGROK_CONFIG", "").strip()
    if config_file:
        files.append(Path(config_file))
    return files


_WALLET_KEY = "wallet"
_WALLET_ENV = "PUMPGROK_WALLET"


def _without_wallet(data: Mapping[str, Any]) -> dict[str, Any]:
    """Copy of a source mapping with the wallet section removed."""
    return {key: value for key, value in data.items() if key != _WALLET_KEY}


class _EnvWithoutWallet(EnvSettingsSource):
    """Env source that never loads PUMPGROK_WALLET or any PUMPGROK_WALLET__* name.

    The names are dropped before pydantic-settings decodes them, so a malformed wallet value
    on the paper path is never parsed.
    """

    def _load_env_vars(self) -> Mapping[str, str | None]:
        loaded = super()._load_env_vars()
        wallet = _WALLET_ENV.lower()
        return {
            name: value
            for name, value in loaded.items()
            if name.lower() != wallet and not name.lower().startswith(wallet + "__")
        }


class _TomlWithoutWallet(TomlConfigSettingsSource):
    def __call__(self) -> dict[str, Any]:
        return _without_wallet(super().__call__())


class _ModeProbe(BaseSettings):
    """Effective mode only. It declares no wallet field, so it cannot read the wallet input."""

    model_config = SettingsConfigDict(
        env_prefix="PUMPGROK_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    mode: Mode | None = Field(default=None)
    execution: ExecutionSettings = Field(default_factory=ExecutionSettings)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=_toml_files()),
        )

    def resolved(self) -> Mode:
        """Same precedence as Settings.effective_mode: init/env mode, then TOML execution.mode."""
        return self.mode if self.mode is not None else self.execution.mode


def resolve_effective_mode(**init_kwargs: Any) -> Mode | None:
    """Effective mode, resolved before any wallet input is read.

    Precedence: init kwarg > PUMPGROK_MODE > TOML (top-level mode, then execution.mode).
    Returns None when the mode cannot be resolved. Callers must treat None as not paper, so
    the wallet input is validated (fail closed).
    """
    try:
        return _ModeProbe(**init_kwargs).resolved()
    except (ValidationError, SettingsError):
        return None


def confirm_wallet_allowlist(allowlist: Sequence[str], read_line: Callable[[str], str]) -> None:
    """Operator retypes each allowlist address, in order; any other answer refuses.

    Nothing is confirmed automatically. The prompt and the refusal name the entry index only,
    never the address or what was typed.
    """
    for index, entry in enumerate(allowlist):
        try:
            typed = read_line(f"Retype wallet allowlist entry {index} to confirm it: ")
        except EOFError:
            typed = ""
        if typed.strip() != entry:
            raise ConfigError([f"allowlist entry {index} was not confirmed by retyping it"])


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
    platform: PlatformSettings = Field(default_factory=PlatformSettings)
    wallet: WalletSettings = Field(default_factory=WalletSettings)
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
    events: EventsSettings = Field(default_factory=EventsSettings)
    grok_gateway: GrokGatewaySettings = Field(default_factory=GrokGatewaySettings)
    datafeed: DatafeedSettings = Field(default_factory=DatafeedSettings)
    recorder: RecorderSettings = Field(default_factory=RecorderSettings)
    strategies: StrategiesSettings = Field(default_factory=StrategiesSettings)
    backtest_v2: BacktestV2Settings = Field(default_factory=BacktestV2Settings)
    risk_strategy: RiskStrategySettings = Field(default_factory=RiskStrategySettings)
    promotion: PromotionSettings = Field(default_factory=PromotionSettings)
    signer: SignerSettings = Field(default_factory=SignerSettings)
    paper_fees: PaperFeesSettings = Field(default_factory=PaperFeesSettings)

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
        init_kwargs = (
            init_settings.init_kwargs if isinstance(init_settings, InitSettingsSource) else None
        )
        files = _toml_files()
        if init_kwargs is not None and resolve_effective_mode(**init_kwargs) == "paper":
            # Paper never reads the wallet: wallet input is dropped before it is decoded.
            return (
                InitSettingsSource(settings_cls, init_kwargs=_without_wallet(init_kwargs)),
                _EnvWithoutWallet(settings_cls),
                _TomlWithoutWallet(settings_cls, toml_file=files),
            )
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
# by the live gate (precondition 2; env-only, never a TOML key),
# PUMPGROK_KILLSWITCH by the kill switch (read once at process start, R22),
# PUMPGROK_TELEGRAM_TOKEN by the Telegram notify sink (env-only and optional:
# unset means Telegram is not configured and never blocks startup),
# PUMPGROK_PAID_RPC_PROVIDER by the safety provider (env-only and optional:
# unset or empty means no paid RPC provider is recorded),
# PUMPGROK_STATE_DIR by the hosted state directory (HOST-01: absolute only),
# PUMPGROK_LOG_LEVEL by the log config (HOST-08: DEBUG|INFO|WARNING|ERROR).
NON_SETTING_ENV_NAMES = frozenset(
    {
        "PUMPGROK_PROFILE",
        "PUMPGROK_CONFIG",
        "PUMPGROK_LOG_JSON",
        "PUMPGROK_LIVE_ENABLE",
        "PUMPGROK_KILLSWITCH",
        "PUMPGROK_CONFIRMATION_KEY",
        "PUMPGROK_TELEGRAM_TOKEN",  # pragma: allowlist secret: env var name, not a credential
        "PUMPGROK_PAID_RPC_PROVIDER",
        "PUMPGROK_STATE_DIR",
        "PUMPGROK_LOG_LEVEL",
    }
)

#: Log levels accepted by PUMPGROK_LOG_LEVEL (HOST-08).
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def valid_log_level(value: str) -> bool:
    """HOST-08: only the four named levels are accepted."""
    return value in LOG_LEVELS


def state_root(environ: Mapping[str, str] | None = None) -> Path | None:
    """Absolute state directory from PUMPGROK_STATE_DIR, or None when unset."""
    env = os.environ if environ is None else environ
    raw = env.get("PUMPGROK_STATE_DIR", "").strip()
    return Path(raw) if raw else None


def resolve_state_path(*parts: str, environ: Mapping[str, str] | None = None) -> Path:
    """Resolve a runtime path under the state root; relative base when unset."""
    base = state_root(environ)
    rel = Path(*parts)
    if base is None:
        return rel
    if rel.is_absolute():
        return rel
    return base / rel


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


def _walk_keys(data: Any, prefix: str) -> Iterator[str]:
    """Yield the dotted path of every table key in decoded TOML."""
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path
            yield from _walk_keys(value, path)


def _secret_setting_paths(model: type[BaseModel] = Settings, prefix: str = "") -> set[str]:
    """Dotted paths of every SecretStr setting; these arrive via env only."""
    paths: set[str] = set()
    for field_name, field in model.model_fields.items():
        path = f"{prefix}{field_name}"
        if SecretStr in [field.annotation, *get_args(field.annotation)]:
            paths.add(path)
        sub = _nested_model(field.annotation)
        if sub is not None:
            paths |= _secret_setting_paths(sub, path + ".")
    return paths


def find_key_bearing_toml(files: Sequence[Path]) -> list[str]:
    """Report secret settings and key-bearing URL values inside TOML files (paths only)."""
    bad: list[str] = []
    secret_paths = _secret_setting_paths()
    for file in files:
        try:
            with file.open("rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            bad.append(f"unreadable config file: {file} ({type(exc).__name__})")
            continue
        for path in _walk_keys(data, ""):
            if path in secret_paths:
                bad.append(f"secret setting refused in config file: {file.name}:{path}")
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

    if "PUMPGROK_STATE_DIR" in present:
        raw_state = (environ.get("PUMPGROK_STATE_DIR") or "").strip()
        if not raw_state or not Path(raw_state).is_absolute():
            problems.append(
                "refused environment variable: PUMPGROK_STATE_DIR "
                "(must be a non-empty absolute path)"
            )
    if "PUMPGROK_LOG_LEVEL" in present:
        raw_level = (environ.get("PUMPGROK_LOG_LEVEL") or "").strip()
        if not valid_log_level(raw_level):
            problems.append(
                "refused environment variable: PUMPGROK_LOG_LEVEL "
                f"(expected one of: {', '.join(LOG_LEVELS)})"
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
        raise ConfigError(_format_validation_error(exc)) from None


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
