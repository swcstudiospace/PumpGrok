"""Gate test suite for ci/gates/ (G-1..G-7).

Each gate is exercised through the same code path CI uses: the CLI for exit codes and messages,
and the imported module for the pure functions. Every constant the pumpgrok port changed has its
own test, so a later edit that quietly widens a regex or a roster bound turns a test red.

Synthetic secret-shaped literals are built at runtime or carry the allowlist marker, so the
secrets gate (G-3) does not flag this file when it scans the PR diff.

    python3 -m pytest ci/tests/ -q
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

GATES = Path(__file__).resolve().parents[1] / "gates"
REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "ownership.yaml"

ALL_GATE_SCRIPTS = [
    "check_ownership.py",
    "check_receipt.py",
    "check_secrets.py",
    "check_contracts.py",
    "check_rollback.py",
    "check_desk_integrity.py",
    "run_all.py",
]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, GATES / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_gate(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATES / script), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


@pytest.fixture(scope="module")
def manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text())


@pytest.fixture(scope="module")
def ownership():
    return _load("check_ownership")


@pytest.fixture(scope="module")
def receipt_gate():
    return _load("check_receipt")


@pytest.fixture(scope="module")
def secrets_gate():
    return _load("check_secrets")


@pytest.fixture(scope="module")
def contracts_gate():
    return _load("check_contracts")


@pytest.fixture(scope="module")
def rollback_gate():
    return _load("check_rollback")


@pytest.fixture(scope="module")
def integrity_gate():
    return _load("check_desk_integrity")


# ---------------------------------------------------------------------------
# G-1 ownership
# ---------------------------------------------------------------------------


class TestG1Ownership:
    def test_manifest_self_check_passes_on_the_tree(self):
        r = run_gate("check_ownership.py", "--validate-manifest")
        assert r.returncode == 0, r.stderr
        assert "each with one declared owner" in r.stdout

    @pytest.mark.parametrize(
        "path,bot",
        [
            ("src/pumpgrok/execution/paper.py", "bot-04-sniper"),
            ("src/pumpgrok/execution/live/live_gate.py", "bot-02-risk"),
            ("src/pumpgrok/core/ids.py", "bot-02-risk"),
            ("src/pumpgrok/engine/exits.py", "bot-06-exit"),
            ("src/pumpgrok/tools/safety/score.py", "bot-05-rug"),
            ("vendor/grokbot-pumpfun/src/models.py", "bot-02-risk"),
            ("vendor/grokbot-pumpfun/README.md", "bot-02-risk"),
            ("tools/notes/SETUP.md", "bot-02-risk"),
            ("banner.jpg", "bot-00-chief"),
            ("agents/chief.md", "bot-00-chief"),
            ("ci/gates/check_receipt.py", "bot-02-risk"),
        ],
    )
    def test_each_path_routes_to_its_owner(self, path, bot):
        r = run_gate("check_ownership.py", "--bot", bot, "--files", path)
        assert r.returncode == 0, f"{path} should belong to {bot}\n{r.stderr}"

    def test_foreign_path_is_blocked(self):
        r = run_gate(
            "check_ownership.py",
            "--bot",
            "bot-01-scout",
            "--files",
            "src/pumpgrok/execution/paper.py",
        )
        assert r.returncode == 1
        assert "FOREIGN" in r.stderr
        assert "bot-04-sniper" in r.stderr

    def test_foreign_contract_surface_is_blocked(self):
        # A contract_surface flag must not exempt a path from ownership: a non-owner editing a
        # shared contract is FOREIGN, not a G-4 NOTE.
        r = run_gate(
            "check_ownership.py",
            "--bot",
            "bot-04-sniper",
            "--files",
            "contracts/tool-rosters/bot-03-whale.yaml",
        )
        assert r.returncode == 1
        assert "FOREIGN" in r.stderr
        assert "bot-02-risk" in r.stderr

    def test_unowned_path_is_blocked(self):
        r = run_gate(
            "check_ownership.py", "--bot", "bot-02-risk", "--files", "some/unclaimed/file.xyz"
        )
        assert r.returncode == 1
        assert "UNOWNED" in r.stderr

    def test_unknown_bot_is_rejected(self):
        r = run_gate(
            "check_ownership.py",
            "--bot",
            "bot-10-nonexistent",
            "--files",
            "ci/gates/check_receipt.py",
        )
        assert r.returncode != 0

    def test_live_rule_placed_after_execution_rule_wins(self, ownership, manifest):
        owner, _ = ownership.resolve_owner("src/pumpgrok/execution/live/live_adapter.py", manifest)
        assert owner == "bot-02-risk"

    def test_self_test_reports_unowned_tracked_path(self, ownership, manifest):
        problems = ownership.self_test(manifest, ["README.md", "some/unclaimed/file.xyz"])
        assert problems == ["UNOWNED  some/unclaimed/file.xyz"]

    def test_self_test_reports_undeclared_owner(self, ownership):
        manifest = {
            "bots": {"bot-00-chief": {}},
            "ownership": [{"pattern": "**/*.py", "owner": "bot-99-ghost"}],
        }
        assert ownership.self_test(manifest, ["a.py"]) == ["UNDECLARED OWNER 'bot-99-ghost'  a.py"]

    def test_every_tracked_path_has_one_declared_owner(self, ownership, manifest):
        assert ownership.self_test(manifest, ownership.tracked_paths()) == []


# ---------------------------------------------------------------------------
# G-2 verification receipts
# ---------------------------------------------------------------------------


def _receipt(**overrides) -> dict:
    receipt = {
        "task_id": "PG-1",
        "bot": "bot-04-sniper",
        "approved_by": "bot-02-risk",
        "commands": [{"cmd": "uv run pytest -q", "exit_code": 0, "output_tail": "3 passed"}],
        "claims": [{"claim": "Tests pass", "evidence_command_index": 0}],
        "unverified": ["live RPC behaviour"],
    }
    receipt.update(overrides)
    return receipt


class TestG2Receipts:
    def test_clean_receipt_passes(self, receipt_gate):
        assert receipt_gate.check(_receipt(), "bot-04-sniper") == []

    @pytest.mark.parametrize("field", ["task_id", "bot", "commands", "claims", "unverified"])
    def test_required_fields_are_enforced(self, receipt_gate, field):
        receipt = _receipt()
        del receipt[field]
        assert f"missing required field '{field}'" in receipt_gate.check(receipt, None)

    def test_self_approval_is_refused(self, receipt_gate):
        problems = receipt_gate.check(_receipt(approved_by="bot-04-sniper"), "bot-04-sniper")
        assert any("self-approval" in p for p in problems)

    def test_receipt_bot_must_match_expected_bot(self, receipt_gate):
        problems = receipt_gate.check(_receipt(), "bot-03-whale")
        assert any("does not match --bot" in p for p in problems)

    def test_claim_citing_failing_command_is_refused(self, receipt_gate):
        receipt = _receipt(commands=[{"cmd": "uv run pytest -q", "exit_code": 1}])
        problems = receipt_gate.check(receipt, "bot-04-sniper")
        assert any("which exited 1" in p for p in problems)

    @pytest.mark.parametrize(
        "cmd",
        [
            "PUMPGROK_LIVE_ENABLE=1 uv run pumpgrok run --mode paper",
            "PUMPGROK_LIVE_ENABLE=true uv run pumpgrok run --mode paper",
            "uv run pumpgrok run --mode live --i-understand-the-risk",
            "uv run pytest -q || true",
            "uv run pytest -q --no-verify",
        ],
    )
    def test_bypass_commands_are_refused(self, receipt_gate, cmd):
        problems = receipt_gate.check(
            _receipt(
                commands=[{"cmd": cmd, "exit_code": 0}],
                claims=[{"claim": "ran", "evidence_command_index": 0}],
            ),
            "bot-04-sniper",
        )
        assert any("contains a bypass" in p for p in problems), problems

    def test_live_flag_and_risk_flag_are_in_the_bypass_list(self, receipt_gate):
        patterns = [p for p, _ in receipt_gate.BYPASS_PATTERNS]
        assert r"PUMPGROK_LIVE_ENABLE=(?:1|true)" in patterns
        assert r"--i-understand-the-risk" in patterns

    @pytest.mark.parametrize(
        "seat",
        [
            "bot-00-chief",
            "bot-05-rug",
            "bot-09-journal",
            "the desk",
            "desk-ops",
        ],
    )
    def test_seat_regex_accepts_pumpgrok_seats(self, receipt_gate, seat):
        assert receipt_gate.SEAT_ID_RE.match(seat)

    @pytest.mark.parametrize("token", ["bot-10-extra", "bot-0", "SNIPER", "LEAD"])
    def test_seat_regex_rejects_non_seats(self, receipt_gate, token):
        assert not receipt_gate.SEAT_ID_RE.match(token)

    def test_loop_ack_granted_by_a_seat_is_refused(self, receipt_gate):
        ack = {
            "condition": "brief_degraded",
            "operation": "work ticket",
            "ack_id": "a1",
            "human_granted_by": "bot-09-journal",
            "at": "2026-10-21T00:00:00Z",
            "scope": "task PG-1",
        }
        problems = receipt_gate.check(_receipt(loop_acks=[ack]), "bot-04-sniper")
        assert any("is a seat, not a human" in p for p in problems)


# ---------------------------------------------------------------------------
# G-3 committed secrets
# ---------------------------------------------------------------------------


def _rules(secrets_gate, line: str) -> set[str]:
    return {f["rule"] for f in secrets_gate.scan_line("fixture.py", 1, line)}


class TestG3Secrets:
    def test_env_example_passes_on_placeholders_only(self, secrets_gate):
        assert secrets_gate.scan_file(REPO_ROOT / ".env.example", ".env.example") == []

    def test_gate_cli_passes_on_env_example(self):
        r = run_gate("check_secrets.py", "--files", ".env.example")
        assert r.returncode == 0, r.stderr

    def test_solana_base58_secret_key_shape_is_flagged(self, secrets_gate):
        line = "SOLANA_KEY = " + "5" + "A" * 87
        assert "solana_base58_key" in _rules(secrets_gate, line)

    def test_solana_json_keypair_byte_array_is_flagged(self, secrets_gate):
        line = "[" + ", ".join(str(i % 256) for i in range(64)) + "]"
        assert "solana_json_keypair" in _rules(secrets_gate, line)

    def test_helius_keyed_rpc_url_is_flagged(self, secrets_gate):
        key = "A1b2C3d4E5f6G7h8I9j0K"
        line = "rpc = 'https://mainnet.helius-rpc.com/?" + "api-" + "key=" + key + "'"
        assert "helius_url_key" in _rules(secrets_gate, line)

    def test_quicknode_keyed_endpoint_is_flagged(self, secrets_gate):
        line = "url = 'https://x-y.solana-mainnet.quiknode.pro/" + "Q" * 24 + "'"
        assert "quicknode_url" in _rules(secrets_gate, line)

    def test_telegram_bot_token_shape_is_flagged(self, secrets_gate):
        line = "TELEGRAM_ID = " + "123456789" + ":" + "A" * 35
        assert "telegram_bot_token" in _rules(secrets_gate, line)

    def test_xai_key_shape_is_flagged(self, secrets_gate):
        line = 'XAI = "xai-' + "k" * 32 + '"'
        assert "xai_key" in _rules(secrets_gate, line)

    def test_original_precedent_families_are_kept(self, secrets_gate):
        line = "KEY = " + "AKIA" + "A" * 16
        assert "aws_access_key" in _rules(secrets_gate, line)

    @pytest.mark.parametrize("name", ["keypair", "mnemonic", "seed_phrase", "wallet_secret"])
    def test_secret_name_regex_covers_trading_names(self, secrets_gate, name):
        line = f'{name} = "Zq8Lr2Tv9Wm4Xk7Nb1Hc6Yd3Pe5Fg0Js"'
        assert "high_entropy" in _rules(secrets_gate, line)

    @pytest.mark.parametrize("name", ["id.json", "keypair.json", "wallet.json"])
    def test_wallet_file_names_are_always_flagged(self, secrets_gate, name):
        findings = secrets_gate.scan_file(Path(name), name)
        assert [f["rule"] for f in findings] == ["forbidden_file"]

    def test_pragma_allowlist_marker_suppresses_a_line(self, secrets_gate):
        line = 'API_KEY = "Zq8Lr2Tv9Wm4Xk7Nb1Hc6Yd3Pe5Fg0Js"  # pragma: allowlist secret'
        assert secrets_gate.scan_line("fixture.py", 1, line) == []

    def test_placeholder_values_are_not_high_entropy_findings(self, secrets_gate):
        assert secrets_gate.is_placeholder("your_api_key_here")
        assert secrets_gate.is_placeholder("changeme")


# ---------------------------------------------------------------------------
# G-4 contract-first changes
# ---------------------------------------------------------------------------


def _change_doc(manifest: dict, **overrides) -> dict:
    doc = {
        "change_id": "C-1",
        "proposed_by": "bot-04-sniper",
        "surface": "contracts/events/order_placed.schema.json",
        "breaking": False,
        "version": "1.2.0",
        "summary": "add an optional field",
        "semantic_changes": [],
        "acknowledgements": [{"bot": bot, "ack": True} for bot in manifest["bots"]],
    }
    doc.update(overrides)
    return doc


class TestG4Contracts:
    def test_event_schemas_have_all_ten_seats_as_consumers(self, contracts_gate, manifest):
        consumers = contracts_gate.required_consumers(
            "contracts/events/order_placed.schema.json", manifest
        )
        assert set(consumers) == set(manifest["bots"])

    def test_tool_rosters_have_all_ten_seats_as_consumers(self, contracts_gate, manifest):
        consumers = contracts_gate.required_consumers(
            "contracts/tool-rosters/bot-04-sniper.yaml", manifest
        )
        assert set(consumers) == set(manifest["bots"])

    def test_non_breaking_change_with_acks_passes(self, contracts_gate, manifest):
        doc = _change_doc(manifest)
        touched = ["contracts/events/order_placed.schema.json"]
        assert contracts_gate.check_change_doc(doc, manifest, touched=touched) == []

    def test_breaking_change_needs_every_consumer_ack(self, contracts_gate, manifest):
        acks = [{"bot": b, "ack": True} for b in manifest["bots"] if b != "bot-09-journal"]
        doc = _change_doc(
            manifest,
            breaking=True,
            version="2.0.0",
            migration_note="rename x",
            previous_version="1.2.0",
            acknowledgements=acks,
        )
        problems = contracts_gate.check_change_doc(doc, manifest)
        assert any("no acknowledgement from 'bot-09-journal'" in p for p in problems)

    def test_breaking_change_needs_a_major_bump(self, contracts_gate, manifest):
        doc = _change_doc(
            manifest,
            breaking=True,
            version="1.3.0",
            migration_note="rename x",
            previous_version="1.2.0",
        )
        problems = contracts_gate.check_change_doc(doc, manifest)
        assert any("major version did not increase" in p for p in problems)

    def test_breaking_change_needs_a_migration_note(self, contracts_gate, manifest):
        doc = _change_doc(manifest, breaking=True, version="2.0.0", previous_version="1.2.0")
        problems = contracts_gate.check_change_doc(doc, manifest)
        assert any("no 'migration_note'" in p for p in problems)

    def test_semantic_changes_declaration_is_required(self, contracts_gate, manifest):
        doc = _change_doc(manifest)
        del doc["semantic_changes"]
        problems = contracts_gate.check_change_doc(doc, manifest)
        assert any("missing 'semantic_changes'" in p for p in problems)

    def test_touched_surface_missing_from_document_is_refused(self, contracts_gate, manifest):
        doc = _change_doc(manifest)
        touched = ["contracts/events/fill_recorded.schema.json"]
        problems = contracts_gate.check_change_doc(doc, manifest, touched=touched)
        assert any("does not cover every contract surface" in p for p in problems)


# ---------------------------------------------------------------------------
# G-5 rollback plans and G-6 destructive operations
# ---------------------------------------------------------------------------

GOOD_PLAN = (
    "Run `pumpgrok killswitch set --reason rollback` to halt; recovery within seconds; "
    "ledger data is append-only so no data is lost."
)


def _approval(blast_radius: str = "max_notional_sol=0.2") -> dict:
    return {
        "operation": "killswitch clear",
        "approved_by": "human:operator",
        "at": "2026-10-21T00:00:00Z",
        "blast_radius": blast_radius,
    }


def _run_rollback(rollback_gate, tmp_path: Path, receipt: dict) -> subprocess.CompletedProcess:
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    return subprocess.run(
        [sys.executable, str(GATES / "check_rollback.py"), "--receipt", str(path)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


class TestG5G6RollbackAndDestructive:
    def test_live_run_is_a_deployment_and_paper_run_is_not(self, rollback_gate):
        live = rollback_gate.find_matches(
            [{"cmd": "uv run pumpgrok run --mode live --once"}], rollback_gate.DEPLOY_PATTERNS
        )
        paper = rollback_gate.find_matches(
            [{"cmd": "uv run pumpgrok run --mode paper --once"}], rollback_gate.DEPLOY_PATTERNS
        )
        assert len(live) == 1
        assert paper == []

    def test_precedent_infrastructure_patterns_are_dropped(self, rollback_gate):
        hits = rollback_gate.find_matches(
            [{"cmd": "terraform destroy -auto-approve"}, {"cmd": "kubectl delete pod x"}],
            rollback_gate.DESTRUCTIVE_PATTERNS,
        )
        assert hits == []

    @pytest.mark.parametrize(
        "cmd,category",
        [
            ("uv run pumpgrok state halt --clear --by human:op --reason ok", "trade"),
            ("uv run pumpgrok killswitch clear --by human:op --reason ok", "trade"),
            ("uv run pumpgrok risk raise-limit max_notional_sol=1", "trade"),
            ("rm -f var/KILLSWITCH", "trade"),
            ("sqlite3 var/ledger.sqlite 'select 1'", "ledger"),
            ("DELETE FROM events WHERE seq = 1", "ledger"),
        ],
    )
    def test_trade_and_ledger_verbs_are_destructive(self, rollback_gate, cmd, category):
        hits = rollback_gate.find_matches([{"cmd": cmd}], rollback_gate.DESTRUCTIVE_PATTERNS)
        assert hits and hits[0][2] == category

    def test_halt_without_clear_is_not_destructive(self, rollback_gate):
        hits = rollback_gate.find_matches(
            [{"cmd": "uv run pumpgrok state halt --reason drawdown"}],
            rollback_gate.DESTRUCTIVE_PATTERNS,
        )
        assert hits == []

    def test_blast_radius_must_name_a_notional(self, rollback_gate):
        assert rollback_gate.TRADE_BLAST_RADIUS_RE.match("max_notional_sol=0.25")
        assert not rollback_gate.TRADE_BLAST_RADIUS_RE.match("unbounded")
        assert not rollback_gate.TRADE_BLAST_RADIUS_RE.match("max_notional_sol=abc")

    def test_trade_operation_with_unbounded_approval_fails(self, rollback_gate, tmp_path):
        receipt = {
            "commands": [
                {
                    "cmd": "uv run pumpgrok killswitch clear --by human:op --reason ok",
                    "exit_code": 0,
                }
            ],
            "approvals": [_approval("unbounded")],
        }
        r = _run_rollback(rollback_gate, tmp_path, receipt)
        assert r.returncode == 1
        assert "max_notional_sol=<float>" in r.stderr

    def test_trade_operation_with_notional_approval_passes(self, rollback_gate, tmp_path):
        receipt = {
            "commands": [
                {
                    "cmd": "uv run pumpgrok killswitch clear --by human:op --reason ok",
                    "exit_code": 0,
                }
            ],
            "approvals": [_approval("max_notional_sol=0.2")],
        }
        r = _run_rollback(rollback_gate, tmp_path, receipt)
        assert r.returncode == 0, r.stderr

    def test_destructive_operation_without_approval_fails(self, rollback_gate, tmp_path):
        receipt = {"commands": [{"cmd": "rm -rf var/replay", "exit_code": 0}]}
        r = _run_rollback(rollback_gate, tmp_path, receipt)
        assert r.returncode == 1
        assert "NO approvals" in r.stderr

    def test_live_deployment_needs_a_rollback_plan(self, rollback_gate, tmp_path):
        receipt = {
            "commands": [{"cmd": "uv run pumpgrok run --mode live --once", "exit_code": 0}],
            "rollback_plan": "roll back",
        }
        r = _run_rollback(rollback_gate, tmp_path, receipt)
        assert r.returncode == 1
        assert "G-5" in r.stderr

    def test_rollback_plan_naming_pumpgrok_command_passes(self, rollback_gate, tmp_path):
        receipt = {
            "commands": [{"cmd": "uv run pumpgrok run --mode live --once", "exit_code": 0}],
            "rollback_plan": GOOD_PLAN,
        }
        assert rollback_gate.check_plan(GOOD_PLAN) == []
        r = _run_rollback(rollback_gate, tmp_path, receipt)
        assert r.returncode == 0, r.stderr

    def test_approval_missing_fields_is_refused(self, rollback_gate, tmp_path):
        approval = _approval()
        del approval["blast_radius"]
        receipt = {
            "commands": [{"cmd": "rm -rf var/replay", "exit_code": 0}],
            "approvals": [approval],
        }
        r = _run_rollback(rollback_gate, tmp_path, receipt)
        assert r.returncode == 1
        assert "missing ['blast_radius']" in r.stderr


# ---------------------------------------------------------------------------
# G-7 desk integrity
# ---------------------------------------------------------------------------


def _tool(name: str = "desk.state_status", kind: str = "read", gates=None, required=None) -> dict:
    return {
        "name": name,
        "kind": kind,
        "gates": list(gates or []),
        "description": "fixture tool",
        "input": {
            "type": "object",
            "additionalProperties": False,
            "properties": {},
            "required": list(required or []),
        },
    }


def _write_roster(directory: Path, name: str, doc: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(yaml.safe_dump(doc, sort_keys=False))


class TestG7DeskIntegrity:
    def test_roster_bounds_are_the_retargeted_values(self, integrity_gate):
        assert integrity_gate.ROSTER_MIN_TOOLS == 8
        assert integrity_gate.ROSTER_MAX_TOOLS == 15

    @pytest.mark.parametrize("name", ["exec.place", "desk.state_status", "journal.note_write"])
    def test_tool_name_accepts_dotted_names(self, integrity_gate, name):
        assert integrity_gate.TOOL_NAME_RE.match(name)

    @pytest.mark.parametrize("name", ["place", "exec_place", "Exec.place", "exec..place", "a."])
    def test_tool_name_rejects_flat_or_malformed_names(self, integrity_gate, name):
        assert not integrity_gate.TOOL_NAME_RE.match(name)

    def test_seat_regex_covers_all_ten_seats(self, integrity_gate, manifest):
        for seat in manifest["bots"]:
            assert integrity_gate.SEAT_RE.match(seat), seat
        assert not integrity_gate.SEAT_RE.match("bot-10-extra")

    def test_assembled_aliases_are_the_pumpgrok_seats(self, integrity_gate):
        assert integrity_gate.ASSEMBLED_ALIASES == [
            "CHIEF",
            "SCOUT",
            "RISK",
            "WHALE",
            "SNIPER",
            "RUG",
            "EXIT",
            "SHILL",
            "SIGNAL",
            "JOURNAL",
        ]

    def test_write_tool_must_be_tagged_g6(self, integrity_gate):
        tool = _tool(
            "exec.place", kind="write", gates=[], required=["approval_id", "rollback_plan"]
        )
        problems = integrity_gate.check_tool(tool, 0)
        assert any("not tagged g6" in p for p in problems)

    def test_write_tool_must_require_rollback_plan(self, integrity_gate):
        tool = _tool("exec.place", kind="write", gates=["g6"], required=["approval_id"])
        problems = integrity_gate.check_tool(tool, 0)
        assert any("lacks 'rollback_plan'" in p for p in problems)

    def test_fully_gated_write_tool_passes(self, integrity_gate):
        tool = _tool(
            "exec.place", kind="write", gates=["g6"], required=["approval_id", "rollback_plan"]
        )
        assert integrity_gate.check_tool(tool, 0) == []

    def test_read_tool_needs_no_gate(self, integrity_gate):
        assert integrity_gate.check_tool(_tool("desk.state_status"), 0) == []

    def test_roster_that_names_a_live_write_tool_is_refused(self, integrity_gate, tmp_path):
        core = [_tool(f"desk.core_{i}") for i in range(8)]
        seat = {
            "seat": "bot-04-sniper",
            "short": "sniper",
            "endpoint": "/mcp/sniper",
            "core": True,
            "tools": [
                _tool(
                    "exec.live_place",
                    kind="write",
                    gates=["g6"],
                    required=["approval_id", "rollback_plan"],
                )
            ],
        }
        problems = integrity_gate.check_roster(_fixture_path(tmp_path, seat), core)
        assert any("live-write tool" in p for p in problems)

    def test_roster_size_bounds_are_inclusive(self, integrity_gate, tmp_path):
        core = [_tool(f"desk.core_{i}") for i in range(8)]
        ok = {
            "seat": "bot-03-whale",
            "short": "whale",
            "endpoint": "/mcp/whale",
            "core": True,
            "tools": [],
        }
        assert integrity_gate.check_roster(_fixture_path(tmp_path, ok), core) == []

        too_many = dict(ok, tools=[_tool(f"whale.tool_{i}") for i in range(8)])
        problems = integrity_gate.check_roster(_fixture_path(tmp_path, too_many), core)
        assert any("must be within [8, 15]" in p for p in problems)

    def test_missing_roster_directory_fails_the_run(self, integrity_gate, tmp_path):
        problems, _ = integrity_gate.run(
            tmp_path,
            tmp_path / "contracts/tool-rosters",
            tmp_path / "contracts/tool-packs",
            tmp_path / "prompts",
            tmp_path / "prompts-assembled",
            tmp_path / "grokbot/templates",
        )
        assert any("roster directory not found" in p for p in problems)

    def test_valid_roster_directory_passes_the_run(self, integrity_gate, tmp_path):
        rosters = tmp_path / "contracts" / "tool-rosters"
        core = {"tools": [_tool(f"desk.core_{i}") for i in range(8)]}
        _write_roster(rosters, "_core.yaml", core)
        _write_roster(
            rosters,
            "bot-04-sniper.yaml",
            {
                "seat": "bot-04-sniper",
                "short": "sniper",
                "endpoint": "/mcp/sniper",
                "core": True,
                "tools": [
                    _tool(
                        "sniper.paper_buy",
                        kind="write",
                        gates=["g6"],
                        required=["approval_id", "rollback_plan"],
                    )
                ],
            },
        )
        problems, counts = integrity_gate.run(
            tmp_path,
            rosters,
            tmp_path / "contracts/tool-packs",
            tmp_path / "prompts",
            tmp_path / "prompts-assembled",
            tmp_path / "grokbot/templates",
        )
        assert problems == []
        assert counts["rosters"] == 1

    def test_trading_secret_shapes_are_forbidden_in_templates(self, integrity_gate, tmp_path):
        template = tmp_path / "grok.md"
        key = "A1b2C3d4E5f6G7h8I9j0K"
        address = "5" + "A" * 40
        template.write_text(
            "\n".join(
                [
                    "rpc: https://mainnet.helius-rpc.com/?" + "api-" + "key=" + key,
                    f"{address} is the mint",
                    "plain guidance with no secret shapes",
                ]
            )
            + "\n"
        )
        problems = integrity_gate.check_template(template)
        assert any("Helius keyed RPC URL" in p for p in problems)
        assert any("literal Solana address beside mint or wallet" in p for p in problems)
        assert not any("plain" in p for p in problems)

    def test_solana_address_without_mint_or_wallet_is_allowed(self, integrity_gate, tmp_path):
        template = tmp_path / "note.md"
        template.write_text("5" + "A" * 40 + " is an example of a shape\n")
        assert integrity_gate.check_template(template) == []


def _fixture_path(tmp_path: Path, doc: dict) -> Path:
    path = tmp_path / f"{doc['seat']}.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    return path


# ---------------------------------------------------------------------------
# Wiring and the stdlib-plus-pyyaml rule
# ---------------------------------------------------------------------------


class TestEveryGateIsWired:
    def test_run_all_runs_g1_to_g7_in_order(self, monkeypatch):
        run_all = _load("run_all")
        calls: list[tuple[str, list[str]]] = []

        def fake_run(name: str, argv: list[str]) -> tuple[str, int]:
            calls.append((name, argv))
            return name, 0

        monkeypatch.setattr(run_all, "run", fake_run)
        monkeypatch.setattr(
            sys, "argv", ["run_all.py", "--bot", "bot-04-sniper", "--receipt", "r.json"]
        )
        assert run_all.main() == 0
        assert [name.split()[0] for name, _ in calls] == [
            "G-1",
            "G-2",
            "G-3",
            "G-4",
            "G-5/G-6",
            "G-7",
        ]

    def test_g7_takes_no_bot_argument(self, monkeypatch):
        run_all = _load("run_all")
        calls: list[tuple[str, list[str]]] = []
        monkeypatch.setattr(
            run_all, "run", lambda name, argv: (calls.append((name, argv)), (name, 0))[1]
        )
        monkeypatch.setattr(
            sys, "argv", ["run_all.py", "--bot", "bot-04-sniper", "--receipt", "r.json"]
        )
        run_all.main()
        g7_argv = calls[-1][1]
        assert "--bot" not in g7_argv
        assert "--repo" in g7_argv

    @pytest.mark.parametrize("script", ALL_GATE_SCRIPTS)
    def test_gate_imports_stay_in_stdlib_and_pyyaml(self, script):
        tree = ast.parse((GATES / script).read_text())
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
        allowed = set(sys.stdlib_module_names) | {"yaml"}
        assert modules <= allowed, sorted(modules - allowed)
