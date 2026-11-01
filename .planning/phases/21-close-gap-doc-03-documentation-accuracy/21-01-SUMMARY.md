---
phase: 21-close-gap-doc-03-documentation-accuracy
plan: 01
requirements-completed: [DOC-03]
---

# Phase 21 plan 01 summary: close DOC-03 (documentation accuracy)

Worktree: /root/src/repos/pumpgrok-wt/v3-closeout, branch bot-00-chief/v3-closeout.
Commits: 1128f0a (test, red then green), c6d8610 (documents, manifests, CHANGELOG), and this summary commit (docs(planning)).
No product code under src/ changed. Nothing pushed or merged.

## 1. Red evidence (D-02)

Test change: `tests/docs/test_doc_consistency.py` now covers all six plugin manifests for the package version (marketplace files read per plugin entry) and adds `test_plugin_manifest_descriptions_avoid_eight_role`.

Run on the tree before any document edit (commit 1128f0a, documents at e58920b):

    uv run python -m pytest tests/docs/test_doc_consistency.py -q --junitxml=/tmp/phase21-red.xml
    exit 1; junit tests=5 failures=2 errors=0 skipped=0

Failure text (from /tmp/phase21-red.xml and /tmp/phase21-red.log):

    FAILED test_plugin_manifest_versions_match_pyproject
    AssertionError: .claude-plugin/marketplace.json version '1.0.0' != pyproject version '0.1.0'
    assert '1.0.0' == '0.1.0'

    FAILED test_plugin_manifest_descriptions_avoid_eight_role
    AssertionError: .claude-plugin/marketplace.json description still says 'Eight-role':
    'Eight-role Solana memecoin trading desk with hard security constitution, RISK absolute veto, and Jupiter execution.'

Each assertion stops at the first failing file, so `.grok-plugin/marketplace.json` (version 1.0.0, description "Eight-role ...") is not in the message. Both fields were read from the file at HEAD. The fix covers it.

Note: the console summary in this environment is unreliable (it printed "No tests collected" for a file that has tests). Counts above come from the junit XML and the exit code.

## 2. Manifest and CHANGELOG changes (D-03, D-08)

| File | Line | Old | New | Evidence |
|------|------|-----|-----|----------|
| `.claude-plugin/marketplace.json` | 9 | "Eight-role Solana memecoin trading desk ..." | "Ten-seat Solana memecoin trading desk ..." (rest unchanged) | AGENTS.md:26 "The ten seats"; agents/ holds 10 role files |
| `.claude-plugin/marketplace.json` | 10 | `"version": "1.0.0"` | `"version": "0.1.0"` | pyproject.toml:3 `version = "0.1.0"` |
| `.grok-plugin/marketplace.json` | 9 | "Eight-role Solana memecoin trading desk for Grok Build. ..." | "Ten-seat ... for Grok Build. ..." (rest unchanged; "35 skills" kept, count is 35) | same; `ls skills/*/SKILL.md` = 35 |
| `.grok-plugin/marketplace.json` | 10 | `"version": "1.0.0"` | `"version": "0.1.0"` | pyproject.toml:3 |
| `CHANGELOG.md` | 5-12 | (none) | one entry "[Unreleased] - v3 Phase 21: DOC-03 documentation accuracy" above the Phase 20 entry, with four bullets: manifests, ARCHITECTURE, SETUP, README | D-08 |

The replay hash line in CHANGELOG (Phase 20 entry, line 9 and the verified lines) is unchanged.

## 3. ARCHITECTURE.md, SETUP.md, README.md change table (D-04, D-05, D-06)

Row keys: "pattern" is yes when the HEAD line matches `eight|Eight|vendor/grokbot-pumpfun|trading-desk|ticket_helper|paper_sim|--rpc|no server, queue|started as a service|market.price`. Line numbers are HEAD numbers. Pipes inside cells are written as "or".

### 3a. ARCHITECTURE.md

| # | Line | Pattern | Old text (abbrev.) | New text (abbrev.) | Evidence path |
|---|------|---------|--------------------|--------------------|---------------|
| A1 | 15 | yes | `vendor/grokbot-pumpfun/` "Vendored third-party screening engine" | "Screening engine (`src/pumpgrok/engine/`)": replay-only port; `vendor/grokbot-pumpfun/` absent from this checkout; formerly vendored (see `docs/VENDOR_PIN.md`) | `ls vendor` -> no such directory; src/pumpgrok/engine/__init__.py:1-6; docs/VENDOR_PIN.md:3-5 |
| A2 | 27 | yes | "...; the only price the fill model uses" | "...Paper fills and marks read the curve through the paper adapter's `_read_curve` port and price with `execution/curve_math.py`" | src/pumpgrok/tools/market/price.py; src/pumpgrok/execution/paper_adapter/adapter.py:152; marks.py:9 imports curve_math; grep finds no market.price use under src/pumpgrok/execution or supervisor |
| A3 | 31 | yes | "Called only by operator-run processes of the vendored engine (see skills/grokbot-pipeline)" | "Endpoints declared in config/settings.py. In-tree REST analyzer and pump.fun read client call pump.fun REST; read client not registered as a tool; no WS or x.ai client in this tree; the retired vendor engine made these calls" | src/pumpgrok/config/settings.py:60-61, 101; src/pumpgrok/engine/analyzer.py:1-16; src/pumpgrok/tools/social/client.py:1-12; grep for websockets / x.ai call sites: none |
| A4 | 33 | yes | "the vendored `vendor/grokbot-pumpfun` component keeps its own GROKBOT_* contract" | "the retired vendor engine (absent from this checkout; see docs/VENDOR_PIN.md) kept its own GROKBOT_* contract"; adds "The paper ledger is one SQLite file, `var/ledger.sqlite`" | src/pumpgrok/ledger/paths.py:22-23; src/pumpgrok/ledger/store.py imports sqlite3; grep GROKBOT_ in src, tests, ci: only a comment at settings.py:297 |
| A5 | 40 | yes | mermaid node `/workspace/trading-desk files` | `$HOME/trading-desk files (operator host folder)` (see D-04(c) note in section 4) | scripts/hermes-bootstrap.sh:8 `DESK="${PUMPGROK_DESK:-${HOME}/trading-desk}"` |
| A6 | 68 | yes | "Vendor engine dry-run screen ... operator-run process from vendor/grokbot-pumpfun ... mode: live is an upstream stub" | "Screening engine dry-run (retired vendor process): `skills/grokbot-pipeline` describes the procedure; the vendor process is absent from this checkout" | ls vendor (absent); skills/grokbot-pipeline/SKILL.md exists |
| A7 | 87 | yes | "**Vendored components.** `vendor/grokbot-pumpfun/` sits outside ... see vendor/grokbot-pumpfun/PUMPGROK.md ... check.sh excludes vendor/ markdown from its emoji sweep ... `pumpgrok scout pipeline --candidates` ... prints fail-closed JSON plus a PIPELINE-EVIDENCE block" | "**Retired vendor components.** Absent from this checkout; formerly vendored (see docs/VENDOR_PIN.md, pin 409e74c...). Ported in-tree as `src/pumpgrok/engine/`. `scout pipeline --candidates` is registered but not implemented: exits 5 with `status: not-yet-implemented`." Removed the check.sh vendor-exclusion claim | `grep -n vendor scripts/check.sh` -> only line 105 (pin check); `uv run pumpgrok scout pipeline --candidates` -> exit 5, `{"ok": false, "status": "not-yet-implemented", ...}` |
| A8 | 122 | yes | `market.price` tool row | unchanged (resolved) | src/pumpgrok/tools/market/price.py exists; `uv run pumpgrok tools market.price --help` exit 0 |
| A9 | 172 | yes | "`ticket_helper.py` also exits 1 on invalid ids, duplicate proposals, and unknown commands" | "Ticket IDs are allocated by `pumpgrok ticket next` (`src/pumpgrok/ledger/tickets.py`), with a bounded retry on UNIQUE collisions (`MAX_ATTEMPTS`)" | src/pumpgrok/ledger/tickets.py:1-25; `uv run pumpgrok ticket next --help` exit 0 |
| A10 | 174 | yes | "**paper** (`paper_sim.py`)" | "**paper** (`pumpgrok run --mode paper`; canonical ledger `var/ledger.sqlite`; `pumpgrok paper buy` and `paper sell` refuse with code `unavailable` until the Phase 4 curve reader is verified)"; also ASCII punctuation in the same sentence | src/pumpgrok/cli/codes.py:37-40 (_TRADE_UNAVAILABLE); src/pumpgrok/cli/verbs_state.py:178-197; ledger/paths.py:22 |
| A11 | 183 | yes | `/workspace/trading-desk/` tree root | `$HOME/trading-desk/` (operator host folder, outside the repository) | scripts/hermes-bootstrap.sh:8 and :217 (`mkdir -p "${DESK}"/{proposals,briefs,leads,research,journal,incidents,positions,watch}`) |
| A12 | 184 | yes | `proposals/     ticket_helper.py create` | `proposals/     operator folder; ticket IDs come from pumpgrok ticket next` | `find . -name 'ticket_helper*'` -> no file; src/pumpgrok/ledger/tickets.py |
| A13 | 188 | yes | `journal/       paper_sim.py appends paper-YYYY-MM-DD.md` | `journal/       operator folder; the ledger of record is var/ledger.sqlite` | `find . -name 'paper_sim*'` -> no file; src/pumpgrok/ledger/paths.py:22 |
| A14 | 196 | yes | "ticket_helper.py uses /workspace/trading-desk/proposals ... paper_sim.py defaults --desk /workspace/trading-desk" | "Ticket IDs come from `pumpgrok ticket next`, `create` or `list` (ledger/tickets.py); scripts/hermes-bootstrap.sh defaults the desk folder to `${HOME}/trading-desk` (PUMPGROK_DESK overrides it) and creates the folders listed above" | ledger/tickets.py; scripts/hermes-bootstrap.sh:8, :217 |
| A15 | 198 | yes | "the in-tree `vendor/grokbot-pumpfun/` engine" | "the in-tree screening engine `src/pumpgrok/engine/` (ported from the retired vendor tree, see docs/VENDOR_PIN.md)" | src/pumpgrok/engine/__init__.py:1-6 |
| A16 | 205 | yes | "`--desk` flag, default `/workspace/trading-desk` in paper_sim.py" | "`PUMPGROK_DESK` env var: scripts/hermes-bootstrap.sh, hermes-install-cron.sh, hermes-verify-isolation.sh (default `${HOME}/trading-desk`; their `--desk` flag overrides it)" | `grep -rn '"--desk"' src` -> no hit; scripts/hermes-bootstrap.sh:8, hermes-install-cron.sh:7, hermes-verify-isolation.sh:7 |
| A17 | 207 | yes | `/workspace/trading-desk/desk.md` | `$HOME/trading-desk/desk.md` | scripts/hermes-bootstrap.sh:8 |
| A18 | 208 | yes | `/workspace/trading-desk/risk-limits.md` | `$HOME/trading-desk/risk-limits.md` | scripts/hermes-bootstrap.sh:8 |
| A19 | 209 | yes | "`GROKBOT_*` ... Vendored engine only (`vendor/grokbot-pumpfun`, e.g. `GROKBOT_GROK_API_KEY`)" | "None read by this tree; the retired vendor engine used them (see docs/VENDOR_PIN.md)" | grep GROKBOT_ in src, tests, ci: settings.py:297 comment only; no GROKBOT_GROK_API_KEY anywhere in the tree |
| A20 | 244 | yes | "Whether a given host actually creates eight persistent Bots ..." | "Whether a given host actually creates ten seats ..." (D-04(d)) | AGENTS.md:26; agents/*.md (10 role files) |
| A21 | 83 | no | module map "`pumpgrok scout pipeline` --> vendor JSONL via the export cursor" | "--> not implemented (exit 5); no vendor import" | exit 5 run as in A7 |
| A22 | 100 (insert after) | no | (no signal or journal rows) | added rows for `signal.md` and `journal.md` (role, writes_to_exchange false, skills copied from frontmatter) | agents/signal.md and agents/journal.md frontmatter; 10 seat files |
| A23 | 102 | no | "EXIT and SHILL may be DMs" | "EXIT, SHILL, SIGNAL and JOURNAL are DM seats (`seat: DM`)" | `grep -l '^seat: DM' agents/*.md` -> exit, journal, shill, signal |
| A24 | 128 | no | tool row: `pumpgrok scout pipeline --candidates` reads trades.jsonl via ledger/export.py | "Not implemented: exits 5 with `status: not-yet-implemented`" | exit 5 run as in A7 |
| A25 | 178 | no | "No database, migrations, or cache layer." | adds "The paper ledger is one SQLite file (var/ledger.sqlite, src/pumpgrok/ledger/store.py); desk operational files live under var/desk/" | ledger/store.py imports sqlite3; ledger/paths.py:22-23; no migrations directory |
| A26 | 204 | no | `PUMPGROK_RPC__ENDPOINTS` -> `authority_check.py`, `priority_fee.py`, `holder_check.py` | `tools/onchain/authorities.py`, `tools/onchain/priority_fee.py`, `tools/onchain/top_holders.py` (RpcSettings in config/settings.py) | `find` for authority_check.py and holder_check.py: none; the three tools/onchain/*.py files exist |
| A27 | 206 | no | "Quote params: `jupiter_quote.py` flags" | "Quote params: `src/pumpgrok/tools/market/jupiter.py` (`QUOTE_URL`)" | jupiter_quote.py missing; tools/market/jupiter.py:27 |
| A28 | 221 | no | "Observability ... No metrics/tracing code." | adds `run --serve` read-only /healthz and /metrics on 127.0.0.1; "No tracing code." | src/pumpgrok/doctor.py:5, :35; src/pumpgrok/cli/parsing.py:58-60 |
| A29 | 225 | no | "`python3 -m unittest tests.test_tools_cli` covers tool CLI contracts" | "`uv run pytest tests/test_tools_cli.py` covers tool CLI contracts" | `python3 -m unittest tests.test_tools_cli` -> ImportError (no pumpgrok on bare python3); `uv run python -m unittest tests.test_tools_cli` -> 0 tests run |
| A30 | 242 | no | plugin manifests "carry AGPL-3.0 and swcstudiospace URLs" (all of them) | scoped to plugin.json and pyproject.toml; marketplace manifests and SETUP.md named as still carrying the placeholder organisation name allowlisted by check.sh | plugin.json:8, :11; pyproject.toml:24-25; marketplace files; scripts/check.sh:121-127 |

Rows A1 to A20 are the 20 pattern hits at HEAD. Rows A21 to A30 are additional accuracy corrections found while checking claims against the code.

### 3b. SETUP.md

| # | Line | Pattern | Old text (abbrev.) | New text (abbrev.) | Evidence path |
|---|------|---------|--------------------|--------------------|---------------|
| S1 | 48 | yes | `mkdir -p /workspace/trading-desk/{proposals,...}` | `mkdir -p ~/trading-desk/{proposals,...}` (same eight subfolders) | scripts/hermes-bootstrap.sh:217 uses the same list |
| S2 | 53 | yes | `touch /workspace/trading-desk/desk.md` | `touch ~/trading-desk/desk.md` | scripts/hermes-bootstrap.sh:8 |
| S3 | 54 | yes | `touch /workspace/trading-desk/risk-limits.md` | `touch ~/trading-desk/risk-limits.md` | scripts/hermes-bootstrap.sh:8 |
| S4 | 145 | yes | "The screening engine is not vendored here: `vendor/` is absent, so there is no `vendor/grokbot-pumpfun/` to read, install, or configure." | "...`vendor/grokbot-pumpfun/` is absent from this checkout (formerly vendored, see docs/VENDOR_PIN.md), so there is nothing to read, install, or configure there." Command claim unchanged | ls vendor (absent); docs/VENDOR_PIN.md:3-5; `pumpgrok scout pipeline --candidates` exit 5 |
| S5 | 166 | yes | "Create or update `/workspace/trading-desk/desk.md` with:" | "Create or update `~/trading-desk/desk.md` with:" | scripts/hermes-bootstrap.sh:8 |
| S6 | 182 | yes | "Also create a starter `/workspace/trading-desk/risk-limits.md`" | "Also create a starter `~/trading-desk/risk-limits.md`" | scripts/hermes-bootstrap.sh:8 |
| S7 | 18 | no | `ls /workspace/pumpgrok/... /workspace/pumpgrok/tools ...` | `/workspace/pumpgrok/src/pumpgrok/tools` | the repo root has no `tools/` directory; src/pumpgrok/tools exists |
| S8 | 25 | no | "agents/ (8 role files + README)" | "agents/ (10 role files + README)" | agents/: chief, exit, journal, risk, rug, scout, shill, signal, sniper, whale |
| S9 | 47 | no | (none) | new sentence: the desk folder is the operator's host folder outside the repository; scripts/hermes-bootstrap.sh uses the same default; PUMPGROK_DESK overrides it (D-04(c) wording, with the evidence) | scripts/hermes-bootstrap.sh:8 |
| S10 | 174 | no | "Bots created: CHIEF, SCOUT, RISK, WHALE, SNIPER, RUG, EXIT, SHILL" | adds SIGNAL, JOURNAL | ten agent files |
| S11 | 212 | no | "Bots: CHIEF, ... SHILL" (receipt) | adds SIGNAL, JOURNAL | ten agent files |
| S12 | 4, 84 | no | "ten seats" (already at HEAD) | no change; D-05 lines 4 and 5 were already "ten seats" | SETUP.md:4 and :84 at HEAD |

Rows S1 to S6 are the 6 pattern hits at HEAD. The check of every SETUP command is in section 5.

### 3c. README.md

| # | Line | Pattern | Old text (abbrev.) | New text (abbrev.) | Evidence path |
|---|------|---------|--------------------|--------------------|---------------|
| R1 | 43 | yes | `uv run pumpgrok tools market.price --help` | unchanged (resolved) | exit 0 on run |
| R2 | 65 | yes | "Formerly the vendored `vendor/grokbot-pumpfun/` tree, retired in Phase 4" | unchanged (past tense, resolved) | src/pumpgrok/engine/ exists; docs/VENDOR_PIN.md |
| R3 | 12 | no (D-06) | "a vendored dry-run screening engine (`skills/grokbot-pipeline`)" | "the screening-engine procedure (`skills/grokbot-pipeline`; the vendored tree is retired, see docs/VENDOR_PIN.md)" | docs/VENDOR_PIN.md:3-5 |
| R4 | 14 | no | "...paper fills, holder concentration, and pipeline JSONL evidence" | "...holder concentration, and paper-trade commands (which refuse until the curve reader is verified); `scout pipeline` is registered but not implemented" | scout pipeline exit 5; `paper buy` refusal path (section 5) |
| R5 | 18 | no | "**paper** logs simulated fills via `pumpgrok paper`; the CLI refuses ... so no paper fill runs from the CLI" | "**paper** is the simulated-fill level: `pumpgrok run --mode paper` drives the paper adapter on recorded data; `pumpgrok paper buy` and `paper sell` refuse with code `unavailable` until the curve reader is verified" | src/pumpgrok/cli/verbs_state.py:_run (line 173 prints "trades filled="); cli/codes.py:37-40 |

Rows R1 and R2 are the 2 pattern hits at HEAD. D-06 residuals `--rpc`, "eight" wording, and `/workspace/trading-desk` were already absent from README at HEAD (grep: 0 hits); R3 is the vendor row in present tense.

### 3d. Row count

- Pattern-matched rows at HEAD: 28 (ARCHITECTURE 20, SETUP 6, README 2). Every one has a row above.
- Additional rows: 10 in ARCHITECTURE (A21 to A30), 5 in SETUP (S7 to S11), 3 in README (R3 to R5).
- Total rows: 47 (ARCHITECTURE 30, SETUP 12 including the S12 no-change record, README 5). Counted with `grep -c -E '^\| [ASR][0-9]+ \|'`.

## 4. Grep table after the edits (D-09)

Command: `grep -n -E 'eight|Eight|vendor/grokbot-pumpfun|trading-desk|ticket_helper|paper_sim|--rpc|no server, queue|started as a service|market.price' ARCHITECTURE.md SETUP.md README.md`

| File | HEAD hits | Final hits | Unresolved |
|------|-----------|------------|------------|
| ARCHITECTURE.md | 20 | 10 | 0 |
| SETUP.md | 6 | 7 | 0 |
| README.md | 2 | 2 | 0 |

Final hits and their status:
- ARCHITECTURE.md 15, 87: `vendor/grokbot-pumpfun/` in "absent from this checkout; formerly vendored" wording (D-04(b)). Resolved.
- ARCHITECTURE.md 27, 124: `market.price` tool id and curve price read. Resolved (A2, A8).
- ARCHITECTURE.md 40, 185, 198, 207, 209, 210: `$HOME/trading-desk` (operator host folder). Resolved with the cited evidence scripts/hermes-bootstrap.sh:8. This is not the `/workspace/trading-desk` path D-04(c) names; see deviation 2.
- ARCHITECTURE.md 207 (PUMPGROK_DESK row): same path, evidence cited.
- SETUP.md 47, 50, 55, 56, 168, 184: `$HOME/trading-desk` commands and the operator-folder sentence. Resolved (S1 to S6, S9).
- SETUP.md 147: vendor absent wording (S4). Resolved.
- README.md 43, 65: resolved (R1, R2).

Zero `/workspace/trading-desk` lines remain in ARCHITECTURE.md, SETUP.md, or README.md (`grep -c '/workspace/trading-desk'` = 0 for all three). Zero hits for `eight`, `Eight`, `--rpc`, `ticket_helper`, `paper_sim`, `no server, queue`, `started as a service` in the three documents.

## 5. Command checks (D-05, D-06)

Commands run from the worktree (`uv run pumpgrok ...`), all exit 0 unless stated:

| Command | Result | Used in |
|---------|--------|---------|
| `uv run pumpgrok --help` | exit 0; verbs include run, doctor, verify, report, backtest, scout, risk, chief, rug, journal, ticket, state, killswitch, paper, live, replay, tools (hidden) | README, ARCHITECTURE |
| `uv run pumpgrok ticket --help` | exit 0; next, create, list | ARCHITECTURE |
| `uv run pumpgrok ticket next --help` | exit 0 | SETUP section 7 |
| `uv run pumpgrok ticket create --help`, `ticket list --help` | exit 0 | README |
| `uv run pumpgrok run --help` | exit 0; --mode, --once, --replay DIR, --serve, --record, --duration | ARCHITECTURE, README |
| `uv run pumpgrok journal --help`, `paper --help`, `verify --help`, `replay --help`, `report --help`, `doctor --help`, `scout --help` | exit 0 | ARCHITECTURE |
| `uv run pumpgrok scout pipeline --help`, `scout pipeline --candidates --help` | exit 0 | README |
| `uv run pumpgrok scout pipeline --candidates` | exit 5; `{"ok": false, "status": "not-yet-implemented", "verb": "scout pipeline"}` | SETUP section 8 (matches) |
| `uv run pumpgrok tools onchain.authorities --help`, `onchain.priority_fee --help`, `market.price --help`, `market.holders_snapshot --help` | exit 0 (JSON schema, per ARCHITECTURE) | SETUP section 7, README |
| `uv run pumpgrok paper buy --help`, `paper sell --help` | exit 0 | README |
| `uv run pumpgrok paper buy ... --seat sniper` (and `exit`, `chief`) | refused before the trade branch: "refused: seat 'sniper' is a forbidden owner for `paper buy`"; `chief` -> permission_denied (not_in_roster); no seat reached the `unavailable` branch | README (see section 7) |
| `uv run pumpgrok verify --fixture smoke-10m` | exit 0; `events.hash=b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`; `verify=CONSISTENT seq=2 events=41` | D-09 |

Makefile targets: SETUP.md names no make target (`grep -n make SETUP.md` -> none). README and ARCHITECTURE name none. `make lint` ran as D-09 (exit 0).

SETUP.md checks, one per command block:
- Section 1 `git clone ...your-org...` and archive fallback: not run (network); clone URL kept with the placeholder that check.sh allowlists for SETUP.md.
- Section 1 `ls /workspace/pumpgrok/agents /workspace/pumpgrok/skills /workspace/pumpgrok/src/pumpgrok/tools /workspace/pumpgrok/rules`: after S7 each path exists in the worktree (the old `tools` path did not).
- Section 3 mkdir and touch: paths now match scripts/hermes-bootstrap.sh; not executed (would write to $HOME).
- Section 7 `cd /workspace/pumpgrok`, `uv sync`, `uv run pumpgrok ticket next --help`, `uv run pumpgrok tools onchain.authorities --help`: help forms verified; `uv sync` not run here (make lint ran `uv sync --frozen`).
- Section 8: vendor absent and `scout pipeline --candidates` exit 5: verified.
- Section 11 optional checks: `pumpgrok ticket next` (no --help) NOT executed, see deviation 6; `pumpgrok tools onchain.priority_fee --help` verified.

README.md checks: D-06 residuals `--rpc` (0 hits), "eight" (0 hits), `/workspace/trading-desk` (0 hits), vendor row in present tense (fixed R3).

## 6. Replay SKILL (D-07)

`skills/replay-and-backtest/SKILL.md` was not changed. The overclaim is already corrected: the description (line 3) and the S2 step (line 33) say replay drives the supervisor, the rule, and the paper adapter with a fixture clock, and that the `run_replay` checkpoint writes its verdict row first and does not run the paper adapter. `grep -n -i -E 'same code path|identical path' skills/replay-and-backtest/SKILL.md` -> no hits.

## 7. Verification results (D-09)

| Check | Command | Exit | Counts / output |
|-------|---------|------|-----------------|
| Red test (before doc edits) | `uv run python -m pytest tests/docs/test_doc_consistency.py -q --junitxml=/tmp/phase21-red.xml` | 1 | tests=5 failures=2 errors=0 |
| Docs tests (final) | `uv run python -m pytest tests/docs -q --junitxml=/tmp/phase21-docs.xml` | 0 | tests=44 failures=0 errors=0 skipped=0 |
| Doc commands | `./scripts/verify_doc_commands.sh` | 0 | pass=2 skip=9 fail=0 |
| Repo check | `./scripts/check.sh` | 0 | "35 skills, 10 agents, 319 markdown files checked"; "repository structure looks healthy" (first run exited 1 on a `your-org` string in ARCHITECTURE.md, fixed in section 3a row A30) |
| Lint | `make lint` | 0 | ruff check "All checks passed!"; ruff format --check "817 files already formatted" |
| Replay verify | `uv run pumpgrok verify --fixture smoke-10m` | 0 | `events.hash=b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`, `verify=CONSISTENT seq=2 events=41`; matches the required hash |

Full `make test` and the full suite were NOT run (assignment instruction; orchestrator runs them).

## 8. Deviations

1. Mis-targeted edit. My first test edit used a relative path and landed in `/root/src/repos/pumpgrok/tests/docs/test_doc_consistency.py` (the other checkout). I verified its diff contained only my edit (no staged changes), reverted that one file with `git checkout -- tests/docs/test_doc_consistency.py` in that checkout, and re-applied the edit in the worktree with an absolute path. The other checkout's pre-existing changes (`tests/upgrade/test_scheduled_promotion.py` modified, `.claude/bot-00-chief/phase-6-integrity` untracked) were not touched. Nothing from that checkout was committed or staged.
2. D-04(c) condition not met as written. No repository skill or script uses `/workspace/trading-desk`: `skills/portfolio-ledger/SKILL.md` and `skills/desk-post-trade-review/SKILL.md` do not mention it, and the hermes scripts use `${HOME}/trading-desk` (`PUMPGROK_DESK` overrides it). I replaced the path with `$HOME/trading-desk`, cited scripts/hermes-bootstrap.sh:8 and :217, and kept the "operator's host folder outside the repository" statement. The acceptance wording "except /workspace/trading-desk lines" therefore applies to zero lines; the remaining `trading-desk` hits are the `$HOME` form with evidence.
3. D-05 lines 4 and 5 were already "ten seats" at HEAD. The real residuals were "8 role files" (SETUP:25) and the Bot lists at SETUP:174 and :212, which omitted SIGNAL and JOURNAL. Those were fixed.
4. Scope beyond the grep pattern. D-04 covers pattern lines. I also corrected statements that the code contradicts (A21 to A30, S7 to S11, R4, R5) because DOC-03 requires the named documents to match the code. Each has an evidence path in the tables above.
5. Marketplace description keeps "35 skills" in the grok manifest; the count is 35, so no change was needed.
6. Not changed, flagged: SETUP.md:201 and README.md:46 suggest `pumpgrok ticket next` as a read-only check. The verb allocates and persists a ticket row in var/ledger.sqlite (ledger/tickets.py), which conflicts with "Setup is read-only". I did not run it. Left for a follow-up because it is a behavior question, not a wording fix.
7. Not changed, out of D-01 scope (found during the grep; recorded as tech debt):
   - agents/README.md:3 "Eight specialist Bots", :16 "All eight roles".
   - skills/desk-operating-model/SKILL.md:3 and :18 "eight roles".
   - scripts/hermes-bootstrap.sh (header and ROLES, eight Hermes profiles) and scripts/README.md:8 "eight isolated Hermes profiles".
   - skills/holder-and-flow-analysis/SKILL.md:27 `/workspace/pumpgrok/tools/holder_check.py` (no such file).
   - docs/VENDOR_PIN.md:24-25 "Copy config.example.yaml to config.yaml" for a tree that is absent (VENDOR_PIN was verify-only; the pin and retirement test passes).
   - docs/ROSTER.md and docs/FOUNDATION_STACK.md: D-10, unchanged.
8. The `your-org` placeholder remains in SETUP.md:16-17 and in both marketplace manifests, as check.sh allowlists. The real organisation name is still unknown (docs/MIGRATION_MAP.md section 8). The root plugin.json and pyproject.toml carry swcstudiospace/PumpGrok, which ARCHITECTURE now states precisely.
9. Console output of pytest in this environment is wrapped by a filter that printed "No tests collected" and "Pytest: 4 passed" for the wrong counts. Junit XML and exit codes are the evidence recorded above, as the assignment said.
10. Runtime artifacts: CLI probes and test runs wrote under var/ (gitignored: `git check-ignore -v var` -> .gitignore:17). Nothing under var/ is tracked.
11. Worktree had pre-existing uncommitted changes before I started (`.planning/ROADMAP.md`, `.planning/phases/07-*/07-VERIFICATION.md`, `08-*`, `10-*`, untracked `.planning/phases/21-*/` context, `.planning/pre-run-snapshot/`, `.planning/state.json`). They were not touched and are not in any of my commits. Only the summary file (this commit) is added, by explicit path.

## 9. What was not verified

- Runtime of `pumpgrok paper buy|sell` reaching the `unavailable` branch: no seat I could resolve reached it. Sniper and exit are forbidden owners for paper buy; chief is not in the roster. The branch is verified in code (cli/verbs_state.py `_paper`, cli/codes.py `_TRADE_UNAVAILABLE`), not at runtime.
- SETUP.md section 1 clone, archive fallback, `uv sync`, section 3 mkdir and touch (writes to $HOME), section 11 chat smoke tests: not executed.
- ARCHITECTURE claims left as-is and not checked: "HTTP/RPC exceptions become {"ok": false} and the process exits 1", "Tools do not read environment variables" (settings classes read env via pydantic; tools not checked individually), and the "no os.environ / .env readers" statement.
- `skills/grokbot-pipeline/SKILL.md` content (it is outside D-01 and may still describe the vendor tree).
- The `make test` suite and the full pytest run were not run, per the assignment.
- Hermes scripts and the cron/isolation checks were not executed.
- docs/VENDOR_PIN.md was not edited (verify only); its pin and retirement wording pass the test, and the residual lines are listed in deviation 7.
