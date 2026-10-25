# Phase 7 CONTEXT: Documentation upgrade

Branch: `bot-00-chief/phase-6-integrity`. Replay hash to preserve: `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`
(smoke-10m events.hash, Phase 6 before=after). Phase 7 MUST NOT change replay output.

## Hard constraints (from brief, non-negotiable)

1. No task runs the full test suite (`make test`, `pytest -q tests/`, `./scripts/check.sh` whole-repo). Targeted `pytest tests/docs/...` only. The orchestrator owns the gates.
2. Do NOT edit `rules/`, `agents/`, `prompts/` or `src/` — no Phase 7 success criterion names a file there, so they are read-only sources.
3. Every plan touches at most five files (CHANGELOG.md counts).
4. Every success criterion gets a named task with a runnable acceptance command (coverage table below).

## Verified evidence (grep-confirmed 2026-10-25 on this branch)

### Counts and versions
- Seats: ten. `agents/*.md` holds chief, exit, journal, risk, rug, scout, shill, signal, sniper, whale (10 seat files + README). `AGENTS.md` "The ten seats" table; `src/pumpgrok/supervisor/scheduler.py:1` "Ten-seat supervised scheduler".
- Skills: 35. `ls -d skills/*/` counts 35 directories.
- Package version: `0.1.0` (`pyproject.toml`: `version = "0.1.0"`).
- Plugin pack version: `1.0.0` in all four manifests (`plugin.json`, `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `.grok-plugin/plugin.json`). Criterion 6 requires plugin statements to match `pyproject.toml`, so manifests move to `0.1.0`.
- Brief said README claims "twenty-three skills": NOT FOUND by grep. README:5,12 already say "35 skills" (correct). Do NOT invent a twenty-three correction; the real README count errors are "eight-role" / "Eight specialist roles" (README:5,11,60, and "eight Bots" README:30).

### Radio / serve / price / replay facts
- No `--rpc` flag: `grep -rn '"--rpc"' src/ scripts/` is empty. RPC endpoints come from `PUMPGROK_RPC__ENDPOINTS` (env_prefix `PUMPGROK_` + nested delimiter `__`, `RpcSettings.endpoints` in `src/pumpgrok/config/settings.py:76-93`, default `https://api.mainnet-beta.solana.com`).
- Serve mode: `run --serve` needs `--replay <dir>` WITHOUT `--once` (`src/pumpgrok/cli.py:583-590`); compose service runs `["run", "--mode", "paper", "--serve", "--replay", "tests/fixtures/replay/smoke"]` (`docker-compose.yml`). One-shot is `run --mode paper --once --replay <dir>`.
- `market.price`: bonding-curve spot via `getAccountInfo` + ASSUMED layout, source always `curve`, no Jupiter path in that module (`src/pumpgrok/tools/market/price.py:1-8`, backend `curve_layout.py via solana_rpc getAccountInfo`). `exec.quote` routes through the ExecutionAdapter (`src/pumpgrok/tools/exec/quote.py:1,54`). Jupiter Swap V2 order URL is the informational-only quote in `src/pumpgrok/tools/market/jupiter.py` (`QUOTE_URL`, never `/execute`).
- Replay paths differ: `run --once --replay` builds a `PaperAdapter` (`scheduler.py:896`, `run_once_replay` at :1117). Separately, `run_replay` "writes the checkpoint verdict row first" (`scheduler.py:1131`). SKILL.md S2 "Run the identical path ... same code path as paper trading" and description "same code path as live paper" overclaim: correct to "replay drives supervisor, rule and paper adapter with a fixture clock; the checkpoint path writes its verdict row first and does not run the paper adapter". SETUP.md carries NO identical-fill language (grep `identical|same code path|fill path` empty) — do not touch SETUP for that; SETUP corrections are eight-Bots→ten-seats and any stale command verified by grep.

### Contradiction locations (README / ARCHITECTURE / SETUP / SKILL)
- README: eight-role (:5), `Version 1.0.0` (:7) vs package 0.1.0, eight roles (:11), `--rpc` (:24), `eight Bots` (:30), `agents/` eight (:60), `vendor/grokbot-pumpfun/` row (:65), `/workspace/trading-desk/` (:52).
- ARCHITECTURE: eight-role (:7), `vendor/grokbot-pumpfun/` layer row (:15), "no server, queue, or daemon" (:18) — code now has `serve_replay`/`_serve_replay_loop` (cli.py:600) and compose serve service; `--rpc` row (:28, :203), Jupiter `market.price` row (:26, :121 — price is the curve account, Jupiter is exec-side), `/workspace/trading-desk` (:39, :182, :195, :206-207), "Nothing in this repo is started as a service" (Containers section).
- ARCHITECTURE "There is no PumpGrok server" correction: fail-closed wording — serve mode is `run --serve` replay loop with /healthz + /metrics, paper-only, no live path.
- `docs/VENDOR_PIN.md`: pin `409e74c905faa0e9de42e918efe2c604f206856e` recorded; criterion 6 test asserts it matches the vendored snapshot.

## Decisions

- D-01: CLAUDE.md is new root map with EXACTLY the nine criterion-2 `##` sections (Purpose, Stack, Layout, Commands, Architecture, Conventions, GSD artifact, Safety, Known gaps — grep matches `^## (Purpose|Stack|Layout|Commands|Architecture|Conventions|GSD artifact|Safety|Known gaps)`), every bullet carrying a backticked repo path (criterion-3 proxy). Prose statements cite files too (human review).
- D-02: AGENTS.md trim removes the generated GSD research dump (`## Technology Stack` … stack/install/alternatives sections sourced from `research/STACK.md`, ~lines 101-260+) and any placeholder blocks, keeps the rules index + seats + receipts + checks, and LINKS `CLAUDE.md` instead of duplicating it. Must end shorter than `origin/main` (423 lines).
- D-03: `scripts/verify_doc_commands.sh` parses fenced `bash` blocks in the Commands sections of AGENTS.md and CLAUDE.md only, runs each, compares exit code to the documented expectation (convention: trailing comment `# exits N`, default 0). Only commands the repo can run offline (pumpgrok verbs, make targets used in docs); no network, no `curl`.
- D-04: Consistency tests live in `tests/docs/`: `test_doc_consistency.py` (plugin versions == pyproject version; VENDOR_PIN pin == vendored snapshot marker; every `pumpgrok ...` command named in README/ARCHITECTURE/SETUP/SKILL exists in CLI help; banned contradiction strings absent) and `test_historical_banners.py` (fixed file set, each starting with the exact banner line `Historical design record`).
- D-05: Banner text is exactly `Historical design record` as the first line-matter of each listed file (criterion 7 greps "begins with the banner"). Fixed set: `docs/DISCOVERY.md`, `docs/MIGRATION_MAP.md`, `docs/upgrade-plan-desk-v2.md`, `docs/design/interfaces.md`, `docs/design/paper-engine.md`.
- D-06: CHANGELOG.md gets one entry per DOC id (DOC-01..DOC-04, satisfying criterion 8 `grep -cE 'DOC-0[1-4]' >= 4`) plus `Phase 7: smoke-10m events.hash after: <hash>` with the hash byte-identical to Phase 6 (criterion 9). All CHANGELOG work is owned by plan 07-06 (keeps wave-1 plans file-disjoint).
- D-07: Where the brief and grep disagree (twenty-three skills; SETUP identical-fill), grep wins — noted above, no phantom corrections.

## Coverage: criterion -> plan -> task

| # | Criterion | Plan | Task |
|---|-----------|------|------|
| 1 | lint/typecheck/test/check.sh + replay smoke exit 0 | — | Orchestrator gates only (no task runs the suite per constraints) |
| 2 | CLAUDE.md ≥9 named `##` sections | 07-01 | "Write root CLAUDE.md" — `test "$(grep -cE '^## (Purpose\|Stack\|Layout\|Commands\|Architecture\|Conventions\|GSD artifact\|Safety\|Known gaps)' CLAUDE.md)" -ge 9` |
| 3 | every CLAUDE.md bullet cites backticked path | 07-01 | same task — `! grep -nE '^\s*[-*] ' CLAUDE.md \| grep -v '`'` |
| 4 | AGENTS.md shorter, links CLAUDE.md, no placeholder | 07-02 | "Trim AGENTS.md" — `test "$(wc -l < AGENTS.md)" -lt "$(git show origin/main:AGENTS.md \| wc -l)"`, `grep -q CLAUDE.md`, `! grep -niE placeholder` |
| 5 | verify_doc_commands.sh green | 07-02 | "Create verify script" — `./scripts/verify_doc_commands.sh` exits 0 |
| 6 | tests/docs/ green (versions, VENDOR_PIN, CLI help, contradictions) | 07-03 (doc fixes), 07-04 (manifest+VENDOR_PIN), 07-05 ("Write consistency test" — `uv run pytest -q tests/docs/test_doc_consistency.py`) | criterion-6 acceptance lives in 07-05 task |
| 7 | historical banners test green | 07-05 ("Write banner test + banner root docs"), 07-06 ("Banner design docs") — `uv run pytest -q tests/docs/test_historical_banners.py` | acceptance in both; full-set green in 07-06 |
| 8 | CHANGELOG carries DOC-01..04 (≥4) | 07-06 | "CHANGELOG DOC entries + Phase 7 hash" — `test "$(grep -cE 'DOC-0[1-4]' CHANGELOG.md)" -ge 4` |
| 9 | replay hash unchanged + Phase 7 hash line | 07-06 | same task — `a=$(...) … grep -qF "Phase 7: smoke-10m events.hash after: $a"` plus equality with Phase 6 value |

## Plan list

- 07-01 (wave 1): CLAUDE.md — DOC-01, criteria 2+3.
- 07-02 (wave 2, dep 07-01): AGENTS.md trim + verify script — DOC-02, criteria 4+5.
- 07-03 (wave 1): README/ARCHITECTURE/SETUP/SKILL corrections — DOC-03 (criteria 6, 8).
- 07-04 (wave 1): four plugin manifests to 0.1.0 + VENDOR_PIN verify — DOC-03 (criterion 6).
- 07-05 (wave 3, dep 07-01..07-04): tests/docs consistency + banner tests, banners on 3 root docs — DOC-03/DOC-04 (criteria 6+7).
- 07-06 (wave 4, dep 07-05): design-doc banners + CHANGELOG — DOC-04/DOC-03 (criteria 7+8+9).
