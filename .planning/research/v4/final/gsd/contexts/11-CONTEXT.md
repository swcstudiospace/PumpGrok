# Phase 11 CONTEXT: Engineering foundation and quality

Milestone v4, Phase 11. Goal per ROADMAP: the quality scaffolding every later phase leans on exists before any feature lands. The soak test is out of the default path; coverage and a complexity ratchet are measured; the six hotspots (paper_adapter sell, batch and confirm; RiskEngine._evaluate; cli/backtest; config/settings.py; supervisor/seat_task.py) are split behind characterization tests with every replay hash unchanged; property tests, a mutation smoke target, an SBOM step and compose hardening exist; every PR-number waiver is gone; every seat can track its receipt without touching a foreign path; the two hash pins (smoke-10m and the trading smoke) are in tests; the v4 roadmap and requirements are installed.

Depends on: nothing inside v4. Branches start from main after the owner-approved merge of draft PRs 17 to 20 (order 18, 19, 20, 17); tag that commit `v4-base`. Plan 11-01 carries three preflight commands (equity.py exists, `def is_writer` exists, `verify_stored_content` exists) that FAIL until those PRs are merged; that is the point, because Phases 16 to 18 rely on the symbols. At HEAD 641927c only a private `_is_writer` exists (ledger/active_set.py:51).

## Locked decisions (NON-NEGOTIABLE)

- D-01: Money is integer base units (lamports); Decimal only for ratios; no float money. Reason: ledger replay hashes must be byte-stable.
- D-02: Time only through the injected Clock, ids only from core/ids.py or derived sha256 identities; no datetime.now, time.time or asyncio.sleep in new code (tests/safety/test_no_direct_time.py).
- D-03: Live stays refused (exit 3); nothing here adds a signer, key, send path or enabling overlay.
- D-04: Hashes are identity only. No hash, digest or random value may act as a score, metric or verdict (the Phase 8 failure); a pin test compares to a recorded value.
- D-05: Style: mypy --strict on src/pumpgrok, ruff, no dead code, no swallowed errors, no TODO or placeholder text, ASCII-only new docs.
- D-06: PRC-RECEIPTS replaces per-file .gitignore receipt lines by ONE glob, `!.receipts/bot-0*/v4-p*.json`; the tracked-receipt test accepts only literal allowlist lines. Reason: otherwise every non-risk PR edits the risk-owned .gitignore (the cause of the G-1 failures on PRs 17 to 20).
- D-07: PRC-WAIVER deletes every PR-number waiver from .github/workflows/gates.yml; ci/tests/test_no_pr_waivers.py pins the waiver set to the empty tuple. Plan 18-07 later raises it to exactly one entry and plan 19-04 returns it to empty.
- D-08: Two pins land before any engine unit. smoke-10m (tests/replay/test_replay_hash_pin.py) and the trading `smoke` hash plus full row dump (tests/replay/test_trading_smoke_pin.py with pins/trading_smoke.json and trading_smoke_rows.json). Reason: smoke-10m has no admitted trade, so it proves almost nothing about risk, adapter or exit edits (N6 section 3 item 1).
- D-09: The trading pin test runs the replay through the library entry used by `pumpgrok verify` under monkeypatch.chdir(tmp_path), so a persisted var/ledger.sqlite (operator_active_set) cannot move the hash. `python -m tests.replay.pin_support --regen` prints a pin, never writes it; a re-pin is a deliberate edit plus a CHANGELOG before and after pair.
- D-10: Characterize before split: each hotspot is pinned by a test passing on the old AND the split code; rows, risk_json (19 STEP_IDS) and every hash stay byte-identical.
- D-11: After 11-04 a new settings section is one module under config/sections plus one import and one field line in settings.py; Q13c pins each PRE-v4 section by its own digest, so later units never edit it.
- D-12: Acceptance never uses collect-only or `--co` (G-2 bypass family). The fast split is proven by tests/quality/test_fast_split.py plus `make -n test | grep -q 'not slow'` and `make -n test-soak | grep -q 'm slow'`; addopts gains `-m 'not slow'`.
- D-13: Q01 alone adds dev dependencies (uv.lock regenerated once). lint, typecheck and audit become path-conditional via $(wildcard services/*/src): no-ops now, covering services/desk-signer once it lands.
- D-14: The complexity ratchet baseline only shrinks; every v4 package is outside it from its first commit.
- D-15: Pulled forward: B01 pump event decoder (rug, plan 11-07) and B02 read-only probe script scripts/probe_pump_accounts.py (chief, plan 11-09). The probe never writes VERIFIED; it records decoded_pending_review.

## Grey-area defaults

- G-01: Coverage floor = measured baseline minus one point, only moves up; set through Makefile --cov-fail-under so pyproject.toml is touched once. Reason: avoids a second pyproject edit and a flaky floor.
- G-02: Mutation smoke targets risk/limits.py, risk/sizing.py, execution/curve_math.py, execution/fees.py; opt-in, outside `make check`.
- G-03: The quality PR (PR-06, plan 11-05 included) merges last in the phase; Phase 12 develops on a draft stacked on it (depth 2) because Q13s lives there.

## Phase boundary

In scope: .gitignore, gates.yml, ci tests, Makefile, pyproject, workflows, compose hardening; characterization tests; the six splits; plain-swallow narrowing (doctor.py, core/manifests.py, authorities.py, holders.py, jupiter.py); pump_events.py decoder; probe script; .planning adoption. Out of scope: feature code, event bus, settings fields, live code, amendment text, running the probe on mainnet (OD-04, human).

## Canonical references

- src/pumpgrok/risk/engine/{core,steps,constants}.py, execution/paper_adapter/, cli/backtest.py, config/settings.py, supervisor/seat_task.py.
- ci/gates/{check_ownership,check_receipt,run_all}.py, ownership.yaml, .github/workflows/{gates,ci,security-pr}.yml, Makefile, pyproject.toml, tests/replay/, tests/fixtures/replay/{smoke,smoke-10m,soak-3d}, .planning/{ROADMAP,REQUIREMENTS,PROJECT,STATE}.md.
- research/N6-critique.md sections 3 and 4, research/changes-applied.md sections R and C, research/pr-plan.md sections 2, 3, 8.

## Existing code insights (verified at HEAD 641927c)

- Sizes: config/settings.py 651 lines, seat_task.py 608, cli/backtest.py 650, risk/engine/steps.py 417.
- Hotspots: paper_adapter _append_order_batch 141 lines CC 25, _await_confirmation 132 lines, _place_sell 179 lines CC 22; RiskEngine._evaluate CC 29; six plain-swallow excepts.
- `verify` reads operator_active_set from the cwd ledger (cli/verbs_state.py:59), so receipts run in a fresh worktree.

## Specifics

- Pin dump columns: seq, ts, type, source, idempotency_key, payload digest (JSON, tests/fixtures/replay/pins/trading_smoke_rows.json); trading_smoke.json asserts fixture == "smoke", len(events_hash) == 64, seq > 1.
- Makefile targets introduced: test (fast), test-soak (-m slow), test-all, cov, mutation-smoke; cov writes coverage.xml.
- Commits inside 11-01 stay separate: PRC-RECEIPTS, PRC-WAIVER, Q05, TSMOKE. The sniper, rug, scout and chief splits are their own PRs (PR-02 to PR-05); 11-05 (ratchet-down) depends on all of them.
- Narrowed excepts raise typed error tuples; tests/quality/test_no_plain_swallow.py rejects new ones; the rug test is named test_onchain_errors.py because test_holders* belong to whale.

## Deferred ideas

Raising the coverage floor beyond baseline; mutation in CI; ratcheting untouched legacy files.

## Ownership, receipt and hash rules (every plan of this phase)

- Branch `bot-0N-seat/v4-pPHASE-slug`, one PR per (phase, seat) (PR table below). Receipt `.receipts/bot-0N-seat/v4-pPHASE-slug.json` (task_id = slug, branch = the branch), tracked through the glob `!.receipts/bot-0*/v4-p*.json` from plan 11-01; no other seat edits .gitignore.
- `approved_by` is NEVER self-written and a seat never approves its own work. An agent reviewer (chief for risk-authored work, risk for other seats) reads the diff; human-gated receipts are committed WITHOUT approved_by and the owner adds `human:SomeRandmGuyy` in a batch at the ship checkpoint (after phases 12, 14, 17, 19).
- Seat purity: every path resolves to the plan seat via `resolve_owner(path, load_manifest(DEFAULT_MANIFEST))`; tests/** is risk except tests/desk/** (chief) and tests/engine/** (signal); execution/** sniper; cli/** risk; supervisor/** chief. A foreign-test failure gets a one-file companion plan by the owning seat, merged first.
- Replay hashes: smoke-10m `events.hash` is `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` (seq=2 events=41, verdict and rollover rows only). Trading `smoke` (5 events, seq 11) gave `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54` at HEAD 641927c; plan 11-01 pins it at v4-base; it moves only in plan 15-01. Run receipts in a fresh worktree without var/ledger.sqlite.
- Live stays refused: `uv run pumpgrok run --mode live --once; test $? -eq 3`; nothing arms it.
- Acceptance lines are real commands; exit 0 means success. The G-2 bypass family (collect-only, `--co`, `|| true`, stderr to /dev/null, `--force`, `--dry-run`, inline PUMPGROK_LIVE_ENABLE) never appears; `! cmd -rs | grep -q SKIPPED` proves no skips. Plans touching src also run make lint and make typecheck.


## Plans (11 planned; research/plans.json is the source)

Pull requests in merge order (numbers from research/pr-plan.md):

| PR | Branch | Plans | Approver | Checkpoint |
|----|--------|-------|----------|------------|
| PR-01 | `bot-02-risk/v4-p11-receipts-pins-characterization` | 11-01, 11-02 | human:SomeRandmGuyy (batch); agent review first | CP12 |
| PR-06 | `bot-02-risk/v4-p11-quality-foundation` | 11-03, 11-04, 11-05 | human:SomeRandmGuyy (batch); agent review first | CP12 |
| PR-02 | `bot-04-sniper/v4-p11-paper-adapter-split` | 11-06 | bot-02-risk (agent) | CP12 |
| PR-03 | `bot-05-rug/v4-p11-rug-excepts-event-decoder` | 11-07 | bot-02-risk (agent) | CP12 |
| PR-04 | `bot-01-scout/v4-p11-jupiter-excepts` | 11-08 | bot-02-risk (agent) | CP12 |
| PR-05 | `bot-00-chief/v4-p11-adopt-milestone-seat-task` | 11-09 | human:SomeRandmGuyy (batch); agent review first | CP12 |
| PR-07 | `bot-09-journal/v4-p11-changelog` | 11-10 | bot-02-risk (agent) | CP12 |
| PR-08 | `bot-00-chief/v4-p11-close` | 11-11 | bot-02-risk (agent) | CP12 |

### 11-01: Receipt glob, waiver removal and the two hash pins (smoke-10m and trading smoke)

- seat bot-02-risk; wave 1; PR-01; depends_on: none; requirements: PRC-05, PRC-04, PRC-03, PRC-09.
- files: .gitignore, ci/tests/test_security_workflows.py, .github/workflows/gates.yml, ci/tests/test_no_pr_waivers.py, tests/replay/test_replay_hash_pin.py, tests/replay/test_trading_smoke_pin.py, tests/replay/pin_support.py, tests/fixtures/replay/pins/trading_smoke.json, tests/fixtures/replay/pins/trading_smoke_rows.json.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q ci/tests/test_security_workflows.py
grep -qF '!.receipts/bot-0*/v4-p*.json' .gitignore
python3 ci/gates/check_ownership.py --validate-manifest
! grep -nE 'pull_request\.number' .github/workflows/gates.yml
uv run pytest -q ci/tests/test_no_pr_waivers.py ci/tests
uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_runner_determinism.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/replay/test_trading_smoke_pin.py
python3 -c "import json;d=json.load(open('tests/fixtures/replay/pins/trading_smoke.json'));assert d['fixture']=='smoke' and len(d['events_hash'])==64 and d['seq']>1"
test -f src/pumpgrok/backtest/equity.py
grep -rq 'def is_writer' src/pumpgrok/ledger
grep -rq 'verify_stored_content' src/pumpgrok
```

### 11-02: Characterization tests for the risk engine, backtest CLI, Settings surface and seat_task before any hotspot split

- seat bot-02-risk; wave 2; PR-01; depends_on: 11-01; requirements: QLT-05, RSK-08.
- files: tests/characterization/risk/test_engine_evaluate.py, tests/risk/test_step_rows_stable.py, tests/cli/test_backtest_verb_characterization.py, tests/config/test_settings_surface_characterization.py, tests/supervisor/test_seat_task_characterization.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/characterization/risk tests/risk/test_step_rows_stable.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/cli tests/backtest
uv run pumpgrok backtest --fixture smoke-10m > /tmp/bt-a.md && uv run pumpgrok backtest --fixture smoke-10m > /tmp/bt-b.md && cmp /tmp/bt-a.md /tmp/bt-b.md
uv run pytest -q tests/config
uv run pytest -q tests/supervisor
uv run pytest -q tests/replay/test_trading_smoke_pin.py
python3 ci/gates/check_ownership.py --validate-manifest
```

### 11-03: Dev tooling lock, fast and soak test split, coverage gate, CI wiring for services, SBOM and compose hardening

- seat bot-02-risk; wave 1; PR-06; depends_on: none; requirements: QLT-01, QLT-02, QLT-07, QLT-08, QLT-09, QLT-10, PRC-10.
- files: pyproject.toml, uv.lock, .github/workflows/security-pr.yml, ci/tests/test_sbom_step.py, docker-compose.yml, tests/safety/test_compose_hardening.py, Makefile, .github/workflows/ci.yml, tests/quality/test_fast_split.py, ci/tests/test_ci_covers_services.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run python -c "import tomllib;c=tomllib.load(open('pyproject.toml','rb'));m=str(c['tool']['pytest']['ini_options']['markers']);assert 'slow' in m"
uv run python -c "import hypothesis,mutmut,pytest_cov"
uv run pytest -q ci/tests/test_sbom_step.py ci/tests/test_security_workflows.py
uv run pytest -q tests/safety/test_compose_hardening.py
uv run python -c "import yaml;yaml.safe_load(open('docker-compose.yml'))"
uv run pytest -q tests/quality/test_fast_split.py
make -n test | grep -q 'not slow'
make -n test-soak | grep -q 'm slow'
make cov
grep -n 'fail_under' pyproject.toml
test -f coverage.xml
uv run pytest -q ci/tests/test_ci_covers_services.py
make -n typecheck | grep -q services
make -n lint | grep -q services
make -n audit | grep -q services
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 11-04: Split RiskEngine._evaluate, cli/backtest.py and config/settings.py; narrow the doctor and manifests excepts

- seat bot-02-risk; wave 3; PR-06; depends_on: 11-01, 11-02; requirements: QLT-04, QLT-06.
- files: src/pumpgrok/risk/engine/core.py, src/pumpgrok/risk/engine/rules.py, src/pumpgrok/cli/backtest.py, src/pumpgrok/cli/backtest_holdout.py, src/pumpgrok/cli/backtest_paper_gate.py, src/pumpgrok/config/settings.py, src/pumpgrok/config/sections/__init__.py, src/pumpgrok/config/sections/core.py, src/pumpgrok/config/sections/engine.py, src/pumpgrok/config/sections/ops.py, src/pumpgrok/doctor.py, src/pumpgrok/core/manifests.py, tests/core/test_manifests_errors.py, tests/test_doctor_errors.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/characterization/risk tests/risk tests/safety tests/replay
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run mypy src/
uv run pytest -q tests/cli tests/backtest
uv run pytest -q tests/config tests/characterization tests/safety
uv run pytest -q tests/core tests/test_doctor_probes.py tests/test_doctor_errors.py
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 11-05: Complexity ratchet, property tests, mutation smoke and the ratchet-down after the hotspot splits

- seat bot-02-risk; wave 4; PR-06; depends_on: 11-03, 11-04, 11-06, 11-07, 11-08, 11-09; requirements: QLT-03, QLT-07, QLT-08, QLT-04, QLT-06.
- files: pyproject.toml, ci/tests/test_complexity_ratchet.py, tests/property/test_money_properties.py, tests/property/test_reducer_order_properties.py, tests/property/test_replay_determinism_properties.py, Makefile, docs/mutation-testing.md, tests/quality/test_function_size.py, tests/quality/test_no_plain_swallow.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run ruff check .
uv run pytest -q ci/tests/test_complexity_ratchet.py
uv run pytest -q tests/property
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
make mutation-smoke
test -f docs/mutation-testing.md
uv run pytest -q tests/quality ci/tests/test_complexity_ratchet.py
uv run pytest -q tests/replay/test_trading_smoke_pin.py
python3 ci/gates/check_ownership.py --validate-manifest
```

### 11-06: Characterize and split paper_adapter sell, batch and confirm

- seat bot-04-sniper; wave 2; PR-02; depends_on: 11-01; requirements: QLT-05, QLT-04.
- files: tests/characterization/execution/test_paper_adapter_sell.py, tests/characterization/execution/test_paper_adapter_batch.py, tests/characterization/execution/test_paper_adapter_confirm.py, src/pumpgrok/execution/paper_adapter/sell.py, src/pumpgrok/execution/paper_adapter/sell_stages.py, src/pumpgrok/execution/paper_adapter/batch.py, src/pumpgrok/execution/paper_adapter/batch_stages.py, src/pumpgrok/execution/paper_adapter/confirm.py, src/pumpgrok/execution/paper_adapter/confirm_stages.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/characterization/execution tests/execution
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/characterization/execution tests/execution tests/replay
uv run mypy src/
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 11-07: Narrow rug-owned plain-swallow excepts; pull forward the pump event decoder

- seat bot-05-rug; wave 2; PR-03; depends_on: 11-01; requirements: QLT-06, MKT-02.
- files: src/pumpgrok/tools/onchain/authorities.py, src/pumpgrok/tools/onchain/holders.py, tests/tools/onchain/test_onchain_errors.py, src/pumpgrok/tools/onchain/pump_events.py, tests/tools/onchain/test_pump_events.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/tools/onchain tests/characterization/test_authority_check.py tests/characterization/test_holder_check.py
uv run pytest -q tests/tools/onchain/test_pump_events.py
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 11-08: Narrow the jupiter plain-swallow except

- seat bot-01-scout; wave 2; PR-04; depends_on: 11-01; requirements: QLT-06.
- files: src/pumpgrok/tools/market/jupiter.py, tests/tools/market/test_jupiter_errors.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/tools/market tests/characterization/test_jupiter_quote.py
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 11-09: Adopt the v4 milestone, split seat_task, pull forward the read-only probe script

- seat bot-00-chief; wave 3; PR-05; depends_on: 11-01, 11-02; requirements: PRC-06, QLT-04, MKT-03; owner decisions: OD-04.
- files: .planning/ROADMAP.md, .planning/REQUIREMENTS.md, .planning/PROJECT.md, .planning/milestones/v3-ROADMAP.md, .planning/milestones/v3-REQUIREMENTS.md, src/pumpgrok/supervisor/seat_task.py, src/pumpgrok/supervisor/seat_restart.py, src/pumpgrok/supervisor/seat_relay.py, scripts/probe_pump_accounts.py, tests/desk/test_probe_pump_accounts.py.
- acceptance (run from the repo root, each exits 0):

```sh
test -f .planning/milestones/v3-ROADMAP.md
grep -qE 'Phase 11: Engineering foundation' .planning/ROADMAP.md
grep -qE 'Coverage: v4 requirements' .planning/REQUIREMENTS.md
./scripts/check.sh
uv run pytest -q tests/supervisor tests/replay
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run mypy src/
! uv run pytest tests/supervisor/test_seat_task_characterization.py -rs | grep -q SKIPPED
uv run pytest -q tests/desk/test_probe_pump_accounts.py
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 11-10: CHANGELOG entry for Phase 11 with both hash pairs

- seat bot-09-journal; wave 5; PR-07; depends_on: 11-01, 11-02, 11-03, 11-04, 11-05, 11-06, 11-07, 11-08, 11-09; requirements: PRC-03, PRC-06.
- files: CHANGELOG.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -qF 'Phase 11: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
grep -qF 'Phase 11: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 11: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 11: trading-smoke events.hash after: $p" CHANGELOG.md
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 11-11: Phase 11 close: STATE, verification record, progress table

- seat bot-00-chief; wave 6; PR-08; depends_on: 11-01, 11-02, 11-03, 11-04, 11-05, 11-06, 11-07, 11-08, 11-09, 11-10; requirements: PRC-06.
- files: .planning/STATE.md, .planning/phases/11-engineering-foundation-and-quality/11-VERIFICATION.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -q 'Phase 11' .planning/STATE.md
./scripts/check.sh
test -f .planning/phases/11-engineering-foundation-and-quality/11-VERIFICATION.md
python3 ci/gates/check_ownership.py --validate-manifest
```
