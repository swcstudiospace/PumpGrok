# MIGRATION_MAP - old-to-new module mapping and keep/move/replace decisions

Tracker: SPE-17996 https://linear.app/swcstudio/issue/SPE-17996/n2-old-to-new-module-mapping-and-keepmovereplace-decisions | Notion https://app.notion.com/p/3ffbc1a0c7ae813290dfd11526829596?pvs=204

Scope: every file tracked at `feat/grokbot-desk-merge` HEAD `8f7ae72` (command: `git log --oneline -1` ->
`8f7ae72 chore(tools): fail-closed exit codes, Jupiter lite-api URL, hermes script modes, CLI contract tests`).
Target layout and names are the orchestrator decisions D1-D9 (programming-desk shape, Python 3.12, paper-only).
This document maps; it does not move anything. Dependency drift detail lives in `docs/DISCOVERY.md` section 5
and is only referenced here (section 6).

Tracked-file census: `git ls-files | wc -l` -> `129`. Section 1 lists exactly 129 rows (78 non-vendor + 51 vendor).

## 0. Decision rules applied

| Decision | Rule | Notes |
|---|---|---|
| keep-in-place | Path unchanged. Content may be edited (frontmatter, placeholders) but logic is preserved. | Used for instruction-pack files that already have the target name. |
| keep-and-move | Path changes, logic preserved verbatim. Allowed ONLY when a characterization test in `tests/characterization/test_<module>.py` passes against the moved module. | Vendor modules whose test file ports 1:1 (see section 3). Translating Russian comments and log strings to English does NOT change the decision; it is a string-only edit covered by the ported tests (tests that assert on Russian message text are listed in section 3.3 and are adapted, not 1:1). |
| rewrite | Logic changes because the file uses a deprecated SDK (`requests` -> `httpx`), a hardcoded venue/RPC/key, duplicated logic (`rpc_call` x3, `desk_root` x2), a replaced persistence model (markdown file bus / flat JSON -> ledger), or because operator-facing strings asserted by tests are non-English. | A rewrite still gets a characterization test when the external contract (JSON stdout, JSONL record shape) must be preserved; column 7 says which. |
| generate | File becomes a build output of `scripts/assemble-prompts.sh` or `scripts/generate-templates.py`. | `agents/*.md`, `prompts-assembled/`. |
| delete | Removed. Allowed only with zero inbound references. Method: `rg -l -F "<string>" . --glob '!*.pyc'` from repo root; the command and result are quoted in the evidence column. | Tracked `*.pyc`, `issues/tissue.json`, vendor packaging files at retirement. |

Live-write column: `no` = file never signs/sends and never will; `quarantine` = file currently contains live-path
code or config (even a stub) and is handled in section 2.

Seat ids used below are D3: `bot-00-chief bot-01-scout bot-02-risk bot-03-whale bot-04-sniper bot-05-rug bot-06-exit bot-07-shill bot-08-signal bot-09-journal`.

## 1. Per-file mapping (129 rows)

### 1.1 Root, plugin manifests, top-level docs (12 rows)

| # | Old path | New path | Decision | Evidence | Live-write? | Characterization test |
|---|---|---|---|---|---|---|
| 1 | `.claude-plugin/marketplace.json` | same | keep-in-place | placeholder `your-org` repo/homepage URLs (scout-pumpgrok-pack: manifest table; confirmed `rg -n your-org .claude-plugin/marketplace.json`) | no | n/a |
| 2 | `.claude-plugin/plugin.json` | same | keep-in-place | `"license": "MIT"` contradicts `LICENSE:1-4` (AGPL-3.0); lacks `skills/agents/rules` paths present in `.grok-plugin/plugin.json` | no | n/a |
| 3 | `.cursor-plugin/plugin.json` | same | keep-in-place | `"license": "MIT"` -> AGPL-3.0 | no | n/a |
| 4 | `.devcontainer.json` | same | keep-in-place | content is exactly `{"image":"mcr.microsoft.com/devcontainers/python:3"}` (`cat .devcontainer.json`); add `postCreateCommand: uv sync` only | no | n/a |
| 5 | `.grok-plugin/marketplace.json` | same | keep-in-place | `your-org` x2 | no | n/a |
| 6 | `.grok-plugin/plugin.json` | same | keep-in-place | `"license": "MIT"`; has `skills: ./skills/`, `agents: ./agents/`, `rules: ./rules/` (model for the other manifests) | no | n/a |
| 7 | `ARCHITECTURE.md` | `ARCHITECTURE.md` | rewrite | describes file bus + `tools/README.md` + vendor pin `409e74c` (`rg -l -F 409e74c .` -> ARCHITECTURE.md README.md SETUP.md skills/grokbot-pipeline/SKILL.md vendor/grokbot-pumpfun/PUMPGROK.md); defines the `micro-live` engagement level (`ARCHITECTURE.md:173`) which R16 retires (section 2.5); all three change | no | n/a |
| 8 | `LICENSE` | same | keep-in-place | AGPL-3.0, Spectrum Web Co LLC 2026 (`LICENSE:1-4`) | no | n/a |
| 9 | `README.md` | `README.md` | rewrite | references `banner.jpg`, `tools/README.md`, vendor pin (`rg -l -F tools/README .` -> ARCHITECTURE.md README.md); `micro-live` prose at `README.md:18` retired (R16, section 2.5) | no | n/a |
| 10 | `SETUP.md` | `docs/runbooks/setup.md` (operator runbook) + install summary in `README.md` | rewrite | clone URL `https://github.com/your-org/pumpgrok.git`, `mkdir -p /workspace/trading-desk/...`, `pip install requests` (scout-pumpgrok-pack: SETUP.md 12 sections); all replaced by `uv sync` + `pumpgrok doctor`; `Engagement: research \| paper \| micro-live` (`SETUP.md:176`) and "move engagement to paper or micro-live" (`:229`) retired (R16, section 2.5) | no | n/a |
| 11 | `banner.jpg` | same | keep-in-place | referenced by README.md and ARCHITECTURE.md (`rg -l -F banner.jpg .`) | no | n/a |
| 12 | `plugin.json` | same | keep-in-place | `"license": "MIT"`, `your-org` in author.url + repository; `$schema` agent-plugins.org 1.0.0 | no | n/a |


### 1.2 Agents (9 rows)

`agents/<seat>.md` is today's host-facing file (frontmatter `name,title,description,seat,skills[],writes_to_exchange`;
e.g. `agents/chief.md:1-12`). Per D2 the SOURCE becomes `prompts/bot-0N-<seat>.xml` and `agents/<seat>.md` is
regenerated by `scripts/generate-templates.py` with the same frontmatter contract. `scripts/hermes-bootstrap.sh:159`
reads `${ROOT}/agents/${role}.md` as SOUL.md, so the generated file keeps the old basename.

| # | Old path | New path | Decision | Evidence | Live-write? | Characterization test |
|---|---|---|---|---|---|---|
| 13 | `agents/README.md` | `agents/README.md` (generated index) | generate | 8-row table that must grow to 10 seats (D3) | no | n/a |
| 14 | `agents/chief.md` | source `prompts/bot-00-chief.xml`; output `agents/chief.md` | generate | `agents/chief.md` frontmatter `name: CHIEF`, `writes_to_exchange: false` | no | n/a |
| 15 | `agents/scout.md` | source `prompts/bot-01-scout.xml`; output `agents/scout.md` | generate | `name: SCOUT`, skills x5 | no | n/a |
| 16 | `agents/risk.md` | source `prompts/bot-02-risk.xml`; output `agents/risk.md` | generate | `name: RISK`, `writes_to_exchange: false` | no | n/a |
| 17 | `agents/whale.md` | source `prompts/bot-03-whale.xml`; output `agents/whale.md` | generate | `name: WHALE` | no | n/a |
| 18 | `agents/sniper.md` | source `prompts/bot-04-sniper.xml`; output `agents/sniper.md` | generate | `writes_to_exchange: true` (paper-write only after migration, D3) | quarantine (paper-write seat, section 2.3) | n/a |
| 19 | `agents/rug.md` | source `prompts/bot-05-rug.xml`; output `agents/rug.md` | generate | `name: RUG` | no | n/a |
| 20 | `agents/exit.md` | source `prompts/bot-06-exit.xml`; output `agents/exit.md` | generate | `writes_to_exchange: true`; "unless the human has explicitly enabled emergency auto-exit in writing" (`agents/exit.md:41`) and "pre-authorised rules" (`:48`) are replaced by the R17 exit-automation rule (section 2.5) | quarantine (paper-write seat, section 2.3) | n/a |
| 21 | `agents/shill.md` | source `prompts/bot-07-shill.xml`; output `agents/shill.md` | generate | `name: SHILL`; D7 detection only | no | n/a |

New sources with no old file: `prompts/bot-08-signal.xml`, `prompts/bot-09-journal.xml`, `prompts/_shared/core-directives.xml`
(generate `agents/signal.md`, `agents/journal.md`).

### 1.3 Hermes (9 rows)

| # | Old path | New path | Decision | Evidence | Live-write? | Characterization test |
|---|---|---|---|---|---|---|
| 22 | `hermes/README.md` | same | rewrite | documents the `/workspace/trading-desk` file bus which becomes ledger-backed (section 4.6) | no | n/a |
| 23 | `hermes/cron/jobs.yaml` | same | keep-in-place | 6 jobs, `forbidden_owners: [sniper, exit]` (`hermes/cron/jobs.yaml:79`), `forbidden_actions` (`:80-84`); only `prompt_file` bodies change | no | n/a |
| 24 | `hermes/cron/prompts/chief-journal.md` | same | rewrite | wraps `tools/desk_state.py status` (`:4`) -> `pumpgrok journal rollup --daily` | no | n/a |
| 25 | `hermes/cron/prompts/chief-pickup.md` | same | rewrite | `desk_state.py status/pending-leads/pending-tickets` (`:13-15`) -> `pumpgrok chief pickup` | no | n/a |
| 26 | `hermes/cron/prompts/risk-audit.md` | same | rewrite | `desk_state.py status/pending-leads` (`:12-13`), `authority_check.py, holder_check.py` (`:16`) -> `pumpgrok risk audit --pending` | no | n/a |
| 27 | `hermes/cron/prompts/rug-watch.md` | same | rewrite | `desk_state.py status/open-positions` (`:10-11`) -> `pumpgrok rug watch` | no | n/a |
| 28 | `hermes/cron/prompts/scout-discover.md` | same | rewrite | `desk_state.py status`, `pending-leads` (`:12-14`) -> `pumpgrok scout discover --max-leads 5` | no | n/a |
| 29 | `hermes/cron/prompts/scout-pipeline.md` | same | rewrite | `pipeline_evidence.py --candidates --block --limit 5` (`:15`) -> `pumpgrok scout pipeline --candidates --limit 5` | no | n/a |
| 30 | `hermes/profiles.yaml` | same | keep-in-place | 8 profiles (`hermes/profiles.yaml:27-102`); skills lists drift from agent frontmatter (scout-pumpgrok-pack: discrepancy note) -> regenerated from `prompts/*.xml` skill lists; add `signal`, `journal` profiles | no | n/a |

### 1.4 Issues, rules, scripts (8 rows)

| # | Old path | New path | Decision | Evidence | Live-write? | Characterization test |
|---|---|---|---|---|---|---|
| 31 | `issues/tissue.json` | (none) | delete | content `{"version":"1.1.0"}` (20 B); inbound refs, code and instruction surfaces only: `rg -l -F tissue . --glob '!*.pyc' --glob '!docs/**'` -> no output (the only matches are this document and `docs/DISCOVERY.md`, which describe the deletion) | no | n/a |
| 32 | `rules/README.md` | same | keep-in-place | table restating 9 constraints; update tool paths only | no | n/a |
| 33 | `rules/pumpgrok-team.mdc` | same | keep-in-place | D2 "kept"; `scripts/check.sh:111-112` requires it; constitutional strings keep their exact bytes (R7). Note: `rules/pumpgrok-team.mdc:46` ("Micro-live trading is only enabled after the user explicitly confirms ...") is the one `micro-live` mention R16 does not list for rewriting; reported in section 2.5 and the closing summary, not resolved here | no | n/a |
| 34 | `scripts/README.md` | same | rewrite | claims check.sh validates "the Hermes cron pack" (`scripts/README.md:7`) which check.sh does not do (`scripts/check.sh` has no jobs.yaml parse) | no | n/a |
| 35 | `scripts/check.sh` | same | rewrite | hardcodes `vendor/grokbot-pumpfun/src/pipeline.py` and `vendor/grokbot-pumpfun/PUMPGROK.md` existence (`scripts/check.sh:118-119`) which retire; emoji regex excludes `vendor/` (`:142`); two dead `pass` checks (writer set, name match) | no | gate self-test `ci/tests/test_check_sh.py` [new] |
| 36 | `scripts/hermes-bootstrap.sh` | same | rewrite | `skills_for()` (`scripts/hermes-bootstrap.sh:21`) is a third copy of the per-role skill list (duplicated logic vs `hermes/profiles.yaml` and agent frontmatter); reads `agents/${role}.md` (`:159`) | no | n/a |
| 37 | `scripts/hermes-install-cron.sh` | same | rewrite | re-declares every job inline (`scripts/hermes-install-cron.sh:119-125`) instead of reading `hermes/cron/jobs.yaml` (duplicated logic) | no | n/a |
| 38 | `scripts/hermes-verify-isolation.sh` | same | rewrite | checks jobs.yaml exists (`:33`) and refuses sniper/exit owners (`:41`), both kept; the `engagement: micro-live` check (`scripts/hermes-verify-isolation.sh:52-53`) is rewritten to fail on any engagement other than `research` or `paper` (R16, section 2.5) | no | n/a |

### 1.5 Skills (24 rows)

All 23 skills keep their directory name (D2 "existing 23 upgraded in place"). Frontmatter today is `name` + `description`
only (scout-pumpgrok-pack skills inventory); new frontmatter adds `bots: [...]` and `gates: [...]` (values proposed in
section 4.2). Bodies gain `## L1 - Summary / ## L2 - Method / ## Failure modes / ## References`. Decision for all 24 is
keep-in-place; column 5 cites the tool reference that must be retargeted (`rg -n -o "tools/[a-z_]+\.py" skills/`).

| # | Old path | New path | Decision | Evidence | Live-write? | Characterization test |
|---|---|---|---|---|---|---|
| 39 | `skills/README.md` | same | rewrite | groups Core/Process/Domain; `skills/README.md:36` references `tools/pipeline_evidence.py`; must document `bots`/`gates` keys | no | n/a |
| 40 | `skills/browser-ops/SKILL.md` | same | keep-in-place | 596 B stub, no tool refs; detection/research only and listed in the forbidden-actions static test scope (no posting, no wallet UI; R39) | no | n/a |
| 41 | `skills/desk-execution-protocol/SKILL.md` | same | keep-in-place | `tools/jupiter_quote.py`, `tools/priority_fee.py` (`:18-19`) -> `pumpgrok` tools `exec.quote`, `onchain.priority_fee`; "Submit once only" (`:23`) becomes the PaperAdapter idempotency rule (R23) | quarantine (paper-write procedure, section 2.3) | n/a |
| 42 | `skills/desk-folders-and-journal/SKILL.md` | same | keep-in-place | file-bus tree -> ledger exports (section 4.6) | no | n/a |
| 43 | `skills/desk-incident-response/SKILL.md` | same | keep-in-place | no tool refs | no | n/a |
| 44 | `skills/desk-monitoring/SKILL.md` | same | keep-in-place | no tool refs; `Engagement: research \| paper \| micro-live` (`:12`) loses `micro-live` (R16, section 2.5) | no | n/a |
| 45 | `skills/desk-operating-model/SKILL.md` | same | keep-in-place | `tools/paper_sim.py` (`:35`) -> `pumpgrok paper buy\|sell`; engagement level `micro-live` (`:36`) retired, levels are `research \| paper` only (R16, section 2.5) | no | n/a |
| 46 | `skills/desk-post-trade-review/SKILL.md` | same | keep-in-place | no tool refs | no | n/a |
| 47 | `skills/desk-risk-limits/SKILL.md` | same | keep-in-place | `risk-limits.md` free text -> `RISK_POLICY.md` + config | no | n/a |
| 48 | `skills/desk-strategy-lab/SKILL.md` | same | keep-in-place | `tools/paper_sim.py --action buy\|sell` (`:12`); attached to no agent today (scout-pumpgrok-pack); "before promotion to micro-live" (`:17`) becomes "before promotion to paper autonomy" (R16, section 2.5) | no | n/a |
| 49 | `skills/desk-trade-lifecycle/SKILL.md` | same | keep-in-place | `tools/ticket_helper.py` (`:12,23,24`) -> `pumpgrok ticket next|create` | no | n/a |
| 50 | `skills/discovery-tools/SKILL.md` | same | keep-in-place | no tool refs | no | n/a |
| 51 | `skills/grokbot-pipeline/SKILL.md` | same | keep-in-place | `tools/pipeline_evidence.py` (`:3,12,46,47`), vendor `scripts/{dashboard,replay,tune}.py`, `requirements.txt`, pin `409e74c` -> all retargeted to `src/pumpgrok/engine` + `pumpgrok scout pipeline`; this is the last inbound ref that blocks vendor retirement (section 3.4) | no | n/a |
| 52 | `skills/hermes-cron-desk/SKILL.md` | same | keep-in-place | `tools/desk_state.py` (`:30-31`), `tools/ticket_helper.py` (`:32-33`) | no | n/a |
| 53 | `skills/holder-and-flow-analysis/SKILL.md` | same | keep-in-place | `tools/holder_check.py` (`:10`) | no | n/a |
| 54 | `skills/jupiter-routing/SKILL.md` | same | keep-in-place | `tools/jupiter_quote.py` (`:13`); `tools/priority_fee.py --max-micro` (`:18`; flag does not exist in `tools/priority_fee.py`, scout-pumpgrok-code; phrasing dropped, R40); "prepare a single-send transaction" (`:3`), "Submit once only" (`:28`), "do NOT retry" (`:29`) -> the skill becomes quote/route preparation feeding `exec.quote` and `exec.place` (paper); single-send is PaperAdapter idempotency (R18, R23) | quarantine (paper-write procedure, section 2.3) | n/a |
| 55 | `skills/position-monitoring/SKILL.md` | same | keep-in-place | no tool refs; "unless auto-exit pre-authorised" (`:25`) replaced by the R17 exit-automation rule (section 2.5) | no | n/a |
| 56 | `skills/pumpgrok-setup/SKILL.md` | same | keep-in-place | points to SETUP.md -> `docs/runbooks/setup.md`; "Set engagement to micro-live during setup" (`:45`) contradicts `ARCHITECTURE.md:234` ("Do not raise engagement to micro-live in setup"); both lines are removed by R16 (section 2.5) | no | n/a |
| 57 | `skills/risk-audit/SKILL.md` | same | keep-in-place | `tools/authority_check.py` (`:13`) | no | n/a |
| 58 | `skills/social-sentiment/SKILL.md` | same | keep-in-place | 507 B schema-only | no | n/a |
| 59 | `skills/solana-api-reference/SKILL.md` | same | keep-in-place | no tool refs | no | n/a |
| 60 | `skills/solana-market-data/SKILL.md` | same | keep-in-place | `tools/jupiter_quote.py` (`:9`) | no | n/a |
| 61 | `skills/solana-rpc-and-wallet/SKILL.md` | same | keep-in-place | `tools/priority_fee.py` (`:15`); wallet rules (`:9-12`: throwaway wallet, keys never enter chat/files/memory, human screen hand-off, public address recorded) stay prose; after migration no wallet connection exists in paper mode ("no key material exists in paper mode; nothing to custody", R40); the only wallet datum the system ever stores is the live-gate public-address allowlist (R21), see section 2.5 | no | n/a |
| 62 | `skills/tool-connections/SKILL.md` | same | keep-in-place | no tool refs; "Wallet Connection Protocol" (`:17-22`) is a human screen hand-off that records a public address only; retained as the no-key procedure for the (disabled) live path, section 2.5 | no | n/a |

### 1.6 Tests and tools (16 rows)

| # | Old path | New path | Decision | Evidence | Live-write? | Characterization test |
|---|---|---|---|---|---|---|
| 63 | `tests/__pycache__/test_tools_cli.cpython-312.pyc` | (none) | delete | build artifact; no root `.gitignore` exists (`cat .gitignore` -> "NO ROOT .gitignore"); inbound refs, code only (docs excluded): `rg -l -F __pycache__ . --hidden --glob '!.git' --glob '!*.pyc' --glob '!docs/**'` -> `vendor/grokbot-pumpfun/Makefile` (its `clean` target), `vendor/grokbot-pumpfun/.gitignore:9`, `vendor/grokbot-pumpfun/.dockerignore:5` (all three retire in batch 5, rows 79, 82, 85; `--hidden` is required because `rg` skips dotfiles by default) | no | n/a |
| 64 | `tests/test_tools_cli.py` | `tests/desk/test_cli.py` | rewrite | loads tools via `importlib.util.spec_from_file_location` (`tests/test_tools_cli.py:25`); 4 classes (`:33,91,172,184`); tests 10-11 assert SKILL.md/README text; with `src/pumpgrok` package the by-path loader goes away | no | this file IS the contract test for rows 71-78; its JSON `ok:false`/exit-1 assertions port into each `tests/characterization/test_<tool>.py` |
| 65 | `tools/README.md` | (none; superseded by `docs/TOOL_CATALOG.md`) | delete | inbound refs, code and instruction surfaces only: `rg -l -F tools/README . --glob '!*.pyc' --glob '!docs/**'` -> `ARCHITECTURE.md`, `README.md` (both rewritten, rows 7 and 9) -> zero after batch 5; `docs/DISCOVERY.md:397` also names it as a today-fact and is left as is | no | n/a |
| 66 | `tools/__pycache__/authority_check.cpython-312.pyc` | (none) | delete | same check as row 63 | no | n/a |
| 67 | `tools/__pycache__/holder_check.cpython-312.pyc` | (none) | delete | same check as row 63 | no | n/a |
| 68 | `tools/__pycache__/jupiter_quote.cpython-312.pyc` | (none) | delete | same check as row 63 | no | n/a |
| 69 | `tools/__pycache__/paper_sim.cpython-312.pyc` | (none) | delete | same check as row 63 | no | n/a |
| 70 | `tools/__pycache__/priority_fee.cpython-312.pyc` | (none) | delete | same check as row 63 | no | n/a |
| 71 | `tools/authority_check.py` | `src/pumpgrok/tools/onchain/authorities.py` (tool `onchain.authorities`, R31) | rewrite | `import requests` (`:17`), `DEFAULT_RPC = "https://api.mainnet-beta.solana.com"` (`:22`), `def rpc_call` copy 1 of 3 (`:25`) | no | `tests/characterization/test_authority_check.py` (JSON keys ok,mint,mintAuthority,freezeAuthority,...; exit 1 on error) |
| 72 | `tools/desk_state.py` | `src/pumpgrok/cli.py` subcommands `state status\|halt` over `src/pumpgrok/ledger/` views (`halt --clear --by --reason` is human-only, R22) | rewrite | `import os` (`:13`), `repo_root` (`:43`), `desk_root` copy 2 of 2 (`:50`), `next_ticket_id(desk)` copy 2 of 2 (`:107`); regex-parses markdown | no | `tests/characterization/test_desk_state.py` (status payload keys: ok,utc,engagement,halt,pending_leads,pending_tickets,open_positions,known_tickets,next_ticket; `engagement` values narrow to `research\|paper`, R16) |
| 73 | `tools/holder_check.py` | `src/pumpgrok/tools/onchain/holders.py` (tool `onchain.top_holders`) | rewrite | `import requests` (`:18`), `DEFAULT_RPC` (`:23`), `def rpc_call` copy 2 of 3 (`:26`) | no | `tests/characterization/test_holder_check.py` |
| 74 | `tools/jupiter_quote.py` | `src/pumpgrok/tools/market/jupiter.py` (tool `exec.quote`; informational route/priority only, never the fill price, R38) | rewrite | `import requests` (`:17`), `JUPITER_QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"` (`:22`) hardcoded venue URL -> config; D8 keeps the venue | no | `tests/characterization/test_jupiter_quote.py` (ports `JupiterQuoteContract`, `tests/test_tools_cli.py:33-71`) |
| 75 | `tools/paper_sim.py` | `src/pumpgrok/execution/paper_adapter.py` (`PaperAdapter`, R31) + `pumpgrok paper buy\|sell --ticket --mint --size-sol --slippage-bps --approval-id` (R40) | rewrite | unused `import os` (`:18`); appends markdown to `<desk>/journal/paper-YYYY-MM-DD.md` (scout-pumpgrok-code per-tool table) - no ledger, slippage recorded but not applied | no (paper only) | `tests/characterization/test_paper_sim.py` (stdout keys ok,mode:"paper",action,ticketId,mint,sizeUsd,price,slippageBps,utc) |
| 76 | `tools/pipeline_evidence.py` | `src/pumpgrok/reporting/evidence.py` + `pumpgrok scout pipeline` | rewrite | `DEFAULT_LOG="vendor/grokbot-pumpfun/logs/trades.jsonl"` hardcoded vendor path (scout-pumpgrok-code), own `repo_root` (`:26`); reads JSONL -> reads ledger `events` | no | `tests/characterization/test_pipeline_evidence.py` (13-line PIPELINE-EVIDENCE block format, `--candidates` filter `type=buy and tx_hash=="dry_run"`) |
| 77 | `tools/priority_fee.py` | `src/pumpgrok/tools/onchain/priority_fee.py` (tool `onchain.priority_fee`) | rewrite | `import requests` (`:19`), `DEFAULT_RPC` (`:24`), `def rpc_call` copy 3 of 3 (`:27`); `recommended_lamports_per_cu` alias mislabels units | no | `tests/characterization/test_priority_fee.py` |
| 78 | `tools/ticket_helper.py` | `src/pumpgrok/ledger/tickets.py` + `pumpgrok ticket next|create|list` | rewrite | `import os` (`:20`), `desk_root` copy 1 of 2 (`:41`), `next_ticket_id()` copy 1 of 2 (`:80`); scan-and-increment ID allocation is not atomic (D9 ticket format enforced in code via a ledger sequence) | no | `tests/characterization/test_ticket_helper.py` (`SOL-\d{8}-\d{3}` regex, duplicate refusal) |

### 1.7 Vendor packaging, docs, config (16 rows)

All vendor rows retire together (section 3.4). "At retirement" means the delete happens in batch 5 after the inbound
reference census returns zero.

| # | Old path | New path | Decision | Evidence | Live-write? | Characterization test |
|---|---|---|---|---|---|---|
| 79 | `vendor/grokbot-pumpfun/.dockerignore` | (none) | delete | inbound refs: `rg -l -F .dockerignore . --glob '!*.pyc'` -> no output; root `Dockerfile` gets its own | no | n/a |
| 80 | `vendor/grokbot-pumpfun/.env.example` | `.env.example` | rewrite | lists `MODE, GROK_API_KEY, DATA_API_KEY, WALLET_PRIVATE_KEY, LOG_LEVEL` (scout-vendor-engine); `WALLET_PRIVATE_KEY` is dropped (D4), prefix becomes `PUMPGROK_` | quarantine (section 2.2) | n/a |
| 81 | `vendor/grokbot-pumpfun/.github/workflows/ci.yml` | `.github/workflows/ci.yml` | rewrite | runs `ruff check .`, `mypy src`, `pytest --cov=src` (`ci.yml:34-40`), negative check `python -m src.pipeline --config config.example.yaml --check` (`:44`); matrix 3.11-3.13 -> 3.12 only (D1) | no | n/a |
| 82 | `vendor/grokbot-pumpfun/.gitignore` | `.gitignore` | rewrite | vendor ignores `config.yaml, *.jsonl, logs/, __pycache__/, state/, .env` (`cat vendor/grokbot-pumpfun/.gitignore`); root has none; merge with programming-desk's 9-line `.gitignore` (`.receipts/**/*.json`, `!.receipts/**/.gitkeep`) plus `var/` | no | n/a |
| 83 | `vendor/grokbot-pumpfun/Dockerfile` | `Dockerfile` | rewrite | python:3.12-slim, non-root, `ENTRYPOINT python -m src.pipeline` (scout-vendor-engine Docker section) -> `uv` multi-stage, entrypoint `pumpgrok run --mode paper` | no | n/a |
| 84 | `vendor/grokbot-pumpfun/LICENSE` | `src/pumpgrok/engine/LICENSE-grokbot-pumpfun` | keep-and-move | MIT (`vendor/grokbot-pumpfun/pyproject.toml:11`); the notice must travel with the ported code; non-code so the characterization-test rule does not apply | no | n/a |
| 85 | `vendor/grokbot-pumpfun/Makefile` | `Makefile` | rewrite | targets install/dev/test/cov/lint/fmt/types/check/run/dashboard/replay/tune/docker/clean reference `requirements*.txt` and `src.pipeline` (`rg -l -F requirements.txt .` includes the Makefile) | no | n/a |
| 86 | `vendor/grokbot-pumpfun/PUMPGROK.md` | `docs/VENDOR_PIN.md` | keep-and-move | pin note (upstream, `409e74c...`, MIT, 4 desk rules; `PUMPGROK.md:1-28`); inbound refs to retarget: `rg -l -F PUMPGROK.md .` -> ARCHITECTURE.md README.md SETUP.md `scripts/check.sh:119` skills/grokbot-pipeline/SKILL.md | no | n/a |
| 87 | `vendor/grokbot-pumpfun/README.md` | (none) | delete | upstream README; inbound refs: `rg -l -F grokbot-pumpfun/README . --glob '!*.pyc'` -> no output | no | n/a |
| 88 | `vendor/grokbot-pumpfun/RUNBOOK.md` | `docs/runbooks/engine.md` | rewrite | English already; incident playbooks (breaker open, budget 0, stalled, blind, halted, corrupt state, executor_not_implemented) keep their meaning but every command changes to `pumpgrok ...`; inbound refs (`rg -l -F RUNBOOK.md . --hidden --glob '!.git' --glob '!docs/**'`): `vendor/grokbot-pumpfun/README.md` (row 87) and `vendor/grokbot-pumpfun/.dockerignore:16` (row 79), both deleted in the same batch | no | n/a |
| 89 | `vendor/grokbot-pumpfun/config.example.yaml` | `src/pumpgrok/config/overlays/{dev,paper,live}.toml` (in-package, R30; operator overlay via `PUMPGROK_CONFIG=<file>`; no root `config/` directory) | rewrite | YAML with `mode`, `solana.wallet_private_key`, `solana.jito` (`config.example.yaml:28-31`) -> TOML overlays (D5), wallet key and jito block removed (section 2.2, FOUNDATION_STACK M-10) | quarantine (section 2.2) | n/a |
| 90 | `vendor/grokbot-pumpfun/conftest.py` | `tests/conftest.py` | rewrite | inserts repo root in sys.path (`conftest.py:6`); programming-desk `tests/conftest.py` inserts repo root AND `src/` (`cat /root/src/repos/programming-desk/tests/conftest.py`) | no | n/a |
| 91 | `vendor/grokbot-pumpfun/docker-compose.yml` | `docker-compose.yml` | rewrite | single service, `GROKBOT_HEALTH_PORT=8080`, 512M limit (scout-vendor-engine) -> `PUMPGROK_*` env, `var/` volume | no | n/a |
| 92 | `vendor/grokbot-pumpfun/pyproject.toml` | `pyproject.toml` | rewrite | setuptools, `packages = ["src", "src.agents"]` (`:37-38`), declares unused `solders>=0.21`, `solana>=0.34` (`:17-18`), `[project.scripts] grokbot = "src.pipeline:main"`; pytest `asyncio_mode = "auto"` (`:42`) is kept | quarantine (section 2.2: signer deps removed) | n/a |
| 93 | `vendor/grokbot-pumpfun/requirements-dev.txt` | (none; `uv.lock` dev group) | delete | inbound refs (`rg -l -F requirements-dev . --hidden --glob '!.git' --glob '!docs/**'`) -> `vendor/grokbot-pumpfun/Makefile` (row 85), `vendor/grokbot-pumpfun/README.md` (row 87), `vendor/grokbot-pumpfun/.github/workflows/ci.yml:31` (row 81, rewritten as the root `ci.yml`), plus the self-include `requirements-dev.txt:1` (`-r requirements.txt`); all retire in the same batch | no | n/a |
| 94 | `vendor/grokbot-pumpfun/requirements.txt` | (none; `uv.lock`) | delete | inbound refs: `rg -l -F requirements.txt .` -> `skills/grokbot-pipeline/SKILL.md` (retargeted row 51), vendor README, requirements-dev.txt, Makefile, Dockerfile (all retire) | no | n/a |

### 1.8 Vendor scripts and src (22 rows)

Column "English" in section 3.1 says what strings get translated. Cyrillic line counts per module come from
`rg -c '<cyrillic-char-class>' <file>` where the class is the Unicode range U+0410-U+044F plus U+0401/U+0451 (reported in section 3.1).

| # | Old path | New path | Decision | Evidence | Live-write? | Characterization test |
|---|---|---|---|---|---|---|
| 95 | `vendor/grokbot-pumpfun/scripts/dashboard.py` | `src/pumpgrok/reporting/dashboard.py` + `pumpgrok report --daily` | rewrite | recomputes today/total PnL from JSONL (scout-vendor-engine) -> reads ledger snapshots; 14 Cyrillic lines | no | n/a (no vendor test) |
| 96 | `vendor/grokbot-pumpfun/scripts/replay.py` | `src/pumpgrok/reporting/summary.py` | rewrite | log summary (score buckets, skip reasons) - NOT stream replay; name collides with D2 `src/pumpgrok/replay/` (recorded-stream replay), hence renamed `summary.py`; 35 Cyrillic lines | no | n/a (no vendor test) |
| 97 | `vendor/grokbot-pumpfun/scripts/tune.py` | `src/pumpgrok/engine/tune.py` | keep-and-move | grid search over logged component scores; `tests/test_tune.py` (15 tests) ports 1:1; 53 Cyrillic lines (CLI help/prints) | no | `tests/characterization/test_tune.py` |
| 98 | `vendor/grokbot-pumpfun/src/__init__.py` | `src/pumpgrok/engine/__init__.py` | rewrite | 3 lines, 1 Cyrillic docstring; new package docstring | no | n/a |
| 99 | `vendor/grokbot-pumpfun/src/agents/__init__.py` | `src/pumpgrok/engine/agents/__init__.py` | keep-and-move | 16-line export list | no | covered by `test_agents.py` port |
| 100 | `vendor/grokbot-pumpfun/src/agents/auditor.py` | `src/pumpgrok/engine/agents/auditor.py` | keep-and-move | `AuditorAgent`, `AUDITOR_PROMPT` (scout-vendor-engine); 24 Cyrillic lines | no | `tests/characterization/test_agents.py` |
| 101 | `vendor/grokbot-pumpfun/src/agents/base.py` | `src/pumpgrok/engine/agents/base.py` | keep-and-move | `GrokAgent._call` POSTs x.ai chat/completions via `httpx.AsyncClient` (`base.py:75`), retries 5xx/429/timeouts (`:165-171`); own `_backoff` kept (tenacity adoption is NOT part of the move, section 6) | no | `tests/characterization/test_agents.py` (21 tests, `httpx.MockTransport`) |
| 102 | `vendor/grokbot-pumpfun/src/agents/checker.py` | `src/pumpgrok/engine/agents/checker.py` | keep-and-move | `CheckerAgent use_checker_model=True`; seat owner bot-08-signal (D3) | no | `tests/characterization/test_agents.py` |
| 103 | `vendor/grokbot-pumpfun/src/agents/narrative.py` | `src/pumpgrok/engine/agents/narrative.py` | keep-and-move | 69 lines | no | `tests/characterization/test_agents.py` |
| 104 | `vendor/grokbot-pumpfun/src/agents/timing.py` | `src/pumpgrok/engine/agents/timing.py` | keep-and-move | cached `get()` under asyncio lock | no | `tests/characterization/test_agents.py` |
| 105 | `vendor/grokbot-pumpfun/src/alerts.py` | `src/pumpgrok/tools/notify/webhook.py` (adapter under abstract `Notifier`, D6) | rewrite | `Notifier._send` POSTs Slack/Discord shape (scout-vendor-engine); D6 requires abstract Notifier + stdout/file sinks + Telegram/webhook adapters, so this becomes one adapter; `test_alerts.py` (19) adapts | no | `tests/characterization/test_alerts.py` (rate limit, redaction, event filter semantics preserved) |
| 106 | `vendor/grokbot-pumpfun/src/analyzer.py` | `src/pumpgrok/engine/analyzer.py` | keep-and-move | 3 parallel GETs to `data.rest_url` (scout-vendor-engine), `signature=raw.get("signature")` is read-only trade parsing (`analyzer.py:136`) | no | `tests/characterization/test_analyzer.py` (16) |
| 107 | `vendor/grokbot-pumpfun/src/executor.py` | split (R31): `ExecutionResult`, `BaseExecutor.price`, `price_from_reserves`, `new_position` -> `src/pumpgrok/execution/curve_math.py` (`CurveQuote.spot()` verbatim, constant-product fill added on top); `DryRunExecutor` -> `src/pumpgrok/execution/paper_adapter.py` (`PaperAdapter`, with `execution/fees.py` and `execution/latency.py`); `LiveExecutor` -> `src/pumpgrok/execution/live/live_adapter.py` raising `LiveGateError`, gate in `execution/live/live_gate.py` (owned by bot-02-risk) | rewrite | `DRY_RUN_TX = "dry_run"` (`:30`), `DryRunExecutor` (`:100-133`) no slippage/fee, `LiveExecutor` (`:137-172`) raises `NotImplementedError` with a 6-step Russian TODO naming `solders.keypair`, `send_transaction`, `jito` (`:150-158`); `build_executor` (`:175-180`) selects by `config.is_live` | quarantine (section 2.1) | `tests/characterization/test_executor.py` (new: dry-run buy/sell math `token_amount = size_sol / price` (`:119`), `proceeds = token_amount * price` (`:125`), `tx_hash == "dry_run"`; the paper adapter must reproduce these numbers when slippage/fee are zero) |
| 108 | `vendor/grokbot-pumpfun/src/log.py` | `src/pumpgrok/ledger/journal.py` (JSONL export of ledger events) | rewrite | `TradeLog` writes `buy/skip/close` JSONL with size rotation (scout-vendor-engine log.py map); ledger becomes the source of truth and JSONL the export (D5) | no | `tests/characterization/test_log.py` (record shapes `type:buy|skip|close`, `ts`/`mode` stamping; 8 tests adapt to export API) |
| 109 | `vendor/grokbot-pumpfun/src/models.py` | split: domain models `Token..TradeDecision` (`models.py:26-270`) -> `src/pumpgrok/engine/models.py` verbatim; config classes `SecretModel..Config` (`:271-624`) -> `src/pumpgrok/config/settings.py` | rewrite | config half: `SolanaConfig.wallet_private_key` (`:299`), `wallet_key` (`:303-304`), `ENV_OVERRIDES GROKBOT_*` (`:403-414`), `is_live` (`:467-468`), live checks (`:571-576`) -> pydantic-settings TOML + `PUMPGROK_*`; `JitoConfig` (`:291`) and `rpc_url` default `https://api.mainnet-beta.solana.com` (`:298`) | quarantine (section 2.2) | `tests/characterization/test_models.py` (domain half 1:1 from the model assertions in `test_analyzer.py`/`test_scoring.py`); `test_config.py` (20) adapts to settings API, keeping "secrets never dumped", "placeholder rejected", "live requires explicit flag" semantics |
| 110 | `vendor/grokbot-pumpfun/src/monitor.py` | `src/pumpgrok/engine/monitor.py` | keep-and-move | `import websockets` (`:23`), `async with websockets.connect(self.config.data.ws_url)` (`:218`), `ws.send` (`:219,258`), `ws.recv` (`:225`); package action in section 6 | no | `tests/characterization/test_monitor.py` (ports `test_filter.py`, 21 tests; `patch_socket` at `test_filter.py:281` monkeypatches `monitor_module.websockets.connect`) |
| 111 | `vendor/grokbot-pumpfun/src/ops.py` | split per `docs/design/paper-engine.md` section 1: `RateLimiter` -> `src/pumpgrok/core/ratelimit.py`; `CallBudget` -> `core/budget.py`; `GrokOps` precheck -> `core/llm.py`; `CircuitBreaker` -> `src/pumpgrok/risk/breakers.py` (base class of the three risk breakers); `drain`, `install_signal_handlers`, `cancel_and_wait`, `Heartbeat` -> `src/pumpgrok/supervisor/lifecycle.py`; `Metrics.prometheus()` hand-rolled text and the raw asyncio `HealthServer` are re-based on `prometheus_client` in `supervisor/metrics.py` and `supervisor/health.py` (D5) | keep-and-move | `install_signal_handlers` (`ops.py:427-431`); the metrics/health subset is a rewrite inside an otherwise 1:1 move | no | `tests/characterization/test_ops.py` (24; HealthServer tests adapt to the new exposition; the rest 1:1 against the split modules) |
| 112 | `vendor/grokbot-pumpfun/src/pipeline.py` | `src/pumpgrok/engine/pipeline.py` (`Pipeline` class) ; CLI/config/live-flag code -> `src/pumpgrok/cli.py` | rewrite | `Pipeline.process` stages kept; `--i-understand-the-risk` (`pipeline.py:18,499,509`), `LIVE_WARNING` (`:490`), `load_and_check` (`:514-540`) raising `SystemExit` on live without flag, `NotImplementedError` catch at buy (`:281`) and sell (`:441`) replaced by `LiveGateError` handling; 104 Cyrillic lines | quarantine (section 2.1) | `tests/characterization/test_pipeline.py` (37; `wire()` client swapping preserved; live-flag tests become `LiveGateError` tests) |
| 113 | `vendor/grokbot-pumpfun/src/reputation.py` | `src/pumpgrok/engine/reputation.py` | keep-and-move | `ReputationBook`, `MAX_CREATORS=50000`, JSON file at `ops.reputation_path` (file path becomes `var/reputation.json`) | no | `tests/characterization/test_reputation.py` (18) |
| 114 | `vendor/grokbot-pumpfun/src/risk.py` | split (R31): `RiskManager` limit checks -> `src/pumpgrok/risk/engine.py` (`RiskEngine`; the class is RiskEngine, not RiskManager), sizing -> `risk/sizing.py`; `ExitSignal`, `exit_signal` -> `src/pumpgrok/engine/exits.py` (bot-06-exit); `PositionWatcher` -> `src/pumpgrok/engine/watcher.py` (bot-05-rug) | keep-and-move | `position_size = min(max_sol_per_trade*score, remaining_loss_budget*0.30)` (`risk.py:145`), `def evaluate` (`:149`), exit priority stop_loss > take_profit > trailing > max_hold (`:238`); day-rollover auto-clear of `halted` (`:106-117`, `:131-134`) is NOT carried (R5: human clear only); D6 breakers/kill switch are ADDED beside it in `src/pumpgrok/risk/{limits,breakers,killswitch}.py` (new files, not a rewrite of this one) | no | `tests/characterization/test_risk.py` (36; the auto-clear cases are adapted to assert the halt persists across rollover) |
| 115 | `vendor/grokbot-pumpfun/src/scoring.py` | `src/pumpgrok/engine/scoring.py` | keep-and-move | 79 lines, 13 Cyrillic; owner bot-08-signal (D3 "ports vendor scoring + checker") | no | `tests/characterization/test_scoring.py` (13) |
| 116 | `vendor/grokbot-pumpfun/src/state.py` | `src/pumpgrok/ledger/snapshots.py` | rewrite | `StateStore` atomic tmp+replace JSON, `STATE_VERSION=1` (scout-vendor-engine) -> sqlite WAL `snapshots` table (D5) | no | `tests/characterization/test_state.py` (16; "corrupt file is quarantined", "restart restores positions" semantics kept) |

### 1.9 Vendor tests (13 rows)

Each row ports to `tests/characterization/test_<module>.py`; "1:1" means the test body is unchanged apart from the
import path and English message assertions (section 3.3). "adapt" means the public API of the target changed (rewrite rows).

| # | Old path | New path | Decision | Evidence | Live-write? | Characterization test |
|---|---|---|---|---|---|---|
| 117 | `vendor/grokbot-pumpfun/tests/test_agents.py` | `tests/characterization/test_agents.py` | keep-and-move (1:1) | 21 tests (`rg -c 'def test_'`) | no | self |
| 118 | `vendor/grokbot-pumpfun/tests/test_alerts.py` | `tests/characterization/test_alerts.py` | rewrite (adapt) | 19; target row 105 is a rewrite | no | self |
| 119 | `vendor/grokbot-pumpfun/tests/test_analyzer.py` | `tests/characterization/test_analyzer.py` | keep-and-move (1:1) | 16; `httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(...))` (`test_analyzer.py:43`) | no | self |
| 120 | `vendor/grokbot-pumpfun/tests/test_config.py` | `tests/characterization/test_config.py` | rewrite (adapt) | 20; target row 109 config half is a rewrite; `docker-compose` referenced (`rg -l -F docker-compose .`) | no | self |
| 121 | `vendor/grokbot-pumpfun/tests/test_filter.py` | `tests/characterization/test_monitor.py` | keep-and-move (1:1 except `patch_socket` target, section 6) | 21; `FakeWebSocket` (`test_filter.py:245`) | no | self |
| 122 | `vendor/grokbot-pumpfun/tests/test_log.py` | `tests/characterization/test_log.py` | rewrite (adapt) | 8; target row 108 is a rewrite | no | self |
| 123 | `vendor/grokbot-pumpfun/tests/test_ops.py` | `tests/characterization/test_ops.py` | keep-and-move (HealthServer subset adapts) | 24; HealthServer tests bind a real loopback port (scout-vendor-engine) | no | self |
| 124 | `vendor/grokbot-pumpfun/tests/test_pipeline.py` | `tests/characterization/test_pipeline.py` | rewrite (adapt) | 37; `signature` fixture (`test_pipeline.py:79`) is read-only trade data; live-flag tests become `LiveGateError` tests | no | self |
| 125 | `vendor/grokbot-pumpfun/tests/test_reputation.py` | `tests/characterization/test_reputation.py` | keep-and-move (1:1) | 18 | no | self |
| 126 | `vendor/grokbot-pumpfun/tests/test_risk.py` | `tests/characterization/test_risk.py` | keep-and-move (1:1 except imports split across `risk/engine.py`, `engine/exits.py`, `engine/watcher.py`, and the halt auto-clear cases, row 114) | 36 | no | self |
| 127 | `vendor/grokbot-pumpfun/tests/test_scoring.py` | `tests/characterization/test_scoring.py` | keep-and-move (1:1) | 13 | no | self |
| 128 | `vendor/grokbot-pumpfun/tests/test_state.py` | `tests/characterization/test_state.py` | rewrite (adapt) | 16; target row 116 is a rewrite | no | self |
| 129 | `vendor/grokbot-pumpfun/tests/test_tune.py` | `tests/characterization/test_tune.py` | keep-and-move (1:1) | 15 | no | self |

### 1.10 Census and decision totals

Rows: 1.1 = 12, 1.2 = 9, 1.3 = 9, 1.4 = 8, 1.5 = 24, 1.6 = 16, 1.7 = 16, 1.8 = 22, 1.9 = 13 -> 129 = `git ls-files | wc -l` (129).
Every tracked path appears exactly once; rows 63 and 66-70 are the six tracked `__pycache__/*.pyc` artefacts.

| Decision | Count | Rows |
|---|---|---|
| keep-in-place | 36 | 1-6, 8, 11, 12, 23, 30, 32, 33, 40-62 |
| generate | 9 | 13-21 |
| rewrite | 49 | 7, 9, 10, 22, 24-29, 34-38, 39, 64, 71-78, 80-83, 85, 88-92, 95, 96, 98, 105, 107-109, 112, 116, 118, 120, 122, 124, 128 |
| keep-and-move | 23 | 84, 86, 97, 99-104, 106, 110, 111, 113-115, 117, 119, 121, 123, 125-127, 129 (84 and 86 are non-code moves; the 8 test rows are their own characterization tests) |
| delete | 12 | 31, 63, 65-70, 79, 87, 93, 94 |

36 + 9 + 49 + 23 + 12 = 129. (Row 38 moved from keep-in-place to rewrite in the convergence pass, R16.)

Census note: the 129 count is `git ls-tree -r --name-only 8f7ae72 | wc -l` at the HEAD this map covers. The
current branch head adds eight paths that are not mapped here because they are outputs of this design wave,
not inputs: `docs/{DISCOVERY,FOUNDATION_STACK,MIGRATION_MAP,ROSTER,TOOL_CATALOG}.md`,
`docs/design/{interfaces,paper-engine}.md`, `.planning/config.json`
(`comm -13 <(git ls-tree -r --name-only 8f7ae72 | sort) <(git ls-files | sort)`; `git ls-files | wc -l` -> 137).

## 2. Live-write quarantine

Commands run from repo root (convergence pass; the earlier run excluded `*.md` and therefore never searched
the instruction surfaces, review B finding 1):

1. Code and config: `rg -n -i "sign|send_transaction|swap|keypair|jito" --type py --type yaml --type sh --type toml . | rg -v __pycache__ | rg -v -i "design|signal|signif|assign"`
   (the second filter removes the false positives `signal`, `assign`, `design`; `signature` hits were reviewed by hand). Hits: section 2.1.
2. Markdown instruction surfaces: the same pattern with `--glob '*.md' --glob '!docs/**' --glob '!vendor/**'`, plus
   `rg -n -i "micro-live|auto-exit|pre-authori|submit once|single-send|do not retry|hand-off|public address" --glob '*.md' --glob '*.sh' --glob '!docs/**' --glob '!vendor/**' .`
   Hits: section 2.5 (every file with live, micro-live, send or wallet prose and its disposition).

### 2.1 Code hits and disposition

| File:line | Hit | Disposition |
|---|---|---|
| `hermes/cron/jobs.yaml:81-82` | `forbidden_actions: send_transaction, sign` | keep; policy list, mirrored into `ci/gates/check_desk_integrity.py` (cron owners must not be sniper/exit; already enforced by `scripts/hermes-verify-isolation.sh:41`) |
| `tools/jupiter_quote.py:8` / `:22` / `:51` | "Never signs or sends." docstring; `/swap/v1/quote` URL; `swapInfo` field | read-only quote; the `/swap` path segment is the Jupiter quote endpoint, no swap transaction is built. Moves to `exec.quote` (row 74); the quote is informational and never the fill price (R38) |
| `tools/holder_check.py:9`, `tools/priority_fee.py:9`, `tools/authority_check.py:8`, `tools/desk_state.py:5`, `tools/pipeline_evidence.py:10,228`, `tools/ticket_helper.py:15` | "Never signs or sends" docstrings | keep the sentence verbatim in the ported module docstrings; a gate test asserts it (section 2.4) |
| `tests/test_tools_cli.py:34,38,59,71` | URL/`swapInfo` assertions | port with row 74 |
| `vendor/grokbot-pumpfun/src/analyzer.py:136` | `signature=raw.get("signature") or raw.get("tx")` | read-only parse of observed trades; keep (row 106) |
| `vendor/grokbot-pumpfun/src/models.py:80` | `Trade.signature: str | None` | read-only domain field; keep (row 109 domain half) |
| `vendor/grokbot-pumpfun/src/models.py:291-294, 299, 300` | `class JitoConfig` (`block_engine_url` default `https://mainnet.block-engine.jito.wtf/...`), `SolanaConfig.wallet_private_key` (`:299`), `SolanaConfig.jito` (`:300`) | DELETE from settings (R3, FOUNDATION_STACK M-10). No code reads `jito` except the `LiveExecutor` TODO comment; `wallet_private_key` must not exist as a setting (D4 "private keys never enter the system"); D8 covers venues and data sources only, so Jito is dead config, not a dropped venue |
| `vendor/grokbot-pumpfun/src/models.py:303-304, 407, 572-573, 610` | `wallet_key` property, `GROKBOT_WALLET_PRIVATE_KEY` env override, live check "wallet key not set", masking in dump | DELETE with the field. Replaced by the nine `LiveGate` preconditions of R21: (1) effective mode `live` (CLI `--mode` > `PUMPGROK_MODE` > TOML, R30); (2) `PUMPGROK_LIVE_ENABLE=1`; (3) `live.min_paper_days >= 14` on `source=paper` ledger events only; (4) closed_trades >= 50, profit_factor >= 1.2, max_drawdown <= `drawdown_halt_fraction` on the same events; (5) non-empty `live.wallet_allowlist` (public addresses only); (6) `0 < live.notional_cap_sol <= 1.0`; (7) HMAC-signed confirmation record from `pumpgrok live confirm`; (8) `live.adapter` named AND registered (none ships, always unmet); (9) no active kill switch, halt or open breaker |
| `vendor/grokbot-pumpfun/src/executor.py:137-172` | `class LiveExecutor`; TODO lines `:150` (`Keypair ... solders.keypair`), `:156-158` (`jito ... send_transaction`); `raise NotImplementedError` (`:161`, `:169`) | REWRITE to `src/pumpgrok/execution/live/live_adapter.py` (R31, owned by bot-02-risk): `class LiveAdapter(ExecutionAdapter)` whose `place`/`simulate`/`cancel` raise `LiveGateError("live execution is disabled in this build")`. The 6-step TODO recipe is NOT carried over (no instructions for signing ship in the repo) |
| `vendor/grokbot-pumpfun/src/executor.py:175-180` | `build_executor` picks `LiveExecutor` when `config.is_live` | REWRITE: `src/pumpgrok/execution/__init__.py:build_adapter(settings)` returns `PaperAdapter` when the effective mode is `paper`; when it is `live` it evaluates `execution/live/live_gate.py:LiveGate.unmet()` and, if any precondition is unmet, prints all of them and exits 3 (R21); if all nine are met (impossible while precondition 8 has no registered implementation) it STILL returns `LiveAdapter` (the stub) - no code path submits a transaction |
| `vendor/grokbot-pumpfun/src/pipeline.py:18,490-499,509,533-540` | `--i-understand-the-risk`, `LIVE_WARNING`, `SystemExit` without flag | REWRITE into `src/pumpgrok/cli.py run --mode`; the flag is replaced by the R21 precondition list; `pipeline.py:281` and `:441` `except NotImplementedError` become `except LiveGateError` |
| `vendor/grokbot-pumpfun/src/pipeline.py:506-509, 533` and `models.py:467-468` (`is_live`) | mode switch | keep the enum `paper|live`; `dry-run` alias is removed (D4 "mode defaults to paper") |
| `vendor/grokbot-pumpfun/tests/test_pipeline.py:79` | `"signature": f"s{i}"` fixture | read-only; port with row 124 |
| `vendor/grokbot-pumpfun/config.example.yaml:29-31` | `jito:` block | DELETE with row 89 |
| `vendor/grokbot-pumpfun/pyproject.toml:17-18`, `requirements.txt:5-6` | `solders>=0.21`, `solana>=0.34` declared | DELETE: never imported anywhere (section 2.4 proof); root `pyproject.toml` MUST NOT declare them |
| `vendor/grokbot-pumpfun/.env.example` | `WALLET_PRIVATE_KEY` | DELETE from `.env.example` (row 80) |

### 2.2 Config and dependency quarantine summary

| Item | Today | After |
|---|---|---|
| Wallet private key setting | `SolanaConfig.wallet_private_key: SecretStr` (`models.py:299`), env `GROKBOT_WALLET_PRIVATE_KEY` (`:407`) | none. `Settings` has no field whose name matches `*key*|*secret*|*seed*|*mnemonic*` except `grok.api_key` and `data.api_key`; `hermes/profiles.yaml` `forbidden_env_keys` (PRIVATE_KEY/SECRET_KEY/SEED/MNEMONIC/PHANTOM/WALLET_SECRET, scout-pumpgrok-pack) becomes a `check_secrets.py` rule |
| Jito | `JitoConfig` (`models.py:291`), `config.example.yaml:29-31` | removed (dead config; see section 8) |
| Signer libraries | declared, never imported | not declared |
| Live mode switch | `mode: live` + `--i-understand-the-risk` | effective mode `live` (R30 precedence) + the nine R21 preconditions; adapter is still a stub; refusal exits 3 |
| Engagement level (prose, `desk.md`, cron guard) | `research \| paper \| micro-live` (`ARCHITECTURE.md:173`, `README.md:18`, `SETUP.md:176,229`, `skills/desk-operating-model/SKILL.md:36`, `skills/desk-monitoring/SKILL.md:12`, `skills/pumpgrok-setup/SKILL.md:45`, enforced by `scripts/hermes-verify-isolation.sh:52-53`) | `research \| paper` only (R16). `micro-live` is retired everywhere in the Restructure phase; `live` is not an engagement level but a config mode behind the live gate. `desk_state.py status` `engagement` (parsed by `ENGAGEMENT_RE`, `tools/desk_state.py:35,68-72`, default `research`) and the `hermes-verify-isolation.sh` guard accept only the two values |

### 2.3 Seats and skills that touch paper-write

`agents/sniper.md` and `agents/exit.md` carry `writes_to_exchange: true`; `skills/desk-execution-protocol` and
`skills/jupiter-routing` describe the send procedure today. After migration these resolve ONLY the paper-write
tools `exec.place` (side `buy` for SNIPER, side `sell` for EXIT) and `exec.cancel` from
`contracts/tool-rosters/{sniper,exit}.yaml` (`kind: write`, `gates: [g6]`), backed by `PaperAdapter`.
`skills/jupiter-routing` becomes quote/route preparation that feeds `exec.quote` and `exec.place` (R18); the
single-send rule is implemented as PaperAdapter idempotency on `(ticket_id, side, decision_id)` (R23), not as
prose. Exit automation (R17): in paper mode the EXIT seat's rule engine (`engine/exits.py`) is the autonomous
paper-write path; under `autonomy_level=autonomous-paper` it is always on; under `manual-ticket` an exit rule
must be approved per ticket (`ApprovalRecord` kind `exit_rule`). No live auto-exit exists (`LiveGateError`).
No roster entry maps to `LiveAdapter` (D3 "NO seat can resolve a live-write tool");
`ci/gates/check_desk_integrity.py` fails if any roster tool name starts with `exec.live`.

### 2.4 Proof that no signer import path exists (and the gate that keeps it so)

Command: `rg -n "solders|from solana|import solana|import solders|base58|Keypair" vendor/grokbot-pumpfun/src vendor/grokbot-pumpfun/pyproject.toml vendor/grokbot-pumpfun/requirements.txt tools/`
Result: only `vendor/grokbot-pumpfun/pyproject.toml:17-18`, `requirements.txt:5-6` (declarations) and
`vendor/grokbot-pumpfun/src/executor.py:150` (a comment). Zero `import` statements. `tools/*.py` import only
`json, sys, os, re, argparse, statistics, pathlib, datetime, typing, requests` (scout-pumpgrok-code deps column).

Post-migration gate (new, owned by bot-02-risk): `ci/gates/check_desk_integrity.py` adds
`--forbid-imports solders,solana,base58,nacl` scanned over `src/`, `services/`, `tests/`, and `pyproject.toml`;
`tests/desk/test_no_signer_imports.py` asserts the same via `ast` walk. Both run in `run_all.py` (G-7).

### 2.5 Markdown-prose quarantine (instruction surfaces)

The files below contain live, micro-live, send or wallet prose. None of them is code; each is rewritten or
regenerated in the Restructure phase with the disposition shown. Row numbers refer to section 1.

| File:line | Prose | Disposition |
|---|---|---|
| `skills/jupiter-routing/SKILL.md:3` ("prepare a single-send transaction. Used only by SNIPER and EXIT"), `:9` ("Execute the single approved buy"), `:28` ("Submit once only"), `:29` ("do NOT retry") | send procedure | quarantine: paper-write procedure (row 54). Rewritten to quote/route preparation feeding `exec.quote` and `exec.place` (paper); single-send = PaperAdapter idempotency (R18, R23) |
| `skills/desk-execution-protocol/SKILL.md:3` ("before, during, and after every transaction. Enforces single-send"), `:23-24` | send procedure | quarantine: paper-write procedure (row 41); same retarget; "UNKNOWN RESULT - reconcile by signature" survives as the `exec.place` outcome `unknown_result` handled by the ledger, not by a retry |
| `skills/desk-incident-response/SKILL.md:9` ("reconcile by signature, never second send") | send procedure | keep; already states the no-retry rule, retargeted to the ledger reconcile view |
| `rules/README.md:20` ("Single-send + no-auto-retry"), `rules/pumpgrok-team.mdc:30` (single-send rule) | constitution | keep verbatim (D9, R7); enforced in code by R23 idempotency and `stop_after_attempt(1)` on the adapter (FOUNDATION_STACK section 1 row 6) |
| `rules/pumpgrok-team.mdc:46` ("Micro-live trading is only enabled after the user explicitly confirms the risk-limits interview and engagement level") | micro-live | CONTRADICTION with R16 ("micro-live retired everywhere") versus D2/R7 (`rules/pumpgrok-team.mdc` kept verbatim). Not resolved here; reported in the closing summary. Default assumed: the line is kept byte-for-byte and the code never implements the level, so it is unreachable prose |
| `skills/pumpgrok-setup/SKILL.md:45` ("Set engagement to micro-live during setup") vs `ARCHITECTURE.md:234` ("Do not raise engagement to micro-live in setup") | micro-live, pre-existing contradiction | both removed (R16); setup leaves engagement at `research`; `pumpgrok doctor` reports it |
| `skills/desk-operating-model/SKILL.md:36` ("micro-live - real throwaway capital only after explicit user confirmation"), `skills/desk-monitoring/SKILL.md:12`, `skills/desk-strategy-lab/SKILL.md:17`, `ARCHITECTURE.md:173`, `README.md:18`, `SETUP.md:176`, `SETUP.md:229` | micro-live engagement level | removed (R16); engagement levels are `research \| paper`; rows 7, 9, 10, 44, 45, 48 |
| `scripts/hermes-verify-isolation.sh:52-53` (`engagement:[[:space:]]*micro-live` -> `err "desk.md engagement is micro-live; cron state machine is research/paper only"`) | micro-live guard (the only executable mention) | rewritten to reject any engagement value other than `research` or `paper` (row 38); the check stays fail-closed |
| `agents/exit.md:41` ("unless the human has explicitly enabled emergency auto-exit in writing"), `:48` ("without either pre-authorised rules or fresh human confirmation"), `skills/position-monitoring/SKILL.md:25` ("unless auto-exit pre-authorised") | auto-exit pre-authorisation | replaced by R17: paper-mode exit rules are the autonomous paper-write path, always on under `autonomous-paper`, approved per ticket (`exit_rule`) under `manual-ticket`; no live auto-exit exists. Regenerated from `prompts/bot-06-exit.xml` (row 20); skill row 55 |
| `agents/sniper.md:54` ("On timeout or error -> do NOT retry ... wait for new human approval") | send procedure | keep the rule; regenerated from `prompts/bot-04-sniper.xml` (row 18); enforced by R23 |
| `skills/tool-connections/SKILL.md:17-22` (Wallet Connection Protocol: human creates throwaway wallet, screen hand-off, bot records the public address, never a seed or private key) and `skills/solana-rpc-and-wallet/SKILL.md:3,9-12` | wallet hand-off (no key material) | keep as the no-key procedure (rows 61, 62). In paper mode no wallet exists ("no key material exists in paper mode; nothing to custody", R40). The only stored wallet datum is the live-gate public-address allowlist (R21 precondition 5), set by env, never by a seat |
| `ARCHITECTURE.md:68,206,210` (human wallet, screen hand-off, "only the public address is recorded") | wallet hand-off | rewritten with the same restriction (row 7) |
| `skills/grokbot-pipeline/SKILL.md:99` ("Set `mode: live` or provide `solana.wallet_private_key` from the desk; the upstream stub must stay unimplemented") | live config | the setting no longer exists (M-10); sentence replaced by a pointer to the live gate (row 51) |
| `hermes/cron/prompts/rug-watch.md:15` ("alert only - EXIT does not act from cron") | cron isolation | keep; `forbidden_owners: [sniper, exit]` (`hermes/cron/jobs.yaml:79`) unchanged |
| `ARCHITECTURE.md:14,15,26,117,169,232`, `README.md:5,13,71`, `tools/README.md:4,14,21,22,51,70`, docstrings "Never signs or sends" | read-only statements | keep the statements; `tools/README.md` is deleted (row 65) and the sentence moves to `docs/TOOL_CATALOG.md` and the ported module docstrings (section 2.4) |

Result: no markdown surface describes a signing or sending procedure that survives migration; the three live-adjacent
families (micro-live engagement, auto-exit pre-authorisation, single-send procedure) are each mapped to a binding
resolution (R16, R17, R18/R23). One contradiction remains (`rules/pumpgrok-team.mdc:46`).

## 3. Vendor engine port plan

### 3.1 Module homes, strings, tests

| Vendor module | Lines | Cyrillic lines | New home | What becomes English | Test ports |
|---|---|---|---|---|---|
| `src/pipeline.py` | 569 | 104 | `src/pumpgrok/engine/pipeline.py` (+ CLI to `cli.py`) | all log calls, `_reject` reasons stay as ASCII codes (`checker_rejected`, `executor_not_implemented` -> `live_gate`), `LIVE_WARNING` dropped | adapt (37) |
| `src/executor.py` | 195 | 45 | `execution/curve_math.py`, `execution/paper_adapter.py` (+ `execution/fees.py`, `execution/latency.py`), `execution/live/live_adapter.py` (R31) | `error="price unknown at entry"` replaces the Russian error text (`executor.py` DryRun buy); docstrings | new `test_executor.py` + subset of `test_pipeline.py` |
| `src/models.py` | 624 | 114 | `engine/models.py` (26-270) + `config/settings.py` (271-624) | field docstrings; `Config.problems` messages (`models.py:573,575`) | `test_config.py` adapt (20); domain 1:1 |
| `src/risk.py` | 382 | 68 | `risk/engine.py` (`RiskEngine`), `risk/sizing.py`, `engine/exits.py`, `engine/watcher.py` (R31) | log strings; `EXIT_REASONS` codes unchanged (plus `graduated`, `blind_flatten`, `kill_flatten`, `manual` added by the ledger reason enum, R32) | 1:1 (36) except the halt auto-clear cases (row 114) |
| `src/ops.py` | 443 | 51 | `core/ratelimit.py`, `core/budget.py`, `core/llm.py`, `risk/breakers.py`, `supervisor/lifecycle.py` (+ `supervisor/{metrics,health}.py` rewrite subset) | log strings | 1:1 except HealthServer (24) |
| `src/monitor.py` | 258 | 32 | `engine/monitor.py` | log strings; skip reasons already ASCII (`no_metadata, curve_too_full, too_young, few_buyers`) | 1:1 (21, from `test_filter.py`) |
| `src/analyzer.py` | 316 | 38 | `engine/analyzer.py` | log strings; veto reasons already ASCII | 1:1 (16) |
| `src/scoring.py` | 79 | 13 | `engine/scoring.py` | docstrings | 1:1 (13) |
| `src/state.py` | 104 | 21 | `ledger/snapshots.py` | n/a (rewrite) | adapt (16) |
| `src/log.py` | 213 | 21 | `ledger/journal.py` | n/a (rewrite) | adapt (8) |
| `src/reputation.py` | 171 | 27 | `engine/reputation.py` | log strings | 1:1 (18) |
| `src/alerts.py` | 136 | 27 | `tools/notify/webhook.py` | n/a (rewrite) | adapt (19) |
| `src/agents/base.py` | 274 | 46 | `engine/agents/base.py` | log strings, `GrokAgentError` messages | 1:1 (21 across agents) |
| `src/agents/auditor.py` | 93 | 24 | `engine/agents/auditor.py` | prompt text if Russian (unverified, section 8) | 1:1 |
| `src/agents/checker.py` | 85 | 27 | `engine/agents/checker.py` | same | 1:1 |
| `src/agents/narrative.py` | 69 | 19 | `engine/agents/narrative.py` | same | 1:1 |
| `src/agents/timing.py` | 101 | 26 | `engine/agents/timing.py` | same | 1:1 |
| `src/__init__.py`, `src/agents/__init__.py` | 3, 16 | 1, 1 | `engine/__init__.py`, `engine/agents/__init__.py` | docstring | n/a |
| `scripts/dashboard.py` | 126 | 14 | `reporting/dashboard.py` | CLI output | none exists |
| `scripts/replay.py` | 168 | 35 | `reporting/summary.py` | CLI output | none exists |
| `scripts/tune.py` | 234 | 53 | `engine/tune.py` | CLI help and prints | 1:1 (15) |

Totals: 264 vendor tests (sum of per-file counts above: 21+19+16+20+21+8+24+37+18+36+13+16+15 = 264);
1:1 ports = 21+16+21+24+18+36+13+15 = 164 (62 percent); adapted = 19+20+8+37+16 = 100.

### 3.2 Seat ownership of ported modules (ownership.yaml patterns, last match wins)

Allocation per R31 and R36; `ownership.yaml` (bot-02-risk) and `docs/ROSTER.md` section 7 hold the full rule list.

| Pattern | Owner |
|---|---|
| `src/pumpgrok/engine/**` | bot-08-signal (scoring, checker, agents, pipeline, tune) |
| `src/pumpgrok/engine/monitor.py`, `src/pumpgrok/engine/analyzer.py` | bot-01-scout |
| `src/pumpgrok/engine/reputation.py`, `src/pumpgrok/engine/watcher.py` | bot-05-rug |
| `src/pumpgrok/engine/exits.py` | bot-06-exit |
| `src/pumpgrok/core/**`, `src/pumpgrok/replay/**`, `src/pumpgrok/ledger/**`, `src/pumpgrok/config/**`, `src/pumpgrok/logging/**`, `src/pumpgrok/risk/**` | bot-02-risk (infrastructure owner, R36) |
| `src/pumpgrok/execution/**` | bot-04-sniper (`paper_adapter.py`, `curve_math.py`, `fees.py`, `latency.py`) |
| `src/pumpgrok/execution/live/**` (rule placed AFTER `execution/**`) | bot-02-risk (R31) |
| `src/pumpgrok/reporting/**` | bot-09-journal |
| `src/pumpgrok/supervisor/**`, `src/pumpgrok/cli.py` | bot-00-chief |
| `src/pumpgrok/tools/notify/**` | bot-00-chief |
| `src/pumpgrok/tools/onchain/**` (directory owner incl. `rpc.py`, `authorities.py`; `docs/ROSTER.md:709-710`) | bot-05-rug; `tools/onchain/holders.py` and `transfers.py` -> bot-03-whale by a later rule (`ROSTER.md:711-712`) |
| `src/pumpgrok/tools/market/**` | bot-01-scout |
| `src/pumpgrok/tools/safety/**` | bot-05-rug |
| `src/pumpgrok/tools/social/**` (approved D2 addition, read-only, R31) | bot-07-shill |
| `tests/characterization/test_<module>.py` | the owner of the module it pins (R36) |
| `agents/*.md`, `prompts-assembled/*` (generated) | bot-00-chief |

### 3.3 Tests that assert Russian text (must be adapted, not 1:1)

Known from the scout: `test_config.py` checks validation error strings produced by `Config.problems`
(`models.py:573,575`); `test_pipeline.py` live-gating tests match `SystemExit` text (`pipeline.py:540`).
Exact test function names were not enumerated (section 8). Rule: a ported test may only assert on ASCII reason
codes, never on free-text messages.

### 3.4 Retirement criterion for `vendor/grokbot-pumpfun/`

Delete the directory when ALL of the following return zero or are retargeted:

1. `rg -l -F "vendor/grokbot-pumpfun" . --glob '!vendor/**' --glob '!*.pyc'` -> today: ARCHITECTURE.md, README.md,
   SETUP.md, `scripts/check.sh:118-119`, `skills/grokbot-pipeline/SKILL.md`, `tools/pipeline_evidence.py`
   (DEFAULT_LOG), `hermes/README.md`, `hermes/cron/prompts/scout-pipeline.md` (`rg -l -F logs/trades.jsonl .`).
2. `rg -l -F "src.pipeline" . --glob '!vendor/**'` -> today: `skills/grokbot-pipeline/SKILL.md`.
3. `rg -l -F 409e74c . --glob '!vendor/**'` -> today: ARCHITECTURE.md, README.md, SETUP.md, skills/grokbot-pipeline/SKILL.md;
   after the move the ONLY allowed hit is `docs/VENDOR_PIN.md` (row 86).
4. `tests/characterization/` contains all 13 ported modules and `uv run pytest -q tests/characterization` passes.
5. `scripts/check.sh` no longer lists vendor paths and the emoji scan no longer excludes `vendor/` (`check.sh:142`).
6. `src/pumpgrok/engine/LICENSE-grokbot-pumpfun` exists (row 84).

## 4. Instruction-pack mapping

### 4.1 agents -> prompts (generated back)

| agents/ file | Prompt source | Assembled | Generated back | Channel (D3) |
|---|---|---|---|---|
| `agents/chief.md` | `prompts/bot-00-chief.xml` | `prompts-assembled/CHIEF.xml` | `agents/chief.md` | Trading Floor |
| `agents/scout.md` | `prompts/bot-01-scout.xml` | `prompts-assembled/SCOUT.xml` | `agents/scout.md` | Trading Floor |
| `agents/risk.md` | `prompts/bot-02-risk.xml` | `prompts-assembled/RISK.xml` | `agents/risk.md` | Trading Floor |
| `agents/whale.md` | `prompts/bot-03-whale.xml` | `prompts-assembled/WHALE.xml` | `agents/whale.md` | Trading Floor |
| `agents/sniper.md` | `prompts/bot-04-sniper.xml` | `prompts-assembled/SNIPER.xml` | `agents/sniper.md` | Trading Floor |
| `agents/rug.md` | `prompts/bot-05-rug.xml` | `prompts-assembled/RUG.xml` | `agents/rug.md` | Trading Floor |
| `agents/exit.md` | `prompts/bot-06-exit.xml` | `prompts-assembled/EXIT.xml` | `agents/exit.md` | DM |
| `agents/shill.md` | `prompts/bot-07-shill.xml` | `prompts-assembled/SHILL.xml` | `agents/shill.md` | DM |
| (new) | `prompts/bot-08-signal.xml` | `prompts-assembled/SIGNAL.xml` | `agents/signal.md` | DM |
| (new) | `prompts/bot-09-journal.xml` | `prompts-assembled/JOURNAL.xml` | `agents/journal.md` | DM |

The 10-clause Security Constitution block that every agent file repeats verbatim (scout-pumpgrok-pack) moves ONCE
into `prompts/_shared/core-directives.xml` and is re-emitted into every generated `agents/*.md` so that
`scripts/check.sh` phrase spot-check (constitution phrases, scout-pumpgrok-pack check list item 10) keeps passing.

### 4.2 Skills: kept name, proposed frontmatter, seat owner

[INFERENCE] values; `docs/ROSTER.md` and `ownership.yaml` are authoritative. Gate ids are the programming-desk G-1..G-7.

| Skill (name unchanged) | bots | gates | owner |
|---|---|---|---|
| browser-ops | [bot-07-shill, bot-01-scout] | [] | bot-07-shill |
| desk-execution-protocol | [bot-04-sniper, bot-06-exit] | [G-2, G-6] | bot-04-sniper |
| desk-folders-and-journal | [bot-00-chief, bot-09-journal] | [G-2] | bot-09-journal |
| desk-incident-response | [all] | [G-2, G-5] | bot-02-risk |
| desk-monitoring | [bot-00-chief, bot-05-rug] | [] | bot-05-rug |
| desk-operating-model | [all] | [G-1, G-2] | bot-00-chief |
| desk-post-trade-review | [bot-09-journal, bot-06-exit, bot-00-chief] | [G-2] | bot-09-journal |
| desk-risk-limits | [bot-02-risk, bot-00-chief] | [G-4, G-6] | bot-02-risk |
| desk-strategy-lab | [bot-08-signal, bot-04-sniper, bot-06-exit] | [G-2] | bot-08-signal |
| desk-trade-lifecycle | [all] | [G-2] | bot-00-chief |
| discovery-tools | [bot-01-scout, bot-03-whale, bot-07-shill] | [] | bot-01-scout |
| grokbot-pipeline | [all] | [G-2] | bot-08-signal |
| hermes-cron-desk | [bot-00-chief, bot-01-scout, bot-02-risk, bot-05-rug] | [G-7] | bot-00-chief |
| holder-and-flow-analysis | [bot-03-whale, bot-02-risk] | [] | bot-03-whale |
| jupiter-routing | [bot-04-sniper, bot-06-exit] | [G-6] | bot-04-sniper |
| position-monitoring | [bot-05-rug, bot-06-exit] | [] | bot-05-rug |
| pumpgrok-setup | [all] | [G-7] | bot-00-chief |
| risk-audit | [bot-02-risk] | [G-2] | bot-02-risk |
| social-sentiment | [bot-07-shill, bot-01-scout] | [] | bot-07-shill |
| solana-api-reference | [bot-04-sniper, bot-02-risk] | [] | bot-02-risk |
| solana-market-data | [bot-01-scout, bot-02-risk, bot-03-whale, bot-04-sniper, bot-05-rug, bot-08-signal] | [] | bot-01-scout |
| solana-rpc-and-wallet | [bot-02-risk, bot-04-sniper] | [G-3] | bot-02-risk |
| tool-connections | [bot-00-chief] | [G-3] | bot-00-chief |

This resolves the three-way drift (agent frontmatter vs `hermes/profiles.yaml` vs `hermes-bootstrap.sh:skills_for`):
the prompt XML `<skills>` list is the single source; `generate-templates.py` emits agent frontmatter, and
`hermes-bootstrap.sh` reads `hermes/profiles.yaml`, which is regenerated from the same list.

### 4.3 Hermes cron prompts -> `pumpgrok` CLI subcommands

| Job (`hermes/cron/jobs.yaml`) | Prompt | Wraps | Silent rule |
|---|---|---|---|
| `scout-discover` (`:12-21`) | `scout-discover.md` | `pumpgrok scout discover --max-leads 5` | CLI returns `{"silent": true, "reason": "halt|engagement"}`; prompt prints `[SILENT]` |
| `scout-pipeline` (`:68-77`) | `scout-pipeline.md` | `pumpgrok scout pipeline --candidates --limit 5` | same |
| `risk-audit-open-leads` (`:23-32`) | `risk-audit.md` | `pumpgrok risk audit --pending` | same |
| `chief-pickup` (`:34-43`) | `chief-pickup.md` | `pumpgrok chief pickup` | same; halt text `FLOOR HALTED - DAILY LOSS LIMIT` comes from the ledger halt event, not from `desk.md` |
| `rug-watch-paper` (`:45-55`) | `rug-watch.md` | `pumpgrok rug watch` | `require_open_positions` evaluated by the CLI |
| `chief-journal-rollup` (`:57-66`) | `chief-journal.md` | `pumpgrok journal rollup --daily` | heartbeat line always emitted |

Shared pre-flight in every prompt (`desk_state.py status`) becomes `pumpgrok state status`. `forbidden_owners`
and `forbidden_actions` stay in `jobs.yaml`; the CLI enforces them too (`sniper`/`exit` verbs are not exposed as
cron-callable subcommands; `pumpgrok paper buy|sell --ticket <SOL-YYYYMMDD-NNN> --mint <mint> --size-sol <sol>
--slippage-bps <bps> --approval-id <id>` (R40) requires a ticket in state `APPROVED` whose `ApprovalRecord`
(kind `human_buy` / `human_sell`, R33) carries the exact human approval phrase, D9; the approval is consumed
inside the same ledger transaction as the order, R23).

### 4.4 rules, manifests, SETUP, ARCHITECTURE

| Item | Action |
|---|---|
| `rules/pumpgrok-team.mdc` | kept verbatim (D2, D9); referenced by `scripts/check.sh:111` |
| `plugin.json`, `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `.grok-plugin/plugin.json` | `"license": "MIT"` -> `"AGPL-3.0"`; add `skills/agents/rules` paths to the claude manifest; keywords aligned; description "23 skills" kept while true |
| `plugin.json`, `.claude-plugin/marketplace.json`, `.grok-plugin/marketplace.json` | `your-org` -> real org (value unknown, section 8) |
| `SETUP.md` | -> `docs/runbooks/setup.md`; README gets the 5-command quick start (`uv sync`, `cp .env.example .env`, `uv run pumpgrok doctor`, `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke`, `./scripts/check.sh`) |
| `ARCHITECTURE.md` | rewritten around `src/pumpgrok/` packages, ledger, supervisor, gates |

### 4.5 `/workspace/trading-desk` file bus -> ledger-backed exports

| Old artefact (`tools/desk_state.py DESK_CHILDREN`, scout-pumpgrok-code) | Ledger entity (event types per R32; `contracts/events/<snake_case>.schema.json`) | CLI |
|---|---|---|
| `leads/<id>.md` | `JournalNote` with payload `note_kind: signal` (schema `contracts/events/journal_note.schema.json`; the signal kind literal is `signal`, R40) | `pumpgrok scout discover`, `pumpgrok ticket list --state LEAD` |
| `briefs/<id>.md` (`Verdict: CLEAR\|CONDITIONAL\|KILL\|BLIND`) | `JournalNote` with `note_kind: safety_report` / `verdict`; RUG red flags are `Escalation` events | `pumpgrok risk audit` |
| `proposals/<id>.md` (`Status:`) | `tickets` view over `ApprovalRecorded` events (`SOL-YYYYMMDD-NNN`, sequence-allocated in `ledger/tickets.py`) | `pumpgrok ticket next\|create\|list` (from `tools/ticket_helper.py`) |
| `positions/`, `watch/` | `positions` snapshot + `OrderPlaced` / `OrderRejected` / `FillRecorded` / `PositionOpened` / `PositionClosed` / `MarkToMarket` | `pumpgrok paper buy\|sell` (from `tools/paper_sim.py`), `pumpgrok rug watch` |
| `incidents/` | `Escalation` and `HaltSet` / `BreakerTripped` / `KillSwitchSet` | `pumpgrok state halt --reason <text>`, `pumpgrok killswitch set` |
| `journal/paper-YYYY-MM-DD.md` | JSONL export `var/journal/YYYY-MM-DD.jsonl` + markdown render (tmp file + `os.replace`, R26) | `pumpgrok journal rollup`, `pumpgrok report --daily\|--weekly` |
| `desk.md` (`Engagement:`, `Halt:`) | reducer view (`mode`, `engagement` in `research\|paper`, `halt`, `halt_reason`) + `var/desk/KILLSWITCH` file | `pumpgrok state status`, `pumpgrok state halt --reason` / `--clear --by <human> --reason <text>` (human only, R22), `pumpgrok killswitch set\|status`, `pumpgrok killswitch clear --by <human> --reason <text>` (CLI only, R22) |
| `risk-limits.md` | settings overlay `[risk]` block with the R20 keys (`max_trade_fraction`, `max_token_fraction`, `daily_loss_halt_fraction`, `drawdown_halt_fraction`, `max_open_positions`, `max_trades_per_day`, `liquidity_floor_multiple`, `partial_fill_fraction`, `paper_equity_sol`; all REVIEW) + `docs/RISK_POLICY.md` | `pumpgrok audit` |

Markdown renders of these views may still be written under `var/desk/` for Hermes profiles whose `terminal.cwd`
is the desk (hermes/profiles.yaml `desk_env`), but they are derived, never read back.

## 5. No-precedent placements (documented deviations)

| Path | programming-desk precedent | Why pumpgrok needs it | Owner |
|---|---|---|---|
| `src/pumpgrok/ledger/` | none; programming-desk persists only JSON receipts (`ls /root/src/repos/programming-desk/src/desk` -> security session supervision telemetry diagnostics recovery assertions, no persistence package) | D5 sqlite WAL append-only events + snapshots is the paper-trading source of truth (positions, PnL, tickets, halt); the 5 percent daily-loss floor (D9) must be computed from it | bot-02-risk (infrastructure owner, R36; bot-09-journal owns `reporting/`) |
| `tests/fixtures/replay/<dataset>/*.jsonl` | none (`ls /root/src/repos/programming-desk/tests/fixtures` -> No such file) | recorded PumpPortal WS + pump.fun REST + Jupiter quote fixtures let `pumpgrok run --once --replay` and the characterization tests run without network (vendor tests already mock everything via `httpx.MockTransport`/`FakeWebSocket`; fixtures make the mocks data-driven) | bot-01-scout (datasets), bot-02-risk (gate that the smoke set exists) |
| `var/` | none (`ls /root/src/repos/programming-desk/var` -> No such file); programming-desk `.gitignore` ignores only `.receipts/**/*.json` and build dirs | runtime state (`ledger.sqlite`, `snapshots/`, `journal/`, `KILLSWITCH`, `health`) must be outside the package and gitignored; vendor used `logs/` + `state/` (vendor `.gitignore`) | bot-00-chief |
| `docs/runbooks/` | programming-desk keeps runbooks flat (`docs/intake-e2e-runbook.md`) | vendor `RUNBOOK.md` + `SETUP.md` + hermes install + incident playbooks are four runbooks; a subdirectory keeps `docs/` readable | bot-02-risk (docs owner, QUALITY analogue) |
| `contracts/events/*.schema.json` | directory exists with a README only (`ls /root/src/repos/programming-desk/contracts/events` -> README.md 889B) | pumpgrok's cross-seat surfaces are the ledger event types (one schema per R32 type, snake_case file names; seat messages travel as `journal_note` payloads); JSON Schema files make G-4 `contract_surface` checks meaningful | bot-02-risk |
| `src/pumpgrok/tools/social/` | not in the D2 subpackage list (market, onchain, safety, exec, portfolio, risk, notify, journal) | SHILL's read-only sentiment ingestion needs its own namespace; approved D2 addition (R31), read-only, inside the no-manipulation static test scope | bot-07-shill |

Each deviation is recorded in `docs/DISCOVERY.md` section "Deviations" by reference to this table.

## 6. Dependency drift that gates a move

Full inventory: `docs/DISCOVERY.md` section 5. Only move-gating package actions are listed here.

| Package | Vendor spec | Installed here (`python3 -c "import X; print(X.__version__)"`) | Action | Gates batch |
|---|---|---|---|---|
| websockets | `>=12.0` (`vendor/grokbot-pumpfun/pyproject.toml:14`) | 16.0 | pin `websockets>=14,<18`; in `engine/monitor.py` import `from websockets.asyncio.client import connect` instead of `websockets.connect` (`monitor.py:23,218`); ported test `patch_socket` (`test_filter.py:281`) patches `monitor_module.connect` | 2 |
| httpx | `>=0.27` (`:15`) | 0.28.1 | pin `httpx>=0.28,<1`; no code change (vendor constructs `AsyncClient(timeout=..., base_url=..., transport=...)` only, `rg -n "AsyncClient\(" vendor/grokbot-pumpfun/src` - none use the removed `proxies`/`app` kwargs); add `respx` dev dep for the rewritten tools | 2 |
| pydantic | `>=2.6` (`:16`) | 2.13.4 | pin `pydantic>=2.11,<3`; add `pydantic-settings>=2.6` (new; config rewrite row 109) | 1 |
| requests | undeclared, used by 4 tools (`tools/*.py:17-19`) | n/a | not a dependency; tools rewritten to httpx | 2 |
| solders, solana | `>=0.21`, `>=0.34` (`:17-18`), never imported | n/a | not declared (section 2.4) | 1 (pyproject) |
| pyyaml | `>=6.0` (`:19`) for `config.yaml` | n/a | config moves to TOML (`tomllib`, stdlib); `pyyaml` stays ONLY as a dev/gates dependency for `ownership.yaml` (`programming-desk: pip install pyyaml pytest`) | 1 |
| pytest-asyncio | `>=0.23`, `asyncio_mode = "auto"` (`:42`) | n/a | keep `asyncio_mode = "auto"` in root `pyproject.toml` or every ported async test needs a marker | 1 |
| tenacity, prometheus_client | new (D5) | n/a | `tenacity` adopted in the shared RPC client `tools/onchain/rpc.py` (batch 2) with `sleep=clock.sleep` (R27); `prometheus_client` in `supervisor/metrics.py` (batch 5); `agents/base.py` keeps its own `_backoff` until its 1:1 tests are green (batch 2), then may switch under its own test | 2, 5 |
| python | `>=3.11` (`:10`), CI matrix 3.11-3.13 | 3.12.3 | `requires-python = ">=3.12,<3.13"` (D1) | 1 |

## 7. Move order in runnable checkpoints (GSD Phases 1-5, re-cut per R37)

Five batches, one per GSD phase. The CHECKPOINT_RULE holds from batch 1 with no waiver: after every batch, on a
clean tree, all tests pass, `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0,
and `uv run pumpgrok doctor` runs. Until batch 5 completes, the vendor tree stays and
`cd vendor/grokbot-pumpfun && python3 -m pytest -q` must ALSO still pass (it is the oracle for the characterization
tests). `./scripts/check.sh` is the rewritten version from batch 1 onward.

Checkpoint semantics that make batches 1-3 runnable (F-M13, F-M14, F-M15):

- `pumpgrok run --mode paper --once --replay <dataset>` from batch 1 executes a SKIP-ONLY cycle: the fixture
  events are read through `replay/fixtures.py`, no engine runs, one `JournalNote` (`note_kind: cycle`, `decision:
  skip`, `reason: engine_not_yet_implemented`) is appended to `var/replay/<dataset>/ledger.sqlite` through
  `ledger/store.py`, and the process exits 0. From batch 2 the engine runs and the cycle may produce a `buy`
  decision, but with no `PaperAdapter` yet the decision is recorded as `skip` with reason
  `execution_not_yet_implemented` (still exit 0). From batch 4 the decision reaches `PaperAdapter` and a fill is
  recorded.
- `pumpgrok doctor` reports every subsystem it can see (effective config with source per field, data-source
  reachability, ledger, kill switch, live gate, gateway) and marks each absent one `not-yet-implemented`. An absent
  subsystem is a WARNING until the batch that owns it has landed, after which it is a FAILURE (exit 1). The
  owning batch per subsystem is the table below; `doctor` reads that mapping from a constant in `cli.py` that
  the batch PR updates.
- Every module named in `docs/design/interfaces.md` section 1 and in `docs/design/paper-engine.md` sections 0-6
  (plus the R31 placements) has exactly ONE home batch, section 7.1. A later batch may extend a module under its
  existing tests (for example `risk/breakers.py` gains the three risk breakers in batch 4) but never introduces it.

| Batch (phase) | Scope (rows and modules) | Must pass after the batch |
|---|---|---|
| 1 Foundation | `pyproject.toml` + `uv.lock` + `Makefile` + `.pre-commit-config.yaml` (row 92, 85), `.gitignore` (82), `.env.example` (80), `.github/workflows/{ci,gates}.yml` (81), delete tracked `*.pyc` (63, 66-70) and `issues/tissue.json` (31), `tests/conftest.py` (90), `scripts/check.sh` rewrite (35), `ci/gates/*` ported (G-1..G-7 incl. the R19 `TOOL_NAME_RE`/`SEAT_RE` and R36 every-path-owned self-test) + `ownership.yaml` + `.receipts/<seat>/.gitkeep`, `docs/VENDOR_PIN.md` (86); `src/pumpgrok/config/{settings.py,overlays/{dev,paper,live}.toml}` (row 109 config half: R30 precedence, R20 `[risk]` keys, R21 `live.*` field validation); `src/pumpgrok/logging/json.py`; `src/pumpgrok/core/{side_effect,errors,correlation,idempotency,tool,datasource,adapter,skill,bot,registry,__init__,interfaces,ids,approvals,atomic_write}.py`; `src/pumpgrok/ledger/{store,events}.py` (schema, `BEGIN IMMEDIATE` append, hash chain, the 18 R32 types); `src/pumpgrok/replay/{clock,rng,fixtures}.py`; `src/pumpgrok/cli.py` skeleton (`run --mode paper --once --replay`, `doctor`, `--version`); `tests/fixtures/replay/smoke/` hand-written minimal dataset (one `create` event, one trade tick); `tests/{core,config,ledger,replay}/` unit tests, `tests/desk/test_cli.py` (64), `tests/safety/test_no_ambient_randomness.py`, `test_no_wall_clock.py`, `test_no_signer_imports.py` (static tests, R27/R29) | `uv sync --frozen` ; `uv run ruff check .` ; `uv run mypy src/` ; `uv run pytest -q` ; `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` (exit 0; one `JournalNote` with `decision: skip`, `reason: engine_not_yet_implemented` in `var/replay/smoke/ledger.sqlite`) ; `uv run pumpgrok doctor` (exit 0; config, ledger, kill-switch file present; engine/tools/execution/supervisor/gateway reported `not-yet-implemented` as warnings) ; `./scripts/check.sh` ; `python3 ci/gates/check_ownership.py --validate-manifest` ; `python3 -m pytest ci/tests/ -q` |
| 2 Restructure | shared RPC client `src/pumpgrok/tools/onchain/rpc.py` (httpx + tenacity `sleep=clock.sleep` + failover list, D8, R27) and the four ported root tools `tools/onchain/{authorities,holders,priority_fee}.py`, `tools/market/jupiter.py` (71, 73, 74, 77); data sources `tools/market/{pumpfun,pumpportal}.py`; `tools/notify/{base,stdout,file,webhook}.py` (105); `src/pumpgrok/replay/{recorder,sources}.py` and the recorded `tests/fixtures/replay/smoke/` dataset (replaces the hand-written one; `pumpgrok run --mode paper --record smoke --duration 600`); engine port rows 97-104, 106, 110, 112, 113, 115 (`engine/{__init__,pipeline,monitor,analyzer,scoring,reputation,tune,models}.py`, `engine/agents/*`), `src/pumpgrok/core/{ratelimit,budget,llm}.py` and `src/pumpgrok/risk/breakers.py` (verbatim `CircuitBreaker` port; row 111 split), `src/pumpgrok/engine/{exits,watcher}.py` (row 114 exit half), English strings (section 3.1); instruction-pack regeneration: `prompts/` + `scripts/assemble-prompts.sh` + `scripts/generate-templates.py` (rows 13-21), hermes prompt rewrites (24-29), `hermes-bootstrap.sh`/`hermes-install-cron.sh`/`hermes-verify-isolation.sh` rewrites (36-38), `README.md`/`ARCHITECTURE.md`/`docs/runbooks/setup.md` (7, 9, 10), manifests (1-6, 12), micro-live and auto-exit prose retired (section 2.5); `tests/characterization/test_{authority_check,holder_check,jupiter_quote,priority_fee,agents,analyzer,monitor,reputation,scoring,tune,pipeline}.py` and the exit/watcher half of `test_risk.py`; old `tools/*.py` remain until batch 5 | `uv run pytest -q` (characterization 1:1 tests green: 21+16+21+18+13+15 plus the exit-rule subset of 36) ; `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` (exit 0; engine runs; decision `buy` or `skip` from fixtures, recorded as `skip` with reason `execution_not_yet_implemented` when `buy`) ; `uv run pumpgrok doctor` (tools and engine present; execution/supervisor/gateway still warnings) ; `uv run pumpgrok tools exec.quote --help` ; `bash scripts/assemble-prompts.sh --check` ; `python3 scripts/generate-templates.py --check` ; `./scripts/check.sh` ; `./scripts/hermes-verify-isolation.sh --desk "$HOME/trading-desk"` |
| 3 Tools and Skills | complete tool catalog per `docs/TOOL_CATALOG.md` (`tools/market/{price,liquidity,trades}.py`, `tools/onchain/{lp,metadata,deployer,transfers}.py`, `tools/safety/score_report.py`, `tools/portfolio/*`, `tools/risk/*` read tools, `tools/notify/{alert,telegram}.py` with the R39 destination allowlist, `tools/journal/*`, `tools/social/*`, `desk.*` core eight); registry least-privilege enforcement (`core/registry.py` grant audit wired to `contracts/tool-rosters/*.yaml`, `tests/desk/test_registry_least_privilege.py`, `test_no_manipulation_tools.py`); the 10 roster YAMLs (`contracts/tool-rosters/{_core,chief,scout,risk,whale,sniper,rug,exit,shill,signal,journal}.yaml`, dotted names, 8-15 tools each, R19/R35); `contracts/events/*.schema.json` (18, R32); skills frontmatter upgrade (rows 39-62) and the 12 new skills; `services/desk-gateway/` thin per-seat wrapper; G-7 port runs against the real rosters | `uv run pytest -q` ; `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` (unchanged semantics from batch 2: no `PaperAdapter` yet, buys recorded as `skip` with reason `execution_not_yet_implemented`) ; `uv run pumpgrok doctor` (tools, registry, rosters, gateway present) ; `python3 ci/gates/check_desk_integrity.py --repo .` (10 rosters, 8-15 tools each, no `exec.live*`) ; `./scripts/check.sh` ; `python3 ci/gates/run_all.py --bot bot-02-risk --base origin/main --receipt .receipts/bot-02-risk/phase-3.json` |
| 4 Paper and Autonomy | `src/pumpgrok/execution/{__init__,paper_adapter,curve_math,fees,latency,quote}.py` (rows 75, 107), `src/pumpgrok/execution/live/{live_adapter,live_gate}.py` (R21 nine preconditions, exit 3); `src/pumpgrok/risk/{engine,limits,sizing,killswitch}.py` (row 114 risk half; `breakers.py` gains the three risk breakers with hysteresis; R22, R24, R34); `src/pumpgrok/ledger/{reducer,views,reconcile,export,desk_bus,snapshots,journal,tickets}.py` (rows 78, 108, 116); `src/pumpgrok/supervisor/{scheduler,seat_task,health,lifecycle,escalation}.py` (row 111 remainder; `/healthz` + `/readyz`; `/metrics` arrives in batch 5); `src/pumpgrok/replay/runner.py` (determinism harness, `pumpgrok verify --fixture`); `src/pumpgrok/reporting/{dashboard,summary,evidence,render}.py` (rows 76, 95, 96; `str.format`, R9); CLI verbs `paper buy\|sell`, `state halt --clear`, `state autonomy`, `killswitch set\|clear\|status`, `live confirm`, `replay trim\|rebuild-ticks`, `verify`, `report`, `journal rollup`, `ticket next\|create\|list`, seat verbs (section 4.3); `tests/characterization/test_{executor,log,state,paper_sim,ticket_helper,pipeline_evidence,desk_state,ops}.py` and the risk half of `test_risk.py`; `tests/desk/test_live_gate_fails_fast.py`, `test_kill_switch_one_cycle.py`, `test_breaker_trip_and_cooldown.py`, `test_replay_determinism.py`, `test_ledger_restart_reconcile.py`, `test_paper_fill_model.py`, `test_supervisor_bounded_restart.py` | `uv run pytest -q` ; `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` (one `OrderPlaced` + `FillRecorded` + `PositionOpened` in `var/replay/smoke/ledger.sqlite`; `pumpgrok report --daily` renders the fill) ; `uv run pumpgrok verify --fixture smoke` (two runs, identical hash chain) ; `uv run pumpgrok run --mode live --once` (exits 3 printing all unmet R21 preconditions, at least precondition 8) ; `uv run pumpgrok doctor` (execution, risk, ledger views, supervisor present; metrics still a warning) ; `./scripts/check.sh` ; `python3 ci/gates/run_all.py --bot bot-04-sniper --base origin/main --receipt .receipts/bot-04-sniper/phase-4.json` |
| 5 Hardening | `src/pumpgrok/supervisor/metrics.py` (`prometheus_client`, `/metrics`) and spans (`logging/spans.py`); `docs/runbooks/{engine,hermes,incidents}.md` (row 88); fault-injection tests `tests/safety/test_fault_injection.py` (RPC down, WS down, LLM down, persistence down, clock skew), `tests/safety/test_soak.py` (three virtual days on a recorded dataset); `.github/workflows/security-pr.yml` + `ci/security/` (gitleaks rules, bandit, semgrep, pip-audit via `uv export`, trivy); `Dockerfile`, `docker-compose.yml` (83, 91); delete `tools/` + `tools/README.md` (65, 71-78 old paths); delete `vendor/grokbot-pumpfun/` when section 3.4 returns zero (rows 79, 87, 93, 94 and the moved rows' sources) | `uv run pytest -q` (incl. `tests/safety/`) ; `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` ; `uv run pumpgrok doctor` (no `not-yet-implemented` left; exit 0) ; `./scripts/check.sh` ; `docker build .` ; `docker compose config` ; section 3.4 commands 1-3 return zero hits outside `docs/VENDOR_PIN.md` ; `python3 ci/gates/run_all.py --bot bot-02-risk --base origin/main --receipt .receipts/bot-02-risk/phase-5.json` |

### 7.1 Module-to-batch coverage (every design-named module exactly once)

Method: the module names were extracted from `docs/design/interfaces.md` section 1 (11 files) and from
`docs/design/paper-engine.md` sections 0-6 (`grep -oE` over backticked `<pkg>/<name>.py` paths plus the section 4
replay modules and the section 3 ledger modules named in R31/R32), deduplicated, and then renamed where R31 fixes a
different path (`core/rpc.py` -> `tools/onchain/rpc.py`; `execution/live_adapter.py` and `execution/live_gate.py`
-> `execution/live/`). The resulting set has 54 modules; the table assigns each to one batch, and the batch
rows above name the same modules. Two naming overlaps are recorded, not resolved: paper-engine section 10 and
R31 name `core/interfaces.py` as the re-export facade while interfaces.md section 1 puts the re-exports in
`core/__init__.py` (both listed; `core/interfaces.py` is a one-line facade over `core/__init__.py`), and
paper-engine section 4.4 still says `core/rpc.py`.

| Batch | Modules (54 design-named) |
|---|---|
| 1 | `core/side_effect.py`, `core/errors.py`, `core/correlation.py`, `core/idempotency.py`, `core/tool.py`, `core/datasource.py`, `core/adapter.py`, `core/skill.py`, `core/bot.py`, `core/registry.py`, `core/__init__.py`, `core/interfaces.py`, `core/ids.py`, `core/approvals.py`, `core/atomic_write.py`, `ledger/store.py`, `ledger/events.py`, `replay/clock.py`, `replay/rng.py`, `replay/fixtures.py`, `cli.py` (21) |
| 2 | `tools/onchain/rpc.py`, `core/ratelimit.py`, `core/budget.py`, `core/llm.py`, `risk/breakers.py`, `engine/monitor.py`, `engine/exits.py`, `engine/watcher.py`, `replay/recorder.py`, `replay/sources.py` (10) |
| 3 | none of the 54 (batch 3 adds the catalog tools under `tools/*` and the gateway, which the two design docs name by tool id, not by module path) (0) |
| 4 | `execution/paper_adapter.py`, `execution/curve_math.py`, `execution/fees.py`, `execution/latency.py`, `execution/quote.py`, `execution/live/live_adapter.py`, `execution/live/live_gate.py`, `risk/engine.py`, `risk/limits.py`, `risk/sizing.py`, `risk/killswitch.py`, `ledger/reducer.py`, `ledger/views.py`, `ledger/reconcile.py`, `ledger/export.py`, `ledger/desk_bus.py`, `replay/runner.py`, `supervisor/scheduler.py`, `supervisor/seat_task.py`, `supervisor/health.py`, `supervisor/lifecycle.py`, `supervisor/escalation.py` (22) |
| 5 | `supervisor/metrics.py` (1) |

21 + 10 + 0 + 22 + 1 = 54. Modules that the port adds beyond the design-named set (`config/settings.py`,
`logging/json.py`, `engine/{pipeline,analyzer,scoring,reputation,tune,models,__init__}.py`, `engine/agents/*`,
`ledger/{snapshots,journal,tickets}.py`, `reporting/*`, `tools/*`, `execution/__init__.py`) appear in exactly one
batch row above as well.

Rollback per batch: each batch is one PR on branch `bot-0N-<seat>/phase-N`; reverting the merge commit restores
the previous checkpoint because old paths are only deleted in batch 5.

## Unverified Items

| # | Unknown | Default assumed |
|---|---|---|
| 1 | Whether `websockets.connect` in 14+ is the asyncio client or a deprecated legacy alias (documented behaviour not checked against the installed 16.0 source) | Assume explicit `from websockets.asyncio.client import connect` is required; batch 2 verifies by running the ported `test_monitor.py` |
| 2 | (resolved by R30) Location of TOML overlays | In-package `src/pumpgrok/config/overlays/{dev,paper,live}.toml`, `PUMPGROK_PROFILE` selects, `PUMPGROK_CONFIG=<file>` is the only operator overlay; no root `config/` |
| 3 | Whether the Grok agent prompts (`auditor.py`, `narrative.py`, `timing.py`, `checker.py`) are Russian or English (only Cyrillic line counts were measured, 19-27 lines each) | Assume mixed; translate everything non-ASCII; `test_agents.py` "prompts demand bare JSON" test is expected to stay green because it checks for JSON wording |
| 4 | Exact vendor test functions that assert Russian message text (section 3.3) | Assume only `test_config.py` and `test_pipeline.py` live-gating tests; discovered at port time and rewritten to assert reason codes |
| 5 | Real organisation name/URL replacing `your-org` in 3 manifests and SETUP.md | Left as-is until the orchestrator supplies it; `check.sh` gains a `your-org` placeholder check that fails until fixed |
| 6 | Whether `tests/characterization/` should instead live under `tests/desk/` to mirror programming-desk exactly (programming-desk has no characterization dir) | Keep `tests/characterization/` as the assignment specifies; listed as a sixth deviation if `docs/DISCOVERY.md` wants it |
| 7 | Final seat ownership of ported modules (section 3.2) and skill `bots`/`gates` values (section 4.2) | Proposals above; `ownership.yaml` and `docs/ROSTER.md` are authoritative |
| 8 | (resolved by R3) Whether removing `JitoConfig` conflicts with D8 | Dead config, removed; recorded as FOUNDATION_STACK M-10. D8 covers venues and data sources only |
| 9 | `tests/fixtures/replay/smoke` content (which recorded events) | One `create` event, one maturing trade stream, one `/coins/{mint}` response, one Jupiter quote; enough for one decision per `--once` run |
| 10 | Whether `hermes/profiles.yaml` can be regenerated by `scripts/generate-templates.py` without breaking `hermes-bootstrap.sh` parsing | Assume yes; the file keeps its current top-level keys (`desk_env`, `isolation`, `profiles`) |
| 11 | Whether `rules/pumpgrok-team.mdc:46` ("Micro-live trading is only enabled after ...") may be edited under R16, given D2/R7 keep the file verbatim | Assume the line stays byte-for-byte and is unreachable prose (no code implements the level); reported in section 2.5 and the summary for the orchestrator |
| 12 | Whether `core/interfaces.py` (R31, paper-engine section 10) and `core/__init__.py` (interfaces.md section 1) are one module or two | Two files, `core/interfaces.py` a one-line re-export facade; both in batch 1 (section 7.1) |
