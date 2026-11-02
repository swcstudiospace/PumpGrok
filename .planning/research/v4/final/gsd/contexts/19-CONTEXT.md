# Phase 19 CONTEXT: Observability, docs, hardening and milestone audit

Milestone v4, Phase 19. Goal per ROADMAP: operators can see the event runtime, sources, Grok budget, strategy stages and kills, and signer attestation in doctor, health.json and metrics; alert rules name only real metrics; the docs, skills and runbooks describe v4 and every documented command runs; a nightly event-mode soak guards the idle-zero-Grok invariant; the amendment waiver is gone; and a human-gated milestone audit traces every v4 requirement to evidence and records that live is still refused. After checkpoint 19 only the human arm procedure remains, and live is still exit 3.

Depends on: Phases 17 and 18 (all plans), Phase 16 (19-02 reads 16-04), Phase 13 (19-01 reads 13-02), Phase 14 (14-04 metric names). Reuses without re-implementing: supervisor/metrics.py NINE_FAMILIES and metrics_events.py, health.json writer, doctor.py probes, ci/gates/run_all.py, scripts verify_doc_commands.

## Locked decisions (NON-NEGOTIABLE)

- D-01: Money integer lamports; Decimal only for ratios.
- D-02: Clock-only time; dashboards and doctor read state, they add no timers.
- D-03: Live stays refused: `uv run pumpgrok run --mode live --once; test $? -eq 3` is part of the audit on the FINAL tree, and the audit never arms anything.
- D-04: hashes are identity only; the audit cites hash lines, it never uses a hash as a verdict.
- D-05: mypy --strict, ruff, no dead code, no swallowed errors, no placeholders, ASCII-only docs.
- D-06: Metric tests live under tests/desk (chief-owned): tests/desk/test_health_event_sections.py and tests/desk/test_metrics_strategy.py; O2t (risk, importorskip) is deleted. The nine existing families stay unchanged; per-strategy P (performance) and live-path L families register only in event mode.
- D-07: Alert rules name only metrics present in the registry (a test reads the rules and the registry); risk-owned docs (ARCHITECTURE, CLAUDE, AGENTS) describe v4 after the amendment merged (19-05 after 18-07).
- D-08: Doctor reports signer attestation by calling the signer over the socket, read-only; it also checks key custody (no key-like env names) and time sync; the HMAC key in a live desk env is flagged.
- D-09 (PRC-19, plan 19-04): the ONLY plan allowed to follow the amendment PR in .github/workflows/gates.yml: it removes the step-scoped waiver and restores the empty waiver set in ci/tests/test_no_pr_waivers.py. After it, `! grep -nE 'pull_request\.number' .github/workflows/gates.yml` passes again.
- D-10 (OD-18): nightly soak is a GitHub Actions `schedule` trigger at 03:00 UTC in ci.yml selecting `-m slow` (3 virtual days of event-mode soak, about 50 minutes with the other soaks); per-plan acceptance uses the fast path, never the full soak. The soak golden hash is recorded in CHANGELOG by 19-06.
- D-11: Docs are split by owning seat: risk (ARCHITECTURE, CLAUDE, AGENTS), chief (README, SETUP, desk skills, runbooks for datafeed, recorder, promotion), signal (skill replay-and-backtest), scout (skill solana-market-data). Every documented command runs (verify_doc_commands). Claims avoid exhaustive wording unless a command proves it.
- D-12 (AUDIT-19, plan 19-08, human-gated): every v4 requirement id from plans.json is traced to a file, test or command with evidence; criterion 9 reads every phase's CHANGELOG hash lines (so it follows 19-06); the result is reported to the owner, who alone decides the arm procedure (OD-19). The receipt is committed WITHOUT approved_by.
- D-13: Phase 19 close (19-09) archives the milestone in .planning (STATE, ROADMAP progress, milestone archive) and is the last plan of v4; it runs after 18-11.

## Grey-area defaults

- G-01: Doctor v4 report is read-only and exits nonzero only on refusal conditions (double triggers, skew, key-like env); warnings do not fail it. Reason: same convention as existing probes.
- G-02: health.json gains event and strategy sections only when wake_mode is event. Reason: cadence default output stays byte-identical.
- G-03: Final hash lines: smoke-10m `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` EQUAL; trading-smoke equals the post-Phase-15 pin in tests/fixtures/replay/pins/trading_smoke.json.

## Phase boundary

In scope: supervisor health and metrics extensions (chief), doctor.py v4 report, ci.yml nightly job, alert rules and their test, docs and skills listed in the plans, CHANGELOG closeout, the audit file under .planning, the milestone archive. Out of scope: any new runtime behavior, live arming, signer changes, new strategies.

## Canonical references

src/pumpgrok/supervisor/{metrics,metrics_events,health}.py, src/pumpgrok/doctor.py, .github/workflows/{ci,gates}.yml, ci/tests/test_no_pr_waivers.py, skills/ (solana-market-data, replay-and-backtest, desk operating skills), docs/runbooks/, CHANGELOG.md, .planning/{ROADMAP,STATE,REQUIREMENTS}.md, research/pr-plan.md sections 5 and 6, research/owner-decisions.md OD-18, OD-19.

## Existing code insights

- docs and CHANGELOG record before and after replay hash lines per phase (Phases 6 to 10 precedent); equal pairs are recorded, not skipped.
- The full `pytest -q` including soak is about 50 minutes, which is why it is the nightly job and not a per-plan command.
- Shared-file chains: ci.yml 11-03, 14-07, 19-04; gates.yml 11-01, 18-07, 19-04; README, SETUP 18-07 then 19-07; AGENTS and ARCHITECTURE 18-07 then 19-05; CHANGELOG ends with 19-06.

## Specifics

- Audit file path and receipt fields: the receipt commands and exit codes of the success criteria of ALL nine phases, run on the integration tree; `unverified` lists every REVIEW default (OD-03, OD-09, OD-16) still unreviewed.
- Checkpoint 19 batch of human receipts: PR-34, PR-35, PR-36, PR-37, PR-43, PR-45.

## Deferred ideas

Grafana dashboards beyond alert rules; flipping wake_mode default after a week of live-paper evidence (OD-20); a milestone v5 scoped to PumpSwap sells and direct instruction building.

## Ownership, receipt and hash rules (every plan of this phase)

- Branch `bot-0N-seat/v4-pPHASE-slug`, one PR per (phase, seat) (PR table below). Receipt `.receipts/bot-0N-seat/v4-pPHASE-slug.json` (task_id = slug, branch = the branch), tracked through the glob `!.receipts/bot-0*/v4-p*.json` from plan 11-01; no other seat edits .gitignore.
- `approved_by` is NEVER self-written and a seat never approves its own work. An agent reviewer (chief for risk-authored work, risk for other seats) reads the diff; human-gated receipts are committed WITHOUT approved_by and the owner adds `human:SomeRandmGuyy` in a batch at the ship checkpoint (after phases 12, 14, 17, 19).
- Seat purity: every path resolves to the plan seat via `resolve_owner(path, load_manifest(DEFAULT_MANIFEST))`; tests/** is risk except tests/desk/** (chief) and tests/engine/** (signal); execution/** sniper; cli/** risk; supervisor/** chief. A foreign-test failure gets a one-file companion plan by the owning seat, merged first.
- Replay hashes: smoke-10m `events.hash` is `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` (seq=2 events=41, verdict and rollover rows only). Trading `smoke` (5 events, seq 11) gave `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54` at HEAD 641927c; plan 11-01 pins it at v4-base; it moves only in plan 15-01. Run receipts in a fresh worktree without var/ledger.sqlite.
- Live stays refused: `uv run pumpgrok run --mode live --once; test $? -eq 3`; nothing arms it.
- Acceptance lines are real commands; exit 0 means success. The G-2 bypass family (collect-only, `--co`, `|| true`, stderr to /dev/null, `--force`, `--dry-run`, inline PUMPGROK_LIVE_ENABLE) never appears; `! cmd -rs | grep -q SKIPPED` proves no skips. Plans touching src also run make lint and make typecheck.


## Plans (9 planned; research/plans.json is the source)

Pull requests in merge order (numbers from research/pr-plan.md):

| PR | Branch | Plans | Approver | Checkpoint |
|----|--------|-------|----------|------------|
| PR-40 | `bot-01-scout/v4-p19-market-data-skill` | 19-01 | bot-02-risk (agent) | CP19 |
| PR-41 | `bot-08-signal/v4-p19-backtest-skill` | 19-02 | bot-02-risk (agent) | CP19 |
| PR-42 | `bot-00-chief/v4-p19-health-metrics` | 19-03 | bot-02-risk (agent) | CP19 |
| PR-43 | `bot-02-risk/v4-p19-doctor-soak-alerts-docs` | 19-04, 19-05 | human:SomeRandmGuyy (batch); agent review first | CP19 |
| PR-44 | `bot-09-journal/v4-p19-changelog` | 19-06 | bot-02-risk (agent) | CP19 |
| PR-45 | `bot-00-chief/v4-p19-docs-audit-close` | 19-07, 19-08, 19-09 | human:SomeRandmGuyy (batch); agent review first | CP19 |

### 19-01: Skill solana-market-data covers the live feed, watch set and fail-closed price rules

- seat bot-01-scout; wave 1; PR-40; depends_on: 11-01, 13-02; requirements: OBS-04.
- files: skills/solana-market-data/SKILL.md.
- acceptance (run from the repo root, each exits 0):

```sh
./scripts/verify_doc_commands.sh
uv run pytest -q tests/test_skill_manifests.py
python3 ci/gates/check_ownership.py --validate-manifest
```

### 19-02: Skill replay-and-backtest covers record, trim, import, strategy backtest and autonomous runs

- seat bot-08-signal; wave 1; PR-41; depends_on: 11-01, 16-04; requirements: OBS-04.
- files: skills/replay-and-backtest/SKILL.md.
- acceptance (run from the repo root, each exits 0):

```sh
./scripts/verify_doc_commands.sh
uv run pytest -q tests/test_skill_manifests.py
python3 ci/gates/check_ownership.py --validate-manifest
```

### 19-03: health.json event and strategy sections, per-strategy P and live L metric families

- seat bot-00-chief; wave 1; PR-42; depends_on: 11-01, 14-04, 17-04; requirements: OBS-02.
- files: src/pumpgrok/supervisor/health.py, src/pumpgrok/supervisor/metrics_events.py, tests/desk/test_health_event_sections.py, tests/desk/test_metrics_strategy.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/supervisor/test_metrics.py tests/desk/test_health_event_sections.py tests/desk/test_metrics_strategy.py
! uv run pytest tests/desk/test_health_event_sections.py -rs | grep -q SKIPPED
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 19-04: Doctor v4 report, nightly event-mode soak and removal of the amendment waiver

- seat bot-02-risk; wave 1; PR-43; depends_on: 11-03, 14-07, 17-02, 17-03, 17-04, 18-02, 18-07; requirements: OBS-01, OBS-06, PRC-08; owner decisions: OD-18.
- files: src/pumpgrok/doctor.py, tests/test_doctor_v4.py, tests/soak/test_soak_event_mode.py, .github/workflows/ci.yml, .github/workflows/gates.yml, ci/tests/test_no_pr_waivers.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/test_doctor_v4.py tests/test_doctor_probes.py tests/test_doctor_event_mode.py
PUMPGROK_REQUIRE_SOAK=1 uv run pytest -q -m slow tests/soak/test_soak_event_mode.py
! grep -nE 'pull_request\.number' .github/workflows/gates.yml
uv run pytest -q ci/tests
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 19-05: Alert rules checked against the metric registry; risk-owned docs describe v4

- seat bot-02-risk; wave 2; PR-43; depends_on: 14-04, 18-07, 19-03; requirements: OBS-03, OBS-04.
- files: docs/observability/alerts.yaml, docs/observability/README.md, tests/docs/test_alert_rules.py, ARCHITECTURE.md, CLAUDE.md, AGENTS.md, docs/quality-gates.md.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/docs/test_alert_rules.py
./scripts/verify_doc_commands.sh
./scripts/check.sh
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 19-06: CHANGELOG v4 closeout entry with the final hash lines

- seat bot-09-journal; wave 3; PR-44; depends_on: 19-01, 19-02, 19-03, 19-04, 19-05; order_after 18-10; requirements: PRC-03, PRC-06.
- files: CHANGELOG.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -qF 'Phase 19: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
grep -qF 'Phase 19: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 19: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 19: trading-smoke events.hash after: $p" CHANGELOG.md
for p in 11 12 13 14 15 16 17 18 19; do grep -qF "Phase $p: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md || exit 1; done
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 19-07: Docs (chief-owned): README, SETUP, desk skills, datafeed, recorder and promotion runbooks

- seat bot-00-chief; wave 2; PR-45; depends_on: 11-01, 16-04, 18-07, 19-04; requirements: OBS-04.
- files: README.md, SETUP.md, skills/desk-doctor/SKILL.md, skills/desk-monitoring/SKILL.md, docs/runbooks/datafeed.md, docs/runbooks/recorder.md, docs/runbooks/promotion.md.
- acceptance (run from the repo root, each exits 0):

```sh
./scripts/verify_doc_commands.sh
./scripts/check.sh
python3 ci/gates/check_ownership.py --validate-manifest
```

### 19-08: Milestone audit: every v4 requirement traced to evidence, live still refused

- seat bot-00-chief; wave 4; PR-45; depends_on: 19-01, 19-02, 19-03, 19-04, 19-05, 19-06, 19-07; requirements: OBS-05; HUMAN-GATED; owner decisions: OD-19.
- files: .planning/milestones/v4-MILESTONE-AUDIT.md, .planning/MILESTONES.md.
- acceptance (run from the repo root, each exits 0):

```sh
test -f .planning/milestones/v4-MILESTONE-AUDIT.md
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 19-09: Phase 19 close: STATE, milestone archive, progress table

- seat bot-00-chief; wave 5; PR-45; depends_on: 19-01, 19-02, 19-03, 19-04, 19-05, 19-06, 19-07, 19-08; order_after 18-11; requirements: PRC-06.
- files: .planning/STATE.md, .planning/ROADMAP.md, .planning/phases/19-observability-docs-hardening-and-milestone-audit/19-VERIFICATION.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -q 'Phase 19' .planning/STATE.md
./scripts/check.sh
test -f .planning/phases/19-observability-docs-hardening-and-milestone-audit/19-VERIFICATION.md
python3 ci/gates/check_ownership.py --validate-manifest
```
