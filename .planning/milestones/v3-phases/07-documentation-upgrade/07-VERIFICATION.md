---
status: passed
phase: 07-documentation-upgrade
requirements:
  - DOC-01
  - DOC-02
  - DOC-03
  - DOC-04
verified_at_commit: da51664
prior_verification: "gaps_found at 9cb6e66 (overwritten by this run; prior file in git history). Fixes landed in fd8a707 (phase 21 round 2) and were re-checked here."
method_notes: "Commands run from /root/src/repos/pumpgrok-wt/v3-closeout at HEAD da51664 (fd8a707 on top of 9cb6e66). make lint, make typecheck, ./scripts/check.sh, the replay smoke, verify_doc_commands.sh, the tests/docs runs and the smoke-10m verify were run by this verifier; outputs in /tmp/p7d/. make test was NOT re-run (contract): criterion 1c cites the orchestrator run on 9cb6e66 (/tmp/mt-9cb6e66.txt, exit 0, 100 percent). `git diff --stat 9cb6e66 HEAD -- src tests Makefile pyproject.toml uv.lock ci scripts` is empty, so no product code changed after that run. Pytest counts are read from JUnit XML (/tmp/p7d-docs.xml, /tmp/p7d-banners.xml); console summaries were not used. CLAUDE.md citations were checked against the code with rg and sed. .planning/phases/21-close-gap-doc-03-documentation-accuracy/21-VERIFICATION.md (gaps_found at 9cb6e66, predates fd8a707) was present and read; its items were re-checked here, not re-issued. No file other than this one was edited; nothing was committed or pushed."
---
# Phase 7 Verification: Documentation upgrade

Status: passed.

All nine ROADMAP criteria pass at da51664. The three contradictions recorded at 9cb6e66 are closed by fd8a707:

1. DOC-01: the CLAUDE.md anchors at lines 93-97 now name the live gate in `src/pumpgrok/execution/live/live_gate.py` and cite `_run` by name, with correct line numbers where a number is given.
2. DOC-03: the ARCHITECTURE.md data-flow diagram no longer draws the retired vendor engine, `trades.jsonl` or `scout pipeline` as a live flow into the Desk.
3. DOC-03: "read-only" is removed as a description of the CLI and setup in README.md, ARCHITECTURE.md and SETUP.md. The phrase remains only where it describes served endpoints or `scripts/check.sh`.

Items outside the named DOC-03 set and outside the ROADMAP-fixed DOC-04 set are recorded as tech debt in the residual notes. None is an unresolved contradiction within a requirement's stated scope.

## Criteria table

| # | Criterion (ROADMAP Phase 7) | Command run | Exit | Result | Verdict |
|---|------------------------------|-------------|------|--------|---------|
| 1a | lint gate | `make lint` | 0 | ruff check: "All checks passed!"; ruff format --check: "819 files already formatted" (`/tmp/p7d/lint.txt`) | PASS |
| 1b | typecheck gate | `make typecheck` | 0 | mypy: "Success: no issues found in 208 source files" (`/tmp/p7d/typecheck.txt`) | PASS |
| 1c | test gate | `make test` not re-run (contract). Orchestrator log `/tmp/mt-9cb6e66.txt`: `uv run pytest -q` reaches `[100%]`, no failed or error lines, orchestrator reports exit 0. Product-code diff since that run is empty (`git diff --stat 9cb6e66 HEAD -- src tests Makefile pyproject.toml uv.lock ci scripts`) | 0 (orchestrator) | Evidence covers this HEAD for product code | PASS (orchestrator evidence) |
| 1d | repo check gate | `./scripts/check.sh` | 0 | "ok: 35 skills, 10 agents, 321 markdown files checked"; "PumpGrok repository structure looks healthy." (`/tmp/p7d/check.txt`) | PASS |
| 1e | paper replay smoke (PRC-01) | `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` | 0 | "trades filled=2 not_filled=1" (`/tmp/p7d/replay.txt`) | PASS |
| 2 | at least 9 named CLAUDE.md `##` sections (DOC-01) | `test "$(grep -cE '^## (Purpose\|Stack\|Layout\|Commands\|Architecture\|Conventions\|GSD artifact\|Safety\|Known gaps)' CLAUDE.md)" -ge 9` | 0 | count 9: CLAUDE.md:3, 15, 26, 45, 58, 71, 83, 91, 101 | PASS |
| 3 | every CLAUDE.md bullet cites a backticked path (DOC-01 proxy) | `! grep -nE '^\s*[-*] ' CLAUDE.md \| grep -v '`'` | 0 | 52 bullet lines; 0 bullet lines without a backtick | PASS |
| 4a | AGENTS.md shorter than f3887bb (DOC-02) | `test "$(wc -l < AGENTS.md)" -lt "$(git show f3887bb:AGENTS.md \| wc -l)"` | 0 | AGENTS.md = 133 lines; f3887bb:AGENTS.md = 423 lines; `git merge-base --is-ancestor f3887bb HEAD` succeeds | PASS |
| 4b | AGENTS.md links CLAUDE.md (DOC-02) | `grep -q "CLAUDE.md" AGENTS.md` | 0 | AGENTS.md:7 `[CLAUDE.md](CLAUDE.md)` | PASS |
| 4c | no placeholder in AGENTS.md (DOC-02) | `! grep -niE "placeholder" AGENTS.md` | 0 | 0 matches | PASS |
| 5 | verify_doc_commands.sh (DOC-02) | `./scripts/verify_doc_commands.sh` | 0 | pass=2 skip=9 fail=0 (`/tmp/p7d/doccmds.txt`); offline subset as the script header states | PASS |
| 6 | tests/docs consistency (DOC-03) | `uv run python -m pytest tests/docs -q --junitxml=/tmp/p7d-docs.xml` | 0 | JUnit: tests=44 failures=0 errors=0 skipped=0 | PASS |
| 7 | historical banner test (DOC-04) | `uv run python -m pytest tests/docs/test_historical_banners.py -q --junitxml=/tmp/p7d-banners.xml` | 0 | JUnit: tests=5 failures=0 errors=0 skipped=0 | PASS |
| 8 | CHANGELOG DOC-01..04 tags at least 4 (DOC-03) | `test "$(grep -cE 'DOC-0[1-4]' CHANGELOG.md)" -ge 4` | 0 | count 15 | PASS |
| 9 | replay hash stable and recorded | `uv run pumpgrok verify --fixture smoke-10m` run twice; `a = b = b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`; `verify=CONSISTENT seq=2 events=41`; CHANGELOG.md:147 `- Phase 6: smoke-10m events.hash after: b69c...ad32d`; CHANGELOG.md:128 `- Phase 7: smoke-10m events.hash after: b69c...ad32d` | 0 | hash equal across runs and recorded under Phase 6 and Phase 7 | PASS |

Criterion 1 requires exit 0 for all four commands and the replay. Criterion 1c rests on the orchestrator log for the verified commit. Criterion 6 was run in the `python -m pytest` form given in the assignment; it is the same suite as the ROADMAP's `pytest -q tests/docs/`.

## Requirements table

| ID | Status | Evidence |
|----|--------|----------|
| DOC-01 | SATISFIED | Criteria 2 and 3 pass. Every CLAUDE.md numeric anchor and named citation was checked against the code (table below). The three 9cb6e66 defects are fixed by fd8a707, and no wrong anchor remains. |
| DOC-02 | SATISFIED | AGENTS.md is 133 lines against 423 at f3887bb (criterion 4a). It links CLAUDE.md at AGENTS.md:7 (4b). It has no placeholder (4c). It has no `GSD:(stack\|conventions\|architecture\|skills\|profile)-start` block (grep exit 1). Commands are verified by criterion 5 (pass=2 skip=9 fail=0). |
| DOC-03 | SATISFIED | Criterion 6 passes. The named-set residual scan is clean (table below). The ARCHITECTURE diagram and the "read-only" wording are corrected. Plugin versions match `pyproject.toml:3`. |
| DOC-04 | SATISFIED (ROADMAP-fixed set) | Criterion 7 passes (tests=5, failures=0). `head -n1` of each file in the fixed set reads `Historical design record`: `docs/DISCOVERY.md`, `docs/MIGRATION_MAP.md`, `docs/upgrade-plan-desk-v2.md`, `docs/design/interfaces.md`, `docs/design/paper-engine.md`. `docs/design/` holds only the last two. Scope note on `docs/ROSTER.md` and `docs/FOUNDATION_STACK.md` is in the residual notes. |

### DOC-01 anchor audit (CLAUDE.md, at da51664)

| CLAUDE.md line | Citation | Code check | Verdict |
|----------------|----------|------------|---------|
| 63 | `supervisor.py:36-37`, `TICK_S = 1.0` | `sed -n 34,38p`: line 36 is the comment, line 37 is `TICK_S = 1.0` | Correct |
| 64 | `open_replay_runtime` builds `PaperAdapter` | `def open_replay_runtime` at `replay_runtime.py:176`; `PaperAdapter(` at :233 | Correct |
| 66 | `price.py` reads the curve with `getAccountInfo`, no Jupiter path | `price.py` docstring: `getAccountInfo`; line 5 "no Jupiter quote path exist in this module" | Correct |
| 68 | `jupiter.py` holds `QUOTE_URL`, never calls `/execute` | `jupiter.py:27` `QUOTE_URL = "https://api.jup.ag/swap/v2/order"`; line 4 "Never /execute, /build or /submit" | Correct |
| 69 | `_serve_replay_loop` in verbs_state.py | `verbs_state.py:120` | Correct |
| 80 | `RpcSettings.endpoints` default; no `--rpc` in parsing.py | `settings.py:85` default `https://api.mainnet-beta.solana.com`; `rg -- --rpc parsing.py` exit 1 | Correct |
| 93-94 | Live preconditions in `live_gate.py`; `_run` enforces | `PRECONDITION_IDS` `live_gate.py:38`; `_run` `verbs_state.py:87`, gate at :88-100 | Correct |
| 96 | `--record`, `--duration` exit not-implemented, `_run` | `verbs_state.py:101-102` | Correct |
| 97 | `run --mode live` refuses with exit 3 (`EXIT_LIVE`) | `verbs_state.py:88` `LiveGate(`, :100 `return EXIT_LIVE`; `codes.py:13` `EXIT_LIVE = 3` | Correct |
| 98-99 | Key-bearing endpoints refused; `api_key` sent as header | `settings.py:80` and :585-586 refusal; `tools/onchain/rpc.py:127-130` sends `x-api-key` | Correct |
| 105 | `[ASSUMED]` curve layout | `curve_layout.py:3`; `scripts/probe_curve_layout.py` exists | Correct |
| 106 | `run_once_replay` in serve.py; `run_replay` writes verdict first, no paper adapter | `serve.py:47`; `runner.py:148` docstring; no `PaperAdapter` construction in runner.py | Correct |

Named symbols and paths without numeric anchors were checked by existence and content: `ownership.yaml` (bot-00-chief at :8, bot-09-journal at :47, last match wins), `ci/gates/check_ownership.py`, `replay/clock.py` (`Clock`, `WallClock`, `FixtureClock`), `core/ids.py` (re-exports `Clock`), `core/units.py`, `core/risk_budget.py`, `tools/exec/quote.py` (imports `ExecutionAdapter` from `core/adapter.py`), `config/settings.py` (`PUMPGROK_` prefix, `__` nested delimiter), `Makefile` targets (`sync` runs `uv sync --frozen --group dev`; `check`; `gates` with `.receipts/$(BOT)/$(TASK).json`), `pyproject.toml` (`requires-python`, `python_version = "3.12"`, `strict = true`), `rules/pumpgrok-team.mdc`, `contracts/events`, `contracts/tool-rosters`, `scripts/assemble-prompts.sh`, `scripts/generate-templates.py`, `src/pumpgrok/cli/verbs_ops.py` (doctor verb), `risk/engine/core.py`, `agents/risk.md`, `skills/momentum-signals/SKILL.md`, 35 skill directories, 10 seat files in `agents/`. All exist and match.

### DOC-03 residual scan (README.md, ARCHITECTURE.md, SETUP.md, skills/replay-and-backtest/SKILL.md)

| Pattern | Result at da51664 | Evidence |
|---------|-------------------|----------|
| `eight` / `Eight` | 0 hits | `rg -n` over the four files |
| `ticket_helper` | 0 hits | `rg -n` |
| `paper_sim` | 0 hits | `rg -n` |
| `/workspace/trading-desk` | 0 hits | `rg -n`; the operator folder is `$HOME/trading-desk` (ARCHITECTURE.md:40, :179, :201; SETUP.md:6, :47, :50, :55-56, :168, :184) and matches `scripts/hermes-bootstrap.sh:8` |
| `--rpc` | 0 hits | `rg -n` |
| `no server, queue` / `started as a service` | 0 hits in the named set. ARCHITECTURE.md:55 "Only one repo process ever runs as a service" is qualified: it is the paper `--serve` replay form only | `rg -n` |
| `config.example.yaml` | 0 hits in the named set; `docs/VENDOR_PIN.md:25` says the file is not in this checkout | `rg -n`; `ls config.example.yaml` absent |
| `market.price` | README.md:43 (help form); ARCHITECTURE.md:27, :118 describe a `getAccountInfo` curve read (ASSUMED layout), matching `tools/market/price.py` | `rg -n` |
| present-tense vendor | None. Every hit is qualified as absent, formerly vendored, or retired: README.md:12, :65; ARCHITECTURE.md:15, :31, :33, :62, :77, :81, :194, :205; SETUP.md:145-147 | `rg -n -i vendor` over the four files |
| bare `ticket next` as a read-only check | None. SETUP.md:136, :203 and README.md:46 are `pumpgrok ticket next --help`. ARCHITECTURE.md:144, :168, :180, :192 and README.md:14, :52 describe allocation, which `ledger/tickets.py:90` (`store.append_batch([row])`) performs | `rg -n "ticket next"` |
| "read-only" as a description of the CLI or setup | None in README.md, SETUP.md, or the replay SKILL. ARCHITECTURE.md:18, :55, :217 describe served `/healthz` and `/metrics`; :78 describes `scripts/check.sh`, which has no write operation | `rg -n -i "read-only\|read only"` |
| replay skill overclaim (`same code path`, `identical path`) | 0 hits | `rg -n -i` on `skills/replay-and-backtest/SKILL.md` |

### DOC-03 ARCHITECTURE mermaid check

- Block 1 (ARCHITECTURE.md:35-51) nodes: Human, Host, Pack, Desk, Jup, Rpc, Web. Edges: Human-->Host, Host-->Pack, Host-->Desk, Host-->Web, Pack-->Jup, Pack-->Rpc. No Vendor, Jsonl or Bridge node or edge.
- Block 2 (ARCHITECTURE.md:151-164) is the seat-flow diagram. It has no Vendor, Jsonl or Bridge node. Its one case-insensitive `scout` match is the seat label `SCOUT LEAD`, not the `scout pipeline` verb.
- Awk scan of all mermaid fences for `vendor|jsonl|bridge|scout|trades`: one match, `SCOUT LEAD`.
- Textual check only: the diagram was not rendered.

### DOC-03 plugin version statements

All six plugin manifests carry `"version": "0.1.0"`, equal to `pyproject.toml:3`: `plugin.json:5`, `.claude-plugin/plugin.json:4`, `.claude-plugin/marketplace.json:10`, `.cursor-plugin/plugin.json:4`, `.grok-plugin/plugin.json:4`, `.grok-plugin/marketplace.json:10`. The marketplace descriptions read "Ten-seat". No "Eight" appears in any of the six.

## Residual notes (tech debt; none is an unresolved contradiction within a requirement's stated scope)

1. **DOC-04 scope, `docs/ROSTER.md` and `docs/FOUNDATION_STACK.md`.** Both are design documents ("Design document only ...") with no banner. They are outside the ROADMAP-fixed set in `tests/docs/test_historical_banners.py`, which criterion 7 and the DOC-04 requirement text both use. Phase 21 decision D-10 kept them out of scope. If Main treats them as historical design records, each needs the banner and the test list needs both entries. Related: `docs/ROSTER.md:6` says "today's eight `agents/*.md` files". Ten seat files exist, so the line is stale. The `desk.* core eight` references in ROSTER.md (lines 176, 197, 218) count tool groups, not seats, and are correct.
2. **Eight-role wording outside the DOC-03 named set.** `agents/README.md:3` ("Eight specialist Bots") and `:16` ("All eight roles"); `skills/desk-operating-model/SKILL.md:3` and `:18` ("eight roles"); `scripts/hermes-bootstrap.sh:2` ("eight PumpGrok roles") and `:214`; `scripts/README.md:8` ("eight isolated Hermes profiles"). The first two and the SKILL line were re-confirmed this run. The Hermes script lines were carried from the phase 21 summary and not re-checked against its ROLES list. None is in the DOC-03 named set.
3. **`.claude-plugin/plugin.json:3`.** The description says "Ten-seat" but its parenthetical lists eight names (CHIEF, SCOUT, RISK, WHALE, SNIPER, RUG, EXIT, SHILL). This is a description, not a version statement, so it is outside DOC-03.
4. **`skills/holder-and-flow-analysis/SKILL.md:27`** cites `/workspace/pumpgrok/tools/holder_check.py`, which does not exist. Carried from the phase 21 summary, not re-checked this run.
5. **`docs/VENDOR_PIN.md:9`** gives the license as `vendor/grokbot-pumpfun/LICENSE`, which is absent. The retained copy is `src/pumpgrok/engine/LICENSE-grokbot-pumpfun`. **`:24-25`** say the vendored runtime artefacts "are gitignored there". Both sit inside a file that calls itself the historical provenance record, so neither is a present-tense claim. A follow-up can repoint line 9.
6. **`CHANGELOG.md:123`** (Phase 7 entry) says DOC-03 corrected the four plugin manifests to version 0.1.0 "to match the code". At that time the two marketplace manifests were at 1.0.0. The phase 21 entry at `CHANGELOG.md:5-9` records the correction. The Phase 7 entry is a historical record and was left unchanged.
7. **No recurrence guard for two DOC-03 items.** `tests/docs` does not inspect the ARCHITECTURE mermaid diagram or the "read-only" wording. Both pass today by manual check, and the suite passes with either defect present (as at 9cb6e66).
8. **`21-VERIFICATION.md`** (phase 21, gaps_found at 9cb6e66) predates fd8a707. Its items were re-checked here and are closed. It was not re-issued by this run.
9. **Not executed:** `make test` (orchestrator evidence only, per contract); setup commands that write to `$HOME` or clone (`mkdir`, `touch`, `git clone`, `uv sync` in SETUP.md); the mermaid render; `verify_doc_commands.sh` skip=9 entries (make targets, `run --serve`, docker are name-checked, not run; this is the documented disposition in the script header).
10. **Read-only wording kept on purpose:** ARCHITECTURE.md:18, :55, :217 (served `/healthz` and `/metrics`) and :78 (`scripts/check.sh`), per the 21-01 round 2 decision.
