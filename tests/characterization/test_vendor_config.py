"""Characterization: settings parity with the vendor config (STRUCT-004).

Pins ``config/settings.py``, ``core/risk_budget.py``, and the TOML overlays
against ``vendor/grokbot-pumpfun/src/models.py:318-392`` (``RiskConfig``,
``FilterConfig``, ``ScoringConfig``, ``AlertsConfig``, ``LoggingConfig``,
``OpsConfig``) and ``vendor/grokbot-pumpfun/tests/test_config.py`` (vendor
oracle, kept byte-identical per R53).
- Adaptations from the oracle (deliberate):
-
- Env handling is stricter than the vendor ``from_raw`` overlay: unknown
  ``PUMPGROK_*`` names fail loudly (typos never silently no-op),
  ``PUMPGROK_EXECUTION*`` is refused outright (mode travels via
  ``PUMPGROK_MODE`` or ``--mode``), secret-like env names are refused, and
  key-bearing URL values are refused in env and TOML alike. None of the
  refusal messages carry values.
- Secrets travel only as ``PUMPGROK_*`` env vars at run time (STRUCT-008):
  there is no wallet key field and no ``.env`` loading. ``SecretStr``
  keeps raw values out of ``repr``.
- The nine ``[risk]`` keys load as ``RiskBudget`` (the ONLY risk-budget
  schema, R20): fractions in ``0..1``, ``paper_equity_sol`` converted to
  lamports once, ``daily_loss_halt_fraction`` capped at ``0.05``.
- Exit thresholds live in ``ExitsSettings``, never in ``RiskBudget``
  (R20/Pitfall 15): stuffing an exit key into the budget is a validation
  error.
- The vendor ``dry-run``/``live`` mode pair maps to ``paper``/``live``;
  ``live`` stays a marker the live gate decides on, never a trading switch.
- The vendor default alert set (started/buy/close/rug/breaker/halted/blind)
  maps to an empty ``NotifySettings.allowlist``: alerts stay off until an
  operator names a destination, like the empty vendor webhook URL.
- All prose is English; the vendor text is Russian.
"""

from __future__ import annotations

import os
import tomllib
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from pumpgrok.config.settings import (
    ConfigError,
    ExitsSettings,
    FilterSettings,
    NotifySettings,
    OpsSettings,
    ScoringSettings,
    Settings,
    allowed_env_names,
    find_key_bearing_env,
    find_unknown_env,
    load_settings,
    refuse_forbidden_env,
)
from pumpgrok.core.risk_budget import RiskBudget

OVERLAYS = Path(__file__).resolve().parents[2] / "src" / "pumpgrok" / "config" / "overlays"


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip every PUMPGROK_* var so tests see only what they set."""
    for name in list(os.environ):
        if name.startswith("PUMPGROK_"):
            monkeypatch.delenv(name, raising=False)


def test_key_bearing_url_value_is_refused() -> None:
    name = "PUMPGROK_RPC__ENDPOINTS"
    problems = find_key_bearing_env({name: "https://host/path?api-key=abc123"})
    assert problems != [] and all("abc123" not in p for p in problems)


def test_env_overrides_overlay_default(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_RISK__MAX_TRADES_PER_DAY", "7")
    assert load_settings().risk.max_trades_per_day == 7


def test_env_can_switch_mode(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_MODE", "live")
    assert load_settings().effective_mode == "live"


def test_unknown_env_name_is_refused(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUMPGROK_TYPO_RISK", "1")
    with pytest.raises(ConfigError, match="unknown setting"):
        load_settings()


def test_execution_env_spelling_is_refused(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mode travels via PUMPGROK_MODE, never via execution.* env."""
    monkeypatch.setenv("PUMPGROK_EXECUTION__MODE", "live")
    with pytest.raises(ConfigError, match="refused environment variable"):
        load_settings()


def test_secret_like_env_name_is_refused(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    name = (
        "PUMPGROK_DATA_PRIVATE_KEY"  # pragma: allowlist secret: test placeholder, not a credential
    )
    monkeypatch.setenv(name, "abc")
    assert refuse_forbidden_env({name: "abc"}) != []


def test_declared_names_pass_the_unknown_check() -> None:
    assert find_unknown_env({"PUMPGROK_MODE": "paper"}, allowed_env_names()) == []


# --- secrets ------------------------------------------------------------------


def test_api_key_never_appears_in_repr(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    key = "xai-test-secret-value"  # pragma: allowlist secret: test placeholder, not a credential
    monkeypatch.setenv(
        "PUMPGROK_GROK__API_KEY",  # pragma: allowlist secret: test placeholder, not a credential
        key,
    )
    settings = load_settings()
    assert key not in repr(settings)
    assert key not in repr(settings.grok)
    assert settings.grok.api_key.get_secret_value() == key


def test_rpc_key_never_appears_in_repr(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    key = "rpc-test-secret-value"  # pragma: allowlist secret: test placeholder, not a credential
    monkeypatch.setenv(
        "PUMPGROK_RPC__API_KEY",  # pragma: allowlist secret: test placeholder, not a credential
        key,
    )
    assert key not in repr(load_settings())


# --- risk budget: the nine keys -------------------------------------------------


def test_paper_overlay_carries_eight_risk_keys() -> None:
    with (OVERLAYS / "paper.toml").open("rb") as handle:
        data = tomllib.load(handle)
    assert set(data["risk"]) == {
        "max_trade_fraction",
        "max_token_fraction",
        "daily_loss_halt_fraction",
        "drawdown_halt_fraction",
        "max_open_positions",
        "max_trades_per_day",
        "liquidity_floor_multiple",
        "partial_fill_fraction",
    }


def test_risk_budget_matches_vendor_review_defaults(clean_env: None) -> None:
    budget = load_settings().risk
    assert budget.max_trade_fraction == Decimal("0.02")
    assert budget.max_token_fraction == Decimal("0.05")
    assert budget.daily_loss_halt_fraction == Decimal("0.05")
    assert budget.drawdown_halt_fraction == Decimal("0.15")
    assert budget.max_open_positions == 3
    assert budget.max_trades_per_day == 20
    assert budget.liquidity_floor_multiple == 10
    assert budget.partial_fill_fraction == Decimal("0.02")


def test_paper_equity_converts_to_lamports_once(clean_env: None) -> None:
    budget = load_settings().risk
    assert budget.paper_equity_sol == Decimal("10")
    assert budget.paper_equity_lamports == 10_000_000_000


def test_daily_loss_halt_fraction_is_capped() -> None:
    with pytest.raises(ValidationError, match=r"0\.05"):
        RiskBudget(daily_loss_halt_fraction=Decimal("0.06"))


def test_fractions_stay_within_zero_and_one() -> None:
    with pytest.raises(ValidationError):
        RiskBudget(max_trade_fraction=Decimal("2"))
    with pytest.raises(ValidationError):
        RiskBudget(max_token_fraction=Decimal("-0.01"))


def test_exit_keys_do_not_belong_in_the_budget() -> None:
    """R20/Pitfall 15: exit thresholds live in ExitsSettings, never in RiskBudget."""
    with pytest.raises(ValidationError):
        RiskBudget(stop_loss_pct=30.0)  # type: ignore[call-arg]


# --- engine sections mirror the vendor defaults ----------------------------------


def test_filter_defaults_mirror_vendor() -> None:
    filt = FilterSettings()
    assert filt.min_unique_buyers == 5
    assert filt.max_curve_progress == pytest.approx(0.40)
    assert filt.require_metadata is True
    assert filt.min_age_seconds == pytest.approx(120.0)
    assert filt.max_risk_score == pytest.approx(7.0)
    assert filt.min_total_score == pytest.approx(0.65)
    assert filt.block_creator_after_rugs == 1
    assert filt.one_position_per_creator is True


def test_scoring_weights_sum_to_one() -> None:
    weights = ScoringSettings().weights
    assert (weights.audit, weights.narrative, weights.timing, weights.metrics) == (
        pytest.approx(0.30),
        pytest.approx(0.25),
        pytest.approx(0.15),
        pytest.approx(0.30),
    )
    total = weights.audit + weights.narrative + weights.timing + weights.metrics
    assert total == pytest.approx(1.0)
    assert ScoringSettings().timing_cache_seconds == pytest.approx(900.0)


def test_exit_thresholds_mirror_vendor() -> None:
    exits = ExitsSettings()
    assert exits.stop_loss_pct == pytest.approx(30.0)
    assert exits.take_profit_pct == pytest.approx(120.0)
    assert exits.trailing_stop_pct == pytest.approx(35.0)
    assert exits.max_hold_seconds == pytest.approx(3600.0)
    assert exits.stop_loss_poll_seconds == pytest.approx(15.0)


def test_ops_keeps_restart_state_path() -> None:
    assert OpsSettings().reputation_path == "var/reputation.json"


def test_alerts_stay_off_by_default() -> None:
    """Empty allowlist is the silent default, like the empty vendor webhook URL."""
    assert NotifySettings().allowlist == []


def test_fresh_settings_default_paper_with_live_disabled(clean_env: None) -> None:
    settings = Settings()
    assert settings.effective_mode == "paper"
    assert settings.live.enabled is False
