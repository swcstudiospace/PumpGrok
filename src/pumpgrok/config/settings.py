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
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

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
    """How a secret may appear in logs: recognisable, not usable."""
    if not secret:
        return "<empty>"
    if len(secret) <= 8:
        return "***"
    return f"{secret[:4]}...{secret[-4:]} ({len(secret)} chars)"


class RiskBudget(BaseModel):
    """Risk limits. Money elsewhere is int; ratios here are Decimal (R28)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_trade_fraction: Decimal = Field(default=Decimal("0.02"), ge=0, le=1)
    max_token_fraction: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    # INV-C-06: the daily loss halt can never exceed 0.05.
    daily_loss_halt_fraction: Decimal = Field(default=Decimal("0.05"), ge=0, le=Decimal("0.05"))
    drawdown_halt_fraction: Decimal = Field(default=Decimal("0.15"), ge=0, le=1)
    max_open_positions: int = Field(default=3, ge=0)
    max_trades_per_day: int = Field(default=20, ge=0)
    liquidity_floor_multiple: int = Field(default=10, ge=1)
    partial_fill_fraction: Decimal = Field(default=Decimal("0.02"), gt=0, le=1)


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
    replay: ReplaySettings = Field(default_factory=ReplaySettings)
    live: LiveSettings = Field(default_factory=LiveSettings)

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


def allowed_env_names() -> set[str]:
    """Every PUMPGROK_* name the loader accepts, upper-cased."""
    names = {"PUMPGROK_PROFILE", "PUMPGROK_CONFIG"}

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
    or validation fails.
    """
    problems = collect_startup_problems(os.environ)
    if problems:
        raise ConfigError(problems)
    try:
        return Settings(**kwargs)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from exc


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
