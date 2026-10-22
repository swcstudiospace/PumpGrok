"""Regression guard for the GitHub workflows and the scanner configs they depend on.

The workflows are YAML, not ci/gates/*.py, so test_gates.py never parses them. A later edit could
quietly drop a blocking flag, reintroduce a self-hosted runner, or interpolate a branch name into
shell source, and the gate suite would stay green. These tests assert what a diff review can miss.

They do not run the scanners (that needs network access and the tools installed).

    python3 -m pytest ci/tests/test_security_workflows.py -v
"""

from __future__ import annotations

import datetime
import importlib.util
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
GITLEAKS_CONFIG = REPO_ROOT / "ci" / "security" / "gitleaks.toml"
BANDIT_SARIF_CONVERTER = REPO_ROOT / "ci" / "security" / "bandit_json_to_sarif.py"
EXCEPTIONS_GATE = REPO_ROOT / "ci" / "security" / "check_exceptions.py"

WORKFLOW_FILES = ["gates.yml", "security-pr.yml", "ci.yml"]

# The bypass snippets G-2 rejects in a receipt, checked in the scanner workflow itself: a step
# that masks its own exit code is the same failure in a different file.
BYPASS_SNIPPETS = ["|| true", "|| exit 0", "2>/dev/null", "--exit-zero", "--dry-run"]

TRADING_GITLEAKS_RULES = [
    "solana-base58-key",
    "solana-json-keypair",
    "helius-rpc-key",
    "quicknode-endpoint-token",
    "telegram-bot-token",
    "xai-api-key",
]


def _load_yaml(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def _trigger(doc: dict) -> dict:
    # YAML 1.1 reads the bare key `on` as boolean True.
    return doc.get("on", doc.get(True))


def _steps(doc: dict) -> list[dict]:
    return [step for job in doc["jobs"].values() for step in job.get("steps", [])]


def _run_blocks(doc: dict) -> list[str]:
    return [step["run"] for step in _steps(doc) if "run" in step]


def _step(doc: dict, name_substring: str) -> dict:
    for step in _steps(doc):
        if name_substring in step.get("name", ""):
            return step
    raise AssertionError(f"no step whose name contains {name_substring!r}")


@pytest.fixture(scope="module")
def security_pr() -> dict:
    return _load_yaml("security-pr.yml")


@pytest.fixture(scope="module")
def gates() -> dict:
    return _load_yaml("gates.yml")


class TestWorkflowsParseAndRunOnHostedRunners:
    @pytest.mark.parametrize("name", WORKFLOW_FILES)
    def test_parses_as_yaml_with_jobs(self, name):
        assert _load_yaml(name)["jobs"]

    @pytest.mark.parametrize("name", WORKFLOW_FILES)
    def test_no_job_uses_a_self_hosted_runner(self, name):
        for job_name, job in _load_yaml(name)["jobs"].items():
            assert job["runs-on"] == "ubuntu-latest", job_name


class TestNoExpressionInterpolationInRunBlocks:
    @pytest.mark.parametrize("name", WORKFLOW_FILES)
    def test_run_blocks_never_interpolate_expressions(self, name):
        # Branch and base-ref names may hold shell metacharacters. They reach a step only
        # through env:, never through ${{ }} inside run:.
        for block in _run_blocks(_load_yaml(name)):
            assert "${{" not in block, block


class TestGatesWorkflow:
    def test_triggers_on_pull_request_and_push_to_main(self, gates):
        trigger = _trigger(gates)
        assert trigger["pull_request"]["branches"] == ["main"]
        assert trigger["push"]["branches"] == ["main"]

    def test_base_ref_overlay_runs_in_both_jobs(self, gates):
        for job_name in ("gates", "gate-self-test"):
            steps = gates["jobs"][job_name]["steps"]
            overlay = [
                s
                for s in steps
                if 'git checkout "origin/$BASE_REF" -- ci/gates/' in s.get("run", "")
            ]
            assert overlay, job_name
            assert overlay[0]["env"]["BASE_REF"] == "${{ github.base_ref || 'main' }}"

    def test_gates_job_runs_g1_through_g7(self, gates):
        names = " | ".join(s.get("name", "") for s in gates["jobs"]["gates"]["steps"])
        for gate in ["G-1", "G-2", "G-3", "G-4", "G-5/G-6", "G-7"]:
            assert gate in names, gate

    def test_acting_bot_is_anchored_to_the_ten_seat_regex(self, gates):
        bot_step = _step(gates, "Determine the acting bot")
        assert r"^bot-0[0-9]-[a-z0-9-]+$" in bot_step["run"]
        assert "bot-0[0-6]" not in bot_step["run"]

    def test_gate_self_test_job_runs_the_gate_suite(self, gates):
        runs = " ".join(s["run"] for s in gates["jobs"]["gate-self-test"]["steps"] if "run" in s)
        assert "python3 -m pytest ci/tests/" in runs

    def test_g7_runs_without_a_bot_argument(self, gates):
        run = _step(gates, "G-7")["run"]
        assert "check_desk_integrity.py --repo ." in run
        assert "--bot" not in run


class TestSecurityGatesStillBlock:
    def test_no_bypass_snippets_in_any_run_block(self, security_pr):
        for block in _run_blocks(security_pr):
            for snippet in BYPASS_SNIPPETS:
                assert snippet not in block, snippet

    def test_checkouts_keep_history_for_base_ref_diffs(self, security_pr):
        for job_name in ("secrets", "semgrep", "bandit"):
            checkout = security_pr["jobs"][job_name]["steps"][0]
            assert checkout["uses"].startswith("actions/checkout")
            assert checkout["with"]["fetch-depth"] == 0, job_name

    def test_gitleaks_scans_only_pr_commits_and_fails_on_a_leak(self, security_pr):
        run = _step(security_pr, "Gitleaks — scan")["run"]
        assert "--exit-code 1" in run
        assert "origin/$BASE_REF..HEAD" in run
        assert "--config ci/security/gitleaks.toml" in run

    def test_semgrep_blocks_error_severity_against_the_baseline(self, security_pr):
        run = _step(security_pr, "Semgrep — repo rules")["run"]
        assert "--severity ERROR --error" in run
        assert '--baseline-commit "origin/$BASE_REF"' in run

    def test_bandit_blocks_high_severity_against_its_baseline(self, security_pr):
        run = _step(security_pr, "Bandit — whole repo")["run"]
        assert "-lll" in run
        assert "-b bandit-baseline.json" in run

    def test_bandit_baseline_fails_closed(self, security_pr):
        run = _step(security_pr, "Bandit baseline")["run"]
        assert "refusing to compare against an untrustworthy baseline" in run
        assert "-gt 1" in run

    def test_trivy_fails_on_high_and_critical_without_ignore_unfixed(self, security_pr):
        with_ = _step(security_pr, "Trivy filesystem scan")["with"]
        assert with_["severity"] == "HIGH,CRITICAL"
        assert with_["exit-code"] == "1"
        assert "ignore-unfixed" not in with_

    def test_pip_audit_scans_the_uv_lock_export_strictly(self, security_pr):
        run = _step(security_pr, "pip-audit")["run"]
        assert "uv export --frozen --no-dev --no-emit-project" in run
        assert "pip-audit -r req.txt --strict" in run

    def test_semgrep_and_bandit_configs_are_referenced_and_present(self, security_pr):
        runs = " ".join(_run_blocks(security_pr))
        assert "ci/security/semgrep.yml" in runs
        assert "ci/security/bandit_json_to_sarif.py" in runs
        assert (REPO_ROOT / "ci" / "security" / "semgrep.yml").is_file()
        assert (REPO_ROOT / "ci" / "security" / "bandit.ini").is_file()


class TestGitleaksConfig:
    @pytest.fixture(scope="module")
    def config(self) -> dict:
        return tomllib.loads(GITLEAKS_CONFIG.read_text())

    def test_extends_the_default_ruleset(self, config):
        assert config["extend"]["useDefault"] is True

    @pytest.mark.parametrize("rule_id", TRADING_GITLEAKS_RULES)
    def test_each_trading_family_has_a_gitleaks_rule(self, config, rule_id):
        assert rule_id in {rule["id"] for rule in config["rules"]}

    def test_every_custom_rule_has_a_regex(self, config):
        for rule in config["rules"]:
            assert rule["regex"], rule["id"]

    def test_sarif_converter_exposes_convert(self):
        spec = importlib.util.spec_from_file_location(
            "bandit_json_to_sarif", BANDIT_SARIF_CONVERTER
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert callable(module.convert)


class TestCiWorkflow:
    def test_runs_the_canonical_make_targets(self):
        runs = " ".join(_run_blocks(_load_yaml("ci.yml")))
        assert "make lint typecheck test audit" in runs

    def test_pins_uv_to_the_lockfile_version(self):
        runs = " ".join(_run_blocks(_load_yaml("ci.yml")))
        assert 'pip install "uv==0.13.4"' in runs

    def test_triggers_on_push_and_pull_request_to_main(self):
        trigger = _trigger(_load_yaml("ci.yml"))
        assert trigger["push"]["branches"] == ["main"]
        assert trigger["pull_request"]["branches"] == ["main"]

    def test_nightly_soak_schedule_requires_soak(self):
        doc = _load_yaml("ci.yml")
        trigger = _trigger(doc)
        assert any("cron" in item for item in trigger["schedule"])
        soak = doc["jobs"]["soak"]
        assert soak["runs-on"] == "ubuntu-latest"
        assert soak["if"] == "github.event_name == 'schedule'"
        step = soak["steps"][-1]
        assert str(step["env"]["PUMPGROK_REQUIRE_SOAK"]) == "1"
        assert "pytest -q -m slow tests/soak" in step["run"]


class TestSecurityPrPushTrigger:
    def test_triggers_on_pull_request_and_push_to_main(self, security_pr):
        trigger = _trigger(security_pr)
        assert trigger["pull_request"]["branches"] == ["main"]
        assert trigger["push"]["branches"] == ["main"]

    def test_pip_audit_runs_through_uv_run(self, security_pr):
        run = _step(security_pr, "pip-audit")["run"]
        assert "uv run pip-audit -r req.txt --strict" in run
        assert "uv sync --frozen" in run

    def test_scanner_installs_are_version_pinned(self, security_pr):
        runs = " ".join(_run_blocks(security_pr))
        assert 'pip install "semgrep==' in runs
        assert 'pip install "bandit==' in runs
        assert "\nrun: pip install semgrep\n" not in runs
        assert "\nrun: pip install bandit\n" not in runs


class TestSecurityExceptions:
    @pytest.fixture(scope="module")
    def gate(self):
        spec = importlib.util.spec_from_file_location("check_exceptions", EXCEPTIONS_GATE)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_exceptions_table_has_columns_and_zero_rows(self, gate):
        text = (REPO_ROOT / "SECURITY.md").read_text()
        assert "| Check | Fingerprint | Reason | Owner | Expiry (ISO) |" in text
        assert gate.check_text(text, datetime.date(2026, 10, 22)) == []

    def test_expired_expiry_is_reported(self, gate):
        text = (
            "## Exceptions\n\n"
            "| Check | Fingerprint | Reason | Owner | Expiry (ISO) |\n"
            "|---|---|---|---|---|\n"
            "| pip-audit | sha256:abc | no fix released | bot-02-risk | 2026-01-01 |\n"
        )
        errors = gate.check_text(text, datetime.date(2026, 10, 22))
        assert len(errors) == 1 and "expired" in errors[0]

    def test_malformed_row_is_reported(self, gate):
        text = (
            "## Exceptions\n\n"
            "| Check | Fingerprint | Reason | Owner | Expiry (ISO) |\n"
            "|---|---|---|---|---|\n"
            "| pip-audit | sha256:abc | no fix released | bot-02-risk | soon |\n"
        )
        errors = gate.check_text(text, datetime.date(2026, 10, 22))
        assert len(errors) == 1 and "ISO" in errors[0]


class TestPreCommitHooks:
    @pytest.fixture(scope="module")
    def hooks(self) -> dict:
        config = yaml.safe_load((REPO_ROOT / ".pre-commit-config.yaml").read_text())
        return {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}

    def test_g3_runs_on_staged_files(self, hooks):
        assert "--staged" in hooks["g3-committed-secrets"]["entry"]

    def test_g1_runs_the_manifest_self_check(self, hooks):
        assert "--validate-manifest" in hooks["g1-ownership-manifest"]["entry"]

    def test_gate_self_test_runs_the_gate_suite(self, hooks):
        assert "pytest ci/tests" in hooks["gate-self-test"]["entry"]

    def test_no_auto_formatter_hook(self, hooks):
        assert not any("ruff format" in hook["entry"] for hook in hooks.values())


class TestReceiptDirectories:
    @pytest.fixture(scope="module")
    def seats(self) -> list[str]:
        manifest = yaml.safe_load((REPO_ROOT / "ownership.yaml").read_text())
        return sorted(manifest["bots"])

    def test_there_are_ten_seats(self, seats):
        assert len(seats) == 10

    def test_every_seat_has_a_tracked_gitkeep(self, seats):
        for seat in seats:
            assert (REPO_ROOT / ".receipts" / seat / ".gitkeep").is_file(), seat

    def test_only_gitignore_allowlisted_receipt_json_is_tracked(self):
        tracked = subprocess.run(
            ["git", "ls-files", "--", ".receipts"],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        ).stdout.split()
        allowed = {
            line.removeprefix("!")
            for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.startswith("!.receipts/") and line.endswith(".json")
        }
        tracked_json = {path for path in tracked if path.endswith(".json")}
        assert tracked_json <= allowed, sorted(tracked_json - allowed)
