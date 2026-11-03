"""QLT-03: ruff C901, PLR0912 and PLR0915 are enforced; the legacy complexity baseline shrinks.

D-14: the baseline is the per-file C901 ignore list in pyproject's ruff per-file-ignores. It was
measured after the hotspot splits (11-04, 11-06 to 11-09): no hotspot successor is in it. Every
new file must pass C901, PLR0912 and PLR0915 without an entry, so a v4 package is outside the
baseline from its first commit. Entries may be removed as files are simplified, never added.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
RATCHET_CODES = frozenset({"C901", "PLR0912", "PLR0915"})
MAX_COMPLEXITY = 10

LEGACY_C901_BASELINE = frozenset(
    {
        "ci/gates/check_desk_integrity.py",
        "ci/gates/check_receipt.py",
        "ci/gates/check_secrets.py",
        "ci/tests/test_gates.py",
        "scripts/generate-event-schemas.py",
        "scripts/generate-templates.py",
        "services/desk-gateway/src/desk_gateway/server.py",
        "src/pumpgrok/engine/agents/base.py",
        "src/pumpgrok/engine/monitor.py",
        "src/pumpgrok/replay/runner.py",
        "src/pumpgrok/risk/breakers.py",
        "src/pumpgrok/supervisor/metrics.py",
        "src/pumpgrok/tools/onchain/large_transfers.py",
        "src/pumpgrok/tools/risk/halt_status.py",
        "tests/docs/test_runbook_commands.py",
        "tests/harness/faults.py",
        "tests/risk/test_check_order_caps.py",
        "tests/safety/test_import_graph_no_live.py",
        "tests/safety/test_money_types.py",
        "tests/safety/test_no_eval_or_shell.py",
        "tests/safety/test_static_guards.py",
        "tests/tools/onchain/test_onchain_reads.py",
    }
)

HOTSPOT_SUCCESSORS = frozenset(
    {
        "src/pumpgrok/execution/paper_adapter/sell.py",
        "src/pumpgrok/execution/paper_adapter/sell_stages.py",
        "src/pumpgrok/execution/paper_adapter/batch.py",
        "src/pumpgrok/execution/paper_adapter/batch_stages.py",
        "src/pumpgrok/execution/paper_adapter/confirm.py",
        "src/pumpgrok/execution/paper_adapter/confirm_stages.py",
        "src/pumpgrok/risk/engine/core.py",
        "src/pumpgrok/risk/engine/rules.py",
        "src/pumpgrok/cli/backtest.py",
        "src/pumpgrok/cli/backtest_holdout.py",
        "src/pumpgrok/cli/backtest_paper_gate.py",
        "src/pumpgrok/config/settings.py",
        "src/pumpgrok/config/sections/core.py",
        "src/pumpgrok/supervisor/seat_task.py",
        "src/pumpgrok/supervisor/seat_restart.py",
        "src/pumpgrok/supervisor/seat_relay.py",
    }
)


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _ruff_lint() -> dict:
    return _pyproject()["tool"]["ruff"]["lint"]


def _per_file_ignores() -> dict[str, list[str]]:
    return _ruff_lint().get("per-file-ignores", {})


def _baseline_paths() -> frozenset[str]:
    return frozenset(path for path, codes in _per_file_ignores().items() if "C901" in codes)


def test_ruff_selects_the_three_complexity_rules() -> None:
    selected = set(_ruff_lint()["select"])
    assert selected >= RATCHET_CODES, f"missing {sorted(RATCHET_CODES - selected)}"


def test_mccabe_threshold_is_declared_at_or_below_ten() -> None:
    threshold = _ruff_lint()["mccabe"]["max-complexity"]
    assert 0 < threshold <= MAX_COMPLEXITY


def test_only_c901_has_a_legacy_baseline() -> None:
    ignored = {
        code for codes in _per_file_ignores().values() for code in codes if code in RATCHET_CODES
    }
    assert ignored <= {"C901"}, f"baseline for {sorted(ignored - {'C901'})} must stay empty"


def test_c901_baseline_only_shrinks() -> None:
    current = _baseline_paths()
    grown = sorted(current - LEGACY_C901_BASELINE)
    assert not grown, f"new C901 baseline entries are not allowed (D-14): {grown}"


def test_c901_baseline_is_lowered_when_entries_are_fixed() -> None:
    current = _baseline_paths()
    fixed = sorted(LEGACY_C901_BASELINE - current)
    assert not fixed, f"remove fixed entries from both pyproject and this test: {fixed}"


def test_baseline_entries_exist_on_disk() -> None:
    gone = sorted(path for path in _baseline_paths() if not (REPO_ROOT / path).is_file())
    assert not gone, f"baseline entries point at missing files: {gone}"


def test_hotspot_successors_are_outside_the_baseline() -> None:
    inside = sorted(HOTSPOT_SUCCESSORS & _baseline_paths())
    assert not inside, f"split successors must pass C901 without an entry: {inside}"
