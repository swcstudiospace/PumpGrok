# DISCOVERY: both repos as they actually are

Tracker: SPE-17995 https://linear.app/swcstudio/issue/SPE-17995/n1-discover-both-repos-as-they-actually-are | Notion https://app.notion.com/p/3ffbc1a0c7ae813a926ce74afa4a8a82?pvs=204

Scope: evidence-only inventory of `pumpgrok` (the repo being modernised) and
`programming-desk` (the shape being mirrored). Every repository fact cites
`file:line` or the exact command run. Inferences are tagged `[INFERENCE]`.
Decisions (keep / move / rewrite) are deferred to `docs/MIGRATION_MAP.md` (n2);
foundation choices (column B) are deferred to `docs/FOUNDATION_STACK.md` (n5).
Canonical CLI names used below are the orchestrator-fixed set:
`pumpgrok run --mode paper [--once] [--replay <dir>]`, `pumpgrok doctor|audit|verify`,
`pumpgrok report --daily|--weekly`, `pumpgrok scout discover|pipeline`,
`pumpgrok risk audit`, `pumpgrok chief pickup`, `pumpgrok rug watch`,
`pumpgrok journal rollup`, `pumpgrok ticket next|create|list`,
`pumpgrok state status|halt`, `pumpgrok paper buy|sell`,
`pumpgrok killswitch set|clear|status`.

## 1. Repos located

| Item | pumpgrok | programming-desk |
|---|---|---|
| Path | `/root/src/repos/pumpgrok` | `/root/src/repos/programming-desk` |
| Branch | `feat/grokbot-desk-merge` | `bot-01-systems-backend/v8.3-workbench-traceability` |
| HEAD | `8f7ae72d490d96263241a303502eddd43e99f14d` 2026-10-20T08:46:41+00:00 "chore(tools): fail-closed exit codes, Jupiter lite-api URL, hermes sc..." | `9de3aa3ceb7255162282011fc8220283dd28dd00` 2026-10-09T13:48:40+00:00 "Merge remote-tracking branch 'origin/main' into bo..." |
| Remote | `origin https://github.com/swcstudiospace/PumpGrok.git` (fetch+push) | `origin https://github.com/swcstudiospace/programming-desk.git` |
| Relation to main | `git log --oneline main..HEAD \| wc -l` = 19 commits ahead | not measured (reference only) |
| Working tree | `git status --short \| wc -l` = 0 (the scout-reported uncommitted diff is now commit 8f7ae72) | n/a |

Commands: `git -C /root/src/repos/pumpgrok log -1 --format='%H %cI %s'`,
`git -C /root/src/repos/pumpgrok remote -v`, `git log --oneline main..HEAD | wc -l`,
`git -C /root/src/repos/programming-desk log -1 --format='%H %cI %s'`.

The 19 commits ahead of `main` (`git log --oneline main..HEAD`) are: 8f7ae72
(tools fail-closed), five "feat: ultrathink ship" commits (6db1728, c54ac75,
89b7cdc, 1ff1281, ef1d902), two "feat: Integrate Grokbot-Pumpfun into PumpGrok"
(48d03a9, 4bac3d2), and eleven Hermes isolation/cron commits (ed8397b .. 32bdd2d).

Last-modified dates (`git log -1 --format=%cI -- <path>`):

| Path | Last commit date |
|---|---|
| `agents/` | 2026-08-28T17:21:58+00:00 |
| `skills/` | 2026-10-20T08:46:41+00:00 |
| `tools/` | 2026-10-20T08:46:41+00:00 |
| `vendor/` | 2026-08-28T17:20:25+00:00 |
| `hermes/` | 2026-08-28T17:27:16+00:00 |
| `rules/` | 2026-08-28T17:21:58+00:00 |
| `scripts/` | 2026-10-20T08:46:41+00:00 |
| `tests/` | 2026-10-20T08:46:41+00:00 |
| `ARCHITECTURE.md` | 2026-10-20T08:46:41+00:00 |
| `SETUP.md` | 2026-08-28T17:21:58+00:00 |
| `docs/` | (did not exist before this wave) |

## 2. programming-desk inventory

### 2.1 Top-level layout

`tree` is not installed on this host; listing produced with
`find . -maxdepth 2 -type d -not -path './.git*' ...` and `find . -maxdepth 1`.

```
programming-desk/
+-- README.md AGENTS.md ARCHITECTURE.md SECURITY.md
+-- ownership.yaml openapi.yaml .pre-commit-config.yaml .mcp.json .gitignore desk_cli.py
+-- .github/workflows/ {desk-intake, gates, gates-template-sync, security-nightly, security-pr}.yml
+-- ci/ {.github/workflows, gates, hooks, security, tests}
+-- contracts/ {api, changes, events, tool-packs, tool-rosters}
+-- docs/ (10 .md, listed in 2.9)
+-- grokbot/ {avatars, marketplace, rosters, skills, templates}
+-- infra/ {desk-gateway, lease-heartbeat, railway, substrate, tailscale, telemetry, tests, unified-lsp-broker}
+-- prompts/ {_shared/, bot-00..bot-06-*.xml, LEAD..QUALITY.xml aliases}
+-- prompts-assembled/ {LEAD, SYSTEMS, WEB, ANDROID, IOS, INFRA, QUALITY}.xml
+-- scripts/ {assemble-prompts.sh, generate-templates.py, dev/}
+-- services/desk-gateway/ {README.md, pyproject.toml, uv.lock, src/desk_gateway/, tests/, tools/, web/}
+-- skills/ (27 SKILL.md; README.md)
+-- src/desk/ {cli.py, __main__.py, assertions, diagnostics, recovery, security, session, supervision, telemetry}
+-- tests/ {conftest.py, desk/}
+-- vendor/ultrathink-policy/
+-- android/ ios/ (seat-local tool stubs)
+-- web/ {desk3d, mcp-unified-lsp}
+-- .receipts/bot-00..bot-06-*/  .planning/  .claude/  .cursor/
```

Skill count: `find skills -name SKILL.md | wc -l` = 27. Receipt dirs: `ls .receipts` =
7 seat dirs. `.gitignore` (verbatim, 9 lines): `.venv/ .pytest_cache/ __pycache__/ *.pyc
.receipts/**/*.json !.receipts/**/.gitkeep *.egg-info/ dist/ build/`.

### 2.2 How a bot/agent is declared

Prompt source opening, `prompts/bot-01-systems-backend.xml:1-6`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Bot 1 - Systems & Design. Prepend prompts/_shared/core-directives.xml. -->
<agent id="bot-01-systems-backend" version="1.1" model="claude-opus" confidence_threshold="0.75">

  <identity>
    <role>Systems and Design Engineer</role>
```

`ownership.yaml` structure: `version: 1` (line 19), `bots:` (line 21),
`ownership:` (line 73), `contract_consumers:` (line 441). A `bots:` entry,
`ownership.yaml:29-34`:

```yaml
  bot-01-systems-backend:
    name: Systems & Design
    languages: [rust, python]
    description: >
      Services, APIs, data layer, performance-critical code, and product/system design
      artifacts (flows, component specs, design tokens consumed by clients).
```

Per-seat receipt ownership, `ownership.yaml:222-223`:
`- pattern: ".receipts/bot-01-systems-backend/**"` / `owner: bot-01-systems-backend`.

Prompt inventory (`ls prompts prompts-assembled`): 7 sources `bot-00-programming-lead.xml`
.. `bot-06-quality-security.xml` (23-34 KB each) plus `_shared/`; 7 assembled
`LEAD|SYSTEMS|WEB|ANDROID|IOS|INFRA|QUALITY.xml` (64-71 KB) in both `prompts/` (alias)
and `prompts-assembled/`. Assembly: `scripts/assemble-prompts.sh [--roster <path>] [--check]`
(`scripts/assemble-prompts.sh:12-16`); default roster
`grokbot/rosters/spectrumwebco.json` (`:23`); substitutes `{{DEFAULT_BRANCH}}`,
`{{BOT_ID}}`, `{{DESK_CHANNEL_ID}}`, `{{SEAT_UUID:<SEAT>}}`, `{{DESK_GATEWAY_URL}}`,
`{{DESK_ROSTER_VERSION}}` and treats any leftover `{{...}}` as an error (`:4-7`).

### 2.3 How skills are defined

`skills/contract-first-changes/SKILL.md:1-6`:

```yaml
---
name: contract-first-changes
description: Changing a shared contract safely - breaking-change analysis, versioning, consumer impact. Use before any change to contracts/, .proto files, or openapi.yaml.
bots: [bot-01-systems-backend, bot-06-quality-security]
gates: [G-4]
---
```

`skills/README.md:1-16` defines the levels: L1 Summary (first ~30 lines, decision
tree), L2 Method (procedure, rubrics, failure modes), L3 References (`references/`
files), and requires a bot to cite the level that informed a decision. The README
`## Map` table (`skills/README.md:18-40`) lists each skill with `Bots` and `Purpose`.

### 2.4 How tools are declared/registered

Core roster, `contracts/tool-rosters/_core.yaml:1-26` (conventions header then first tool):

```yaml
# kind:   read  - never mutates a system of record; fails open (empty result + reason)
#         write - mutates; fails closed
# gates:  g5 - deployment-class tool: rollback_plan and approval_id are required inputs
#         g6 - destructive-class tool: approval_id is required and echoed into the audit event
# backend: the gateway module and function that implements the tool
version: 1.0.0
surface: contracts/tool-rosters/_core.yaml
tools:
  - name: desk_brief
    kind: read
    gates: []
    description: >-
      Start-of-turn brief for this seat: ...
    backend: core.brief
    input:
      type: object
      additionalProperties: false
      properties:
        graph_id: { type: string, pattern: "^ut-[a-z0-9]+-[0-9a-f]{8}$" }
        task_id: { type: string, maxLength: 120 }
        refresh: { type: boolean, default: false }
```

Seat roster header, `contracts/tool-rosters/systems.yaml:1-11`:

```yaml
# SYSTEMS roster: core 8 + 7 = 15. Contract surface (QUALITY); consumer bot-01-systems-backend.
version: 1.1.0
seat: bot-01-systems-backend
short: systems
endpoint: /mcp/systems
scope: seat:systems
memory_banks: { own: pd-systems, shared: [pd-desk] }
core: true
packs_allowed: true
consumers: [bot-01-systems-backend]
tools:
  - name: desk_index_query
    kind: read
```

Registration: the gateway maps `backend: <module>.<fn>` to
`services/desk-gateway/src/desk_gateway/tools/{core,packs}.py` and the feature modules
(listing: `ls services/desk-gateway/src/desk_gateway` shows ~80 modules). G-7
(`ci/gates/check_desk_integrity.py`) enforces roster size 10-15 and schema presence
(`.github/workflows/gates.yml:200-201`).

### 2.5 Orchestrator / entrypoints

- `desk_cli.py:1-18` (verbatim): adds `src/` to `sys.path` and calls `desk.cli.main`.
- `src/desk/cli.py:207-244`: `argparse` parser `prog="desk"` with subcommands
  `doctor` (:212), `audit` (:218), `verify` (:226), `session` (:233), `run` (:242,
  "Supervised process execution", `command` as `argparse.REMAINDER`).
- Gateway: `services/desk-gateway/pyproject.toml:27` `desk-gateway = "desk_gateway.server:main"`;
  `server.py:759-760` registers `/healthz`, `:804` registers `/metrics`, `:199`
  `logger = logging.getLogger("desk_gateway")`.
- Supervisor precedent: `src/desk/supervision/process_supervisor.py:11` is
  `subprocess`-based (no `asyncio` import found by
  `grep -n 'import asyncio' src/desk/supervision/process_supervisor.py`).

### 2.6 Config + secrets pattern

- `.mcp.json:1-16`: two HTTP MCP servers with `"Authorization": "Bearer ${HINDSIGHT_MCP_API_KEY}"`
  and `${RAGFLOW_MCP_API_KEY}` - placeholders only, never values.
- `infra/desk-gateway/gateway.env.example:1-4`: live file is
  `/etc/desk-gateway/gateway.env` (root:root 0600, never committed); every variable
  listed, blank means unconfigured. Seat passphrases `SEAT_PASSPHRASE_*` (:24-30), intake
  tokens (:35), upstream tokens (:38-40).
- `services/desk-gateway/src/desk_gateway/config.py:1-60`: settings are a stdlib
  `@dataclass Settings` populated from `os.environ` via `_env/_csv/_float_env` helpers
  (`:39-48`); `SEATS` map seat short name -> bot id (`:9-17`). It is NOT pydantic-settings
  even though `pydantic>=2.11` is a dependency (`pyproject.toml:12`). This is a precedent
  gap for D5's "pydantic-settings" choice (see section 7).

### 2.7 Tests + runners (exact commands)

- `tests/conftest.py:1-9`: inserts repo root and `src/` into `sys.path`.
- Root/desk tests: `python3 -m pytest tests/desk`.
- Gate self-tests: `python3 -m pytest ci/tests/ -v` (`.github/workflows/gates.yml:227` "Gate test suite").
- Gateway: `cd services/desk-gateway && uv sync && uv run pytest -q`
  (`pyproject.toml:30-41`: `uv_build` backend, dev group `pytest>=8.0`,
  `pytest-asyncio>=1.0`, `asgi-lifespan>=2.1`; `asyncio_mode = "auto"`, `testpaths = ["tests"]`).
- Gates: `python3 ci/gates/check_ownership.py --validate-manifest` (`gates.yml:90`),
  `check_ownership.py --bot .. --base ..` (:97), `check_receipt.py` (:168),
  `check_secrets.py --base` (:176), `check_contracts.py` (:189-192),
  `check_rollback.py --receipt` (:198), `check_desk_integrity.py --repo .` (:201);
  `run_all.py --bot --base --receipt [--change] [--strict]` wraps them.
- Prompt drift: `bash scripts/assemble-prompts.sh --check`; `python3 scripts/generate-templates.py --check`.

### 2.8 Lint / format / typecheck

No root `pyproject.toml`, `ruff.toml`, `mypy.ini`, `tox.ini`, `Makefile`, `Dockerfile`
(`ls` of each: "No such file or directory"). `services/desk-gateway/pyproject.toml`
has no `[tool.ruff]` or `[tool.mypy]` section (`grep -rn 'ruff\|mypy'` over
`.pre-commit-config.yaml` and that pyproject returns nothing). The only ruff/mypy
mentions are prose in `skills/platforms/python/SKILL.md:18,33,58` ("`mypy --strict`
on new modules"). `.pre-commit-config.yaml` hooks are all `repo: local` wrappers over
`ci/gates/*` (`g3-committed-secrets`, `g1-ownership-manifest`, `gate-self-test`,
`g4-preflight-selftest`, `g4-contract-preflight` manual stage) - no formatter hooks.
Verdict: `no precedent` for lint/format/typecheck tooling; the convention is prose only.

### 2.9 CI workflows

| Workflow | Trigger (file:line) | What it runs |
|---|---|---|
| `.github/workflows/gates.yml` | `pull_request`+`push` on `main` (`:25-29`) | overlay trusted `ci/gates` from base ref (:46), derive bot from branch (:70), G-1..G-7 (:89-201), `gate-self-test` job `python3 -m pytest ci/tests/ -v` (:227); Python 3.12 (:65, :225) |
| `gates-template-sync.yml` | `pull_request`+`push` on `main` (`:17-21`) | diff live vs `ci/.github/workflows/gates.yml` |
| `security-pr.yml` | `pull_request` on `main` (`:23-25`) | gitleaks on PR commits (:63), semgrep (:115), bandit -> SARIF (:181, :258), pip-audit over `services/**|ci/**/requirements*.txt` (skips when none, :303-310), trivy (:328); SARIF uploads; Python 3.12 (:112, :178, :287) |
| `security-nightly.yml` | `schedule: "17 2 * * *"` + `workflow_dispatch` (`:13-16`) | ZAP/Nuclei vs staging (informational) |
| `desk-intake.yml` | `issues: types: [labeled]` (`:8-10`), `permissions: {}` (:12) | intake token POST only |

### 2.10 Docs conventions

`ls docs`: `cross-bot-protocol.md`, `desk-operating-model.md`,
`github-sot-orchestration.md`, `gotxcot-cloud-pipeline.md`, `handoff-contracts.md`,
`intake-e2e-runbook.md`, `pack-sync.md`, `quality-gates.md`, `upgrade-plan-desk-v2.md`,
`vps-agent-bus.md`. Skills README structure: levels table then a `## Map` table
(`skills/README.md:1-40`). Root docs: `README.md AGENTS.md ARCHITECTURE.md SECURITY.md`.

### 2.11 UI presence

`ls web` = `desk3d/`, `mcp-unified-lsp/`. **AMBIGUITY: not mirrored.** pumpgrok's
target layout (D2) has no `web/`; reporting is markdown only (`pumpgrok report
--daily|--weekly` writing under `var/` and the journal). Flagged so n2/n5 do not
accidentally scope a UI.

## 3. pumpgrok inventory

### 3.1 Languages and manifests

- Language: Python 3 only. Root tools are stdlib + `requests`
  (`tools/jupiter_quote.py:18-20`, `tools/authority_check.py:18-20`,
  `tools/holder_check.py:19-21`, `tools/priority_fee.py:20-22` each `except ImportError`
  on `requests`). Shell: `scripts/*.sh`. Vendor: Python with Russian comments/log strings
  (`rg -c '\p{Cyrillic}' vendor/grokbot-pumpfun/src/*.py`: models.py 114, pipeline.py 104,
  risk.py 68, ops.py 51, agents/base.py 46, executor.py 45, ... every module non-zero).
- Root dependency manifests: **none** (`ls pyproject.toml setup.py requirements*.txt
  .gitignore` all absent; `.gitignore` confirmed absent by `ls .gitignore`). Six
  compiled files are tracked: `git ls-files | rg '\.pyc$'` = 6
  (`tests/__pycache__/test_tools_cli.cpython-312.pyc`,
  `tools/__pycache__/{authority_check,holder_check,jupiter_quote,paper_sim,priority_fee}.cpython-312.pyc`).
- `.devcontainer.json` (whole file): `{"image":"mcr.microsoft.com/devcontainers/python:3"}`.
- Vendor manifests: `vendor/grokbot-pumpfun/pyproject.toml` (`requires-python = ">=3.11"`
  :9; deps :12-19; dev extras :22-29; `grokbot = "src.pipeline:main"` :32; ruff
  `target-version = "py311"` :44; mypy `python_version = "3.11"` :59),
  `requirements.txt:1-8`, `requirements-dev.txt:1-5`, `Dockerfile`, `docker-compose.yml`,
  `Makefile`, `.env.example`, `.github/workflows/ci.yml` (matrix 3.11/3.12/3.13, `:18-19`).
  No lockfile anywhere.

### 3.2 Entrypoints

| Entry | Kind | Evidence |
|---|---|---|
| `tools/jupiter_quote.py` | CLI, GET Jupiter quote | `JUPITER_QUOTE_URL` `:22`; `sys.exit(0 if ok else 1)` `:72` |
| `tools/authority_check.py` | CLI, RPC `getAccountInfo` | `DEFAULT_RPC` `:22`; exit `:87` |
| `tools/holder_check.py` | CLI, RPC `getTokenLargestAccounts` | `:23`; exit `:89` |
| `tools/priority_fee.py` | CLI, RPC `getRecentPrioritizationFees` | `:24`; flags `:91`; exit `:96` |
| `tools/paper_sim.py` | CLI, appends markdown fill to journal | `--desk` default `/workspace/trading-desk` `:48`; exit `:81` |
| `tools/ticket_helper.py` | CLI `next|create|list` | `desk_root` `:41`; `next_ticket_id` `:80-87`; exits `:180,:186` |
| `tools/desk_state.py` | CLI `status|pending-leads|pending-tickets|open-positions|ensure|next-id|halt` | `desk_root` `:50`; `next_ticket_id(desk)` `:107`; `write_halt` `:195-207`; `sys.exit(main())` `:273` |
| `tools/pipeline_evidence.py` | CLI reading vendor JSONL | `sys.exit(main())` `:297` |
| `scripts/check.sh` | bash + embedded Python lint of markdown pack | see section 6 |
| `scripts/hermes-bootstrap.sh`, `hermes-install-cron.sh`, `hermes-verify-isolation.sh` | operator shell | `FORBIDDEN_ENV_RE` `hermes-bootstrap.sh:19`; `FORBIDDEN_KEYS` `hermes-verify-isolation.sh:30` |
| `python -m src.pipeline --config ... [--check] [--i-understand-the-risk]` | vendor engine daemon | `vendor/grokbot-pumpfun/src/pipeline.py:17-18`, `parse_args` `:504-509`, `main` `:560`, `raise SystemExit(main())` `:569` |
| `vendor/grokbot-pumpfun/scripts/{dashboard,replay,tune}.py` | vendor operator scripts | `ls vendor/grokbot-pumpfun/scripts` |
| Hermes cron (6 jobs) | LLM prompts on schedule | `hermes/cron/jobs.yaml:12-71` ids `scout-discover` (every 60m), `risk-audit-open-leads` (15m), `chief-pickup` (15m), `rug-watch-paper` (30m), `chief-journal-rollup` (`0 12 * * *`), `scout-pipeline` (60m); `forbidden_owners: [sniper, exit]` `:79`; `forbidden_actions` `:80-` incl. `send_transaction` `:81` |

Target mapping of these entrypoints to the canonical CLI is in section 8.

### 3.3 Bots and prompt files

| Seat (today) | File | `writes_to_exchange` | Target id (D3) |
|---|---|---|---|
| CHIEF | `agents/chief.md` | false (`:16`) | bot-00-chief |
| SCOUT | `agents/scout.md` | false (`:12`) | bot-01-scout |
| RISK | `agents/risk.md` | false (`:12`); frontmatter `:1-12` has `name,title,description,seat: Trading Floor,skills[5]` | bot-02-risk |
| WHALE | `agents/whale.md` | false (`:11`) | bot-03-whale |
| SNIPER | `agents/sniper.md` | **true** (`:13`) | bot-04-sniper |
| RUG | `agents/rug.md` | false (`:11`) | bot-05-rug |
| EXIT | `agents/exit.md` | **true** (`:12`) | bot-06-exit |
| SHILL | `agents/shill.md` | false (`:10`) | bot-07-shill |
| (none) | - | - | bot-08-signal (new; ports vendor `src/scoring.py` + `src/agents/checker.py`) |
| (none) | - | - | bot-09-journal (new; absorbs `chief-journal-rollup` + `paper_sim.py` journal) |

Every agent file carries the constitution line "NEVER request, accept, store, print,
or reason about seed phrases, private keys, recovery phrases, or any key with withdraw
capability." (`agents/chief.md:28`, `scout.md:24`, `risk.md:24`, `whale.md:23`,
`sniper.md:25`, `rug.md:23`, `exit.md:24`, `shill.md:22`).

Hermes prompts: `hermes/cron/prompts/{scout-discover,scout-pipeline,risk-audit,chief-pickup,rug-watch,chief-journal}.md`
(6 files, `ls hermes/cron/prompts`). Hermes profiles: `hermes/profiles.yaml` -
`telegram_token_profile: chief` (`:16`), `telegram_inbound: true` only for chief
(`:29`; every other profile `false` at `:40,51,62,71,80,91,100`); forbidden env keys
`PRIVATE_KEY, SECRET_KEY, SEED, MNEMONIC` (`:19-22`). Vendor LLM agents:
`vendor/grokbot-pumpfun/src/agents/{base,auditor,narrative,timing,checker}.py`
(`ls src/agents`).

### 3.4 Chains / venues / RPC / data APIs (every URL in code or config)

| Surface | URL | Evidence |
|---|---|---|
| Solana mainnet JSON-RPC (public default) | `https://api.mainnet-beta.solana.com` | `tools/authority_check.py:22`, `tools/holder_check.py:23`, `tools/priority_fee.py:24`, `vendor/.../src/models.py:298`, `config.example.yaml:27`, `README.md:25`, `ARCHITECTURE.md:27` |
| Jupiter quote (lite-api, swap v1) | `https://lite-api.jup.ag/swap/v1/quote` | `tools/jupiter_quote.py:22`; asserted by `tests/test_tools_cli.py:38,71`; `ARCHITECTURE.md:26` |
| pump.fun frontend REST (unofficial) | `https://frontend-api.pump.fun` | `vendor/.../src/models.py:309`; `config.example.yaml:36` |
| PumpPortal WebSocket | `wss://pumpportal.fun/api/data` | `vendor/.../src/models.py:310`; `config.example.yaml:37`; consumed at `src/monitor.py:218` (`websockets.connect(self.config.data.ws_url)`) |
| x.ai Grok chat completions | `https://api.x.ai/v1/chat/completions` | `vendor/.../src/models.py:279` (`fast_model: "grok-4-fast"` :280, `checker_model: "grok-4"` :281); `config.example.yaml:19` |
| Jito block engine (config only, never called) | `https://mainnet.block-engine.jito.wtf/api/v1/bundles` | `vendor/.../src/models.py:291-294` `JitoConfig`; `config.example.yaml:29-32`; only referenced from the stub comment `src/executor.py:156-158` |
| Telegram | token profile, no URL in repo | `hermes/profiles.yaml:16,29`; `scripts/hermes-bootstrap.sh:19` forbids `TELEGRAM_BOT_TOKEN` in non-chief env |
| Alert webhook (Slack/Discord shape) | configured via `GROKBOT_ALERT_WEBHOOK` | `vendor/.../src/models.py:356-368` `AlertsConfig.webhook_url: SecretStr`, events `started,buy,close,rug,breaker,halted,blind`; `ENV_OVERRIDES` `:413` |

All remaining URLs found by `rg -o 'https?://...|wss://...'` are test fixtures
(`hooks.example`, `http://test`, `x.com/cat`), licence links, the upstream repo
(`vendor/.../pyproject.toml:35`, `PUMPGROK.md:7`), and the `your-org` placeholders
(section 6). No other chain, DEX, launchpad, or data vendor exists in code: D8 holds.

### 3.5 Execution / wallet-signing code paths

None executable. Full classification in section 4. Summary: the only code that
would submit a transaction is `vendor/grokbot-pumpfun/src/executor.py:148-172`
(`LiveExecutor.buy/sell`), both bodies are a TODO comment followed by
`raise NotImplementedError(...)`. `solders`/`solana` are declared
(`pyproject.toml:17-18`) but never imported
(`rg -n 'solders|from solana|import solana' src scripts tests` -> one comment hit,
`src/executor.py:150`).

### 3.6 Persistence

| Store | Location | Evidence |
|---|---|---|
| Desk file bus (markdown) | `$PUMPGROK_DESK`, else `/workspace/trading-desk`, else `./trading-desk` | `tools/ticket_helper.py:12,42-45`; `tools/desk_state.py:6,51-54`; `tools/paper_sim.py:48` |
| Halt flag + journal line | `<desk>/desk.md` rewritten in place; `<desk>/journal/YYYY-MM-DD.md` appended | `tools/desk_state.py:195-207` |
| Vendor pipeline state | `state/pipeline.json` (positions, day counters) | `vendor/.../src/models.py:381`; env `GROKBOT_STATE_PATH` `:411` |
| Vendor creator reputation | `state/creators.json` | `models.py:382` |
| Vendor trade log | `logs/trades.jsonl` | `models.py:372`; bridged read-only by `tools/pipeline_evidence.py` (`DEFAULT_LOG`) |

### 3.7 Tests

- Root: `python3 -m unittest tests.test_tools_cli` -> `Ran 11 tests in 0.321s OK`
  (run on this host). No `tests/__init__.py`; loads tools via importlib.
- Vendor: `rg -c '^\s*(async )?def test_' vendor/grokbot-pumpfun/tests/*.py | awk sum` = 264
  across 13 files (`ls vendor/grokbot-pumpfun/tests`: test_agents, test_alerts,
  test_analyzer, test_config, test_filter, test_log, test_ops, test_pipeline,
  test_reputation, test_risk, test_scoring, test_state, test_tune). Not run here
  (assignment forbids running tests).

### 3.8 Docs and alert channels

Docs today: `README.md`, `SETUP.md`, `ARCHITECTURE.md`, `agents/README.md`,
`skills/README.md`, `rules/README.md`, `tools/README.md`, `scripts/README.md`,
`hermes/README.md`, `vendor/grokbot-pumpfun/{README,RUNBOOK,PUMPGROK}.md`. No `docs/`
directory existed before this wave. Alert channels: Telegram via Hermes chief profile
(`hermes/profiles.yaml:16,29`), vendor webhook (`models.py:356-368`), stdout JSON from
every tool.

## 4. Real-money risk surface

Command: `rg -n -i "private_key|secret_key|seed|mnemonic|keypair|sign\(|send_transaction|sendTransaction|swap|jito|tip" /root/src/repos/pumpgrok --glob '!.git' --glob '!banner.jpg'`
-> 94 hits (incl. 0 in `__pycache__`). Note the pattern `tip` also matches
`multiplier`/`multiplex`, which produces 10 false positives.

| Class | Count | Hits (file:line) |
|---|---|---|
| Doc / instruction (constitution, skills, READMEs) | 29 | `rules/pumpgrok-team.mdc:26`, `rules/README.md:17`, `SETUP.md:161,237`, `skills/solana-rpc-and-wallet/SKILL.md:10`, `skills/desk-operating-model/SKILL.md:9`, `skills/browser-ops/SKILL.md:16`, `skills/pumpgrok-setup/SKILL.md:46`, `skills/tool-connections/SKILL.md:22`, `skills/jupiter-routing/SKILL.md:18`, `skills/grokbot-pipeline/SKILL.md:26,29,99`, `skills/solana-api-reference/SKILL.md:9`, `ARCHITECTURE.md:26,123,210,214,232,242`, `README.md:53`, `tools/README.md:38,71`, `hermes/README.md:156`, `vendor/.../README.md:208,345,361,363`, `vendor/.../PUMPGROK.md:16`, 8x `agents/*.md` (chief:28 scout:24 risk:24 whale:23 sniper:25 rug:23 exit:24 shill:22), `agents/risk.md:61` ("Multiple" false positive) |
| Deny-list / isolation config | 10 | `hermes/profiles.yaml:19-22`, `hermes/cron/jobs.yaml:81` (`send_transaction` in `forbidden_actions`), `scripts/hermes-bootstrap.sh:19,55,59,128,146`, `scripts/hermes-verify-isolation.sh:30` |
| False positive (`multiplex`/`multiplier`) | 10 | `scripts/hermes-install-cron.sh:17,90,137`, `hermes/README.md:119,125,126`, `tools/priority_fee.py:6,42,66,77,91,94` (6 of these), `ARCHITECTURE.md:123` |
| Config placeholder | 7 | `vendor/.../config.example.yaml:6,28 ("YOUR-BASE58-PRIVATE-KEY"),29,31,32`, `vendor/.../docker-compose.yml:17` (`${GROKBOT_WALLET_PRIVATE_KEY:-}`), `vendor/.../src/models.py:399` placeholder markers |
| Test fixture | 11 | `tests/test_tools_cli.py:34,38,59,71` (swap URL), `vendor/.../tests/test_config.py:57,71,147,152,158`, `vendor/.../tests/test_pipeline.py:109` (Cyrillic dummy keys) |
| Read-only tool code (swap *quote*, no send) | 2 | `tools/jupiter_quote.py:22,51` |
| Executable config model (reads a key value) | 9 | `vendor/.../src/models.py:291-294 (JitoConfig),299 (wallet_private_key: SecretStr),304 (wallet_key getter),407 (ENV_OVERRIDES GROKBOT_WALLET_PRIVATE_KEY),573 (live requires key),610 (redaction)` |
| Stub (raises) | 5 | `vendor/.../src/executor.py:146,150,156,157,158` (comments inside `LiveExecutor`) |

**Code paths that could submit or sign a transaction: exactly one class, and it raises.**
`vendor/grokbot-pumpfun/src/executor.py:137-172`:

```python
class LiveExecutor(BaseExecutor):
    ...
    async def buy(self, token: Token, size_sol: float) -> ExecutionResult:
        # TODO(live): ... 1. Load Keypair from config.solana.wallet_private_key (solders.keypair).
        # ... 5. if jito.enabled add tip and send bundle; else send_transaction via RPC.
        raise NotImplementedError(
            "LiveExecutor.buy ... before enabling mode: live"
        )

    async def sell(self, position: Position) -> ExecutionResult:
        raise NotImplementedError(
            "LiveExecutor.sell ... before enabling mode: live"
        )
```

(`:161-164` and `:169-172`; Russian message text elided.) It is selected only by
`build_executor` when `config.is_live` (`executor.py:175-180`; `is_live` =
`mode == "live"`, `models.py:466-468`). The pipeline additionally refuses live without
`--i-understand-the-risk` (`pipeline.py:534-541`, `SystemExit`), catches
`NotImplementedError` on buy (`pipeline.py:281-285`, skip reason
`executor_not_implemented`) and on sell (`pipeline.py:441-444`, metric
`sell_not_implemented`). No `solders`/`solana` import exists anywhere.
Root `tools/*.py` contain no send/sign/swap-execute path (`rg` shows only the quote URL).

**Places a key could be read:** only vendor `SolanaConfig.wallet_private_key: SecretStr`
(`models.py:297-304`), fed from YAML `solana.wallet_private_key` or env
`GROKBOT_WALLET_PRIVATE_KEY` (`models.py:407`), masked in `redacted()` (`:610`), and
required non-placeholder only when `mode: live` (`:571-573`). Root tools read no
environment secrets (`ARCHITECTURE.md:210` "Tools do not read environment variables";
confirmed: only `PUMPGROK_DESK`/`PUMPGROK_ROOT` at `ticket_helper.py:42`, `desk_state.py:51`).

**Secret-shape scan (counts only, values redacted):**

| Shape | Regex | Count | Where |
|---|---|---|---|
| base58 64-byte key (87-88 chars) | `[1-9A-HJ-NP-Za-km-z]{87,88}` | 0 | - |
| JSON 64-int byte array | `\[\s*(\d{1,3}\s*,\s*){63}\d{1,3}\s*\]` (multiline) | 0 | - |
| `xai-` token-like (10+ chars) | `xai-[A-Za-z0-9]{10,}` | 14 | all in `vendor/.../tests/test_config.py` (11 lines) and `tests/test_alerts.py:208,217,224` - test fixtures [INFERENCE from location; values not inspected] |
| `sk-` token-like | `\bsk-[A-Za-z0-9]{16,}` | 0 | - |
| Telegram bot token | `\d{8,10}:[A-Za-z0-9_-]{35}` | 0 | - |

## 5. Dependency drift table

Source: `curl -s https://pypi.org/pypi/<pkg>/json` run 2026-10-20 (online; all
queries succeeded). Current pins from `vendor/grokbot-pumpfun/pyproject.toml:12-29`,
`requirements.txt:1-8`, `requirements-dev.txt:1-5`; root `requests` is undeclared.

| Package | Current pin | Latest (requires-python) | Breaking-change note | Action |
|---|---|---|---|---|
| websockets | `>=12.0` | 17.3 (>=3.11) | 13.0 added the new asyncio client; 14+ deprecates the legacy implementation. Vendor uses only `websockets.connect(...)` as async context manager (`monitor.py:23,218`) and async iteration, which the new API keeps [INFERENCE: not executed]. | upgrade, pin `>=15,<18` |
| httpx | `>=0.27` | 0.28.1 (>=3.8) | 0.28 removed the deprecated `proxies=`/`app=` kwargs; vendor uses `AsyncClient`, `MockTransport`, `HTTPStatusError`, `TimeoutException` only (`rg 'proxies=\|app='` in src = 0 hits). programming-desk pins `httpx>=0.28.1` (`services/desk-gateway/pyproject.toml:10`). | upgrade, pin `>=0.28.1,<0.29` |
| pydantic | `>=2.6` | 2.14.1 (>=3.10) | already v2 (`BaseModel, ConfigDict, Field, SecretStr`, `models.py:19`); 2.x minors are additive. programming-desk pins `>=2.11` (`pyproject.toml:12`). | upgrade, pin `>=2.11,<3` |
| pyyaml | `>=6.0` | 6.0.3 (>=3.8) | none | keep, pin `>=6.0.2,<7` |
| solders | `>=0.21` | 0.29.0 (<4.0,>=3.10) | never imported (`rg` = 0 imports; comment only `executor.py:150`); 0.2x API churn irrelevant | **drop** (D4: no live path; reintroduce only behind the live gate) |
| solana | `>=0.34` | 0.41.0 (>=3.11) | never imported | **drop** |
| pytest | `>=8.0` | 9.1.1 (>=3.10) | 9.x removes long-deprecated hooks/`py.path` shims [INFERENCE] | upgrade, pin `>=8.3,<10` and verify |
| pytest-asyncio | `>=0.23` | 1.4.0 (>=3.10) | 1.0 removed the `event_loop` fixture; vendor uses `asyncio_mode = "auto"` (`pyproject.toml:39`) and no `event_loop` fixture (`rg event_loop tests` = 0). programming-desk pins `>=1.0`. | upgrade, pin `>=1.0,<2` |
| pytest-cov | `>=5.0` | 7.1.0 (>=3.9) | none known | upgrade, pin `>=6,<8` |
| ruff | `>=0.6` | 0.17.1 (>=3.7) | rule-set additions; `target-version = "py311"` (`pyproject.toml:44`) -> `py312`; ignores `RUF001-003` exist only for Cyrillic (`:48-52`) and go away once strings are English | upgrade, pin `>=0.17,<0.18` |
| mypy | `>=1.11` | 2.4.0 (>=3.10) | 2.x tightened defaults [INFERENCE]; `python_version = "3.11"` (`pyproject.toml:59`) -> 3.12; `--strict` on `src/` per D5 | upgrade, pin `>=2.4,<3` |
| types-PyYAML | unpinned | 6.0.12.20260906 | none | pin to latest |
| requests (root) | unpinned, undeclared | 2.34.2 (>=3.10) | replaced by httpx under D5 | **drop** after tools are ported |
| New under D5 (for n5): pydantic-settings 2.16.0, tenacity 9.2.1, prometheus_client 0.26.0, pip-audit 2.10.1, uv 0.13.3 | - | queried same run | - | n5 decides |

Python: vendor `requires-python = ">=3.11"` (`pyproject.toml:9`) and CI matrix
`["3.11", "3.12", "3.13"]` (`.github/workflows/ci.yml:19`) vs D1 "3.12 only" ->
target `requires-python = "==3.12.*"` and single-version CI. Deprecated SDK APIs
called: none found (no solders/solana calls; websockets/httpx usage within supported
surface as above).

## 6. Broken / deprecated / drifted items

| # | Item | Evidence | Severity | Fix location (target layout) |
|---|---|---|---|---|
| 1 | Jupiter `/v6/quote` still documented while code uses lite-api | `ARCHITECTURE.md:121` vs `tools/jupiter_quote.py:22` | low | `docs/TOOL_CATALOG.md`, regenerated `ARCHITECTURE.md` |
| 2 | `--max-micro 50000` documented but not implemented | `skills/jupiter-routing/SKILL.md:18`, `tools/README.md:38`, acknowledged `ARCHITECTURE.md:242`; parser `tools/priority_fee.py:91` has only `--rpc --percentile --multiplier` | medium (operator follows a flag that fails) | `src/pumpgrok/tools/market/` fee tool gets a real `max_micro` cap; skill rewritten |
| 3 | `tools/README.md` table omits `desk_state.py` | `tools/README.md:8-14` lists 7 tools; `tools/desk_state.py` exists | low | `docs/TOOL_CATALOG.md` |
| 4 | Manifests say MIT, LICENSE is AGPL-3.0 | `plugin.json:10`, `.claude-plugin/plugin.json:8`, `.grok-plugin/plugin.json:8`, `.cursor-plugin/plugin.json:8` vs `LICENSE:1-4` | high (legal) | the four manifests (`"license": "AGPL-3.0"`), per D2 |
| 5 | `your-org` placeholders | `plugin.json:8,11`, `SETUP.md:16,17`, `ARCHITECTURE.md:241` | medium | manifests, `README.md`, `SETUP.md` -> `swcstudiospace/PumpGrok` (from `git remote -v`) |
| 6 | Dead `pass` checks in lint | `scripts/check.sh:71` (name vs stem), `:89` (writer subset "soft check"), `:148` (swallowed emoji read error), `:31` (nested metadata) | medium (false confidence) | `ci/gates/check_desk_integrity.py` + `scripts/check.sh` rewrite |
| 7 | Three drifting skill maps | `agents/risk.md:6-11` (5 skills) vs `hermes/profiles.yaml:53-57` (different 4) vs `scripts/hermes-bootstrap.sh:21 skills_for()` | medium | single source: `contracts/tool-rosters/*.yaml` + `prompts/bot-0N-*.xml`; `scripts/generate-templates.py` regenerates `agents/*.md`; G-7 asserts agreement |
| 8 | Russian log/exception strings in vendor | `rg -c '\p{Cyrillic}'`: every `src/*.py` non-zero (models 114, pipeline 104, ...) ; ruff ignores `RUF001-003` `pyproject.toml:48-52` | medium (operator-facing, alert text) | port into `src/pumpgrok/{engine,execution,risk,ledger}` with English strings; characterization tests pin behaviour not text |
| 9 | pump.fun frontend-api is unofficial, heuristic field parsing | `vendor/.../src/models.py:309`; parsers `src/monitor.py` `parse_create_event`, `src/analyzer.py` `enrich_token` | high (data fragility) | `src/pumpgrok/tools/market/pumpfun.py` with pydantic response models + respx fixtures under `tests/fixtures/replay/` |
| 10 | ImportError payloads lack `ok:false` in two tools | `tools/authority_check.py:19`, `tools/priority_fee.py:21` vs `holder_check.py:20`, `jupiter_quote.py:19` | low | disappears: deps declared in `pyproject.toml`; shared error envelope in `src/pumpgrok/core/` |
| 11 | `rpc_call` copy-pasted 3x; `desk_root`/`next_ticket_id` duplicated | `tools/authority_check.py:25`, `holder_check.py:26`, `priority_fee.py:27`; `desk_root` `desk_state.py:50` + `ticket_helper.py:41`; `next_ticket_id` `desk_state.py:107` + `ticket_helper.py:80` | medium | `src/pumpgrok/tools/onchain/rpc.py` (single client, failover list per D8); `src/pumpgrok/ledger/tickets.py` |
| 12 | Non-atomic `desk.md` rewrite on halt | `tools/desk_state.py:195-205` (`read_text` ... `path.write_text`) | medium (halt flag can be torn) | `src/pumpgrok/supervisor/killswitch.py` writes `var/KILLSWITCH` atomically (tmp+rename, vendor precedent `state.py` StateStore) |
| 13 | Ticket-ID allocation race | `tools/ticket_helper.py:80-87` scans files then returns max+1 with no lock; 4 cron owners share it (`hermes/cron/jobs.yaml:12-71`) | high (duplicate `SOL-YYYYMMDD-NNN` violates D9) | `src/pumpgrok/ledger/` allocates ids inside the sqlite WAL transaction |
| 14 | No root `.gitignore`; 6 `*.pyc` tracked | `ls .gitignore` -> missing; `git ls-files \| rg '\.pyc$'` = 6 | medium | `.gitignore` (n5), delete tracked pyc (n2) |
| 15 | No root packaging / lockfile; vendor `>=` ranges, no lock | section 3.1 | high | `pyproject.toml` + `uv.lock` |
| 16 | `issues/tissue.json` is `{"version":"1.1.0"}` while manifests say 1.0.0 | `issues/tissue.json` (20 B); `plugin.json` version field | low | drop or align in manifests |
| 17 | Vendor Python floor 3.11 / CI matrix 3.11-3.13 vs D1 3.12 | `vendor/.../pyproject.toml:9`, `ci.yml:19` | low | `pyproject.toml`, `.github/workflows/ci.yml` |
| 18 | solders/solana declared but unused | `pyproject.toml:17-18`; 0 imports | low | drop (section 5) |
| 19 | `hermes/cron/jobs.yaml` schedule strings `"every 60m"` are Hermes-specific, not cron | `hermes/cron/jobs.yaml:15,26,37,48,71` vs `:60` real cron | low | cron prompts become thin wrappers over `pumpgrok scout discover` etc.; schedule owned by the asyncio supervisor |
| 20 | `check.sh` runs no Python tests, does not validate jobs.yaml/manifests/LICENSE | `scripts/check.sh` (lint of markdown only; `scripts/README.md` overstates) | medium | `ci/gates/*` + `ci/tests/` |

## 7. Foundation Stack (column A: what programming-desk actually uses)

| Concern | programming-desk precedent (column A) | Evidence |
|---|---|---|
| Config | stdlib `@dataclass Settings` from `os.environ`; env template file; `${VAR}` placeholders in `.mcp.json` | `services/desk-gateway/src/desk_gateway/config.py:1-60`; `infra/desk-gateway/gateway.env.example:1-4`; `.mcp.json:7,14` |
| Logging | stdlib `logging.getLogger("desk_gateway")`; no JSON formatter found | `services/desk-gateway/src/desk_gateway/server.py:199` |
| Metrics / spans | `/metrics` and `/healthz` custom routes on the MCP server; no `prometheus_client` dependency (`pyproject.toml:9-16`) | `server.py:759-760,804` |
| Scheduler | `no precedent` for in-process async scheduling; `src/desk/supervision/process_supervisor.py:11` is `subprocess`-based; Hermes cron in pumpgrok (`hermes/cron/jobs.yaml`) | - |
| Persistence | `no precedent` for sqlite (`grep -rln 'import sqlite3' src services/desk-gateway/src` = none); receipts are JSON files under `.receipts/<seat>/` | `.gitignore:5-6` |
| HTTP / RPC client | `httpx>=0.28.1` | `services/desk-gateway/pyproject.toml:10` |
| Validation | `pydantic>=2.11` (models), JSON Schema `input` blocks in rosters with `additionalProperties: false` | `pyproject.toml:12`; `contracts/tool-rosters/_core.yaml:18-24` |
| Fixture tests | `pytest>=8.0`, `pytest-asyncio>=1.0`, `asgi-lifespan`, `asyncio_mode = "auto"`; `tests/conftest.py` sys.path shim | `pyproject.toml:32-41`; `tests/conftest.py:1-9` |
| Lint / format / typecheck | `no precedent` (no ruff/mypy config anywhere; prose only in `skills/platforms/python/SKILL.md:33,58`) | section 2.8 |
| CI + vuln scan | `gates.yml` (G-1..G-7 + gate self-test), `security-pr.yml` (gitleaks, semgrep, bandit, pip-audit, trivy, SARIF), Python 3.12 | section 2.9 |
| Container | `no precedent` at root; systemd unit + nginx for the gateway (`infra/desk-gateway/desk-gateway.service`, `install.sh`); pumpgrok's vendor has `Dockerfile`/`docker-compose.yml` | `ls infra/desk-gateway` |
| Package manager | `uv` with `uv.lock` (184 KB) and `uv_build` backend for the service; plain `python3` for gates | `services/desk-gateway/pyproject.toml:29-30`; `ls -la services/desk-gateway/uv.lock` |

Column B (choices) is n5's; D5 already fixes most of it. Contradiction to report:
D5 names pydantic-settings, prometheus_client, sqlite3 WAL, JSON logging and
ruff/mypy, none of which has a programming-desk precedent (rows above). This is
"mirror shape and names, not libraries" (D1) and is consistent with D1 but should be
stated explicitly in `FOUNDATION_STACK.md`.

## 8. Old-to-new module mapping skeleton

Decisions keep/move/rewrite belong to `docs/MIGRATION_MAP.md`; this table only fixes
the destination under D2 so n2/n3/n5 share one vocabulary.

### 8.1 pumpgrok top-level paths

| Today | Target (D2) | Notes |
|---|---|---|
| `README.md` | `README.md` | fix `your-org` |
| `SETUP.md` | `docs/runbooks/setup.md` | content merges into runbooks |
| `ARCHITECTURE.md` | `ARCHITECTURE.md` | regenerate |
| `LICENSE` | `LICENSE` | unchanged (AGPL-3.0) |
| `plugin.json`, `.claude-plugin/`, `.grok-plugin/`, `.cursor-plugin/` | same paths | license -> AGPL-3.0, org placeholders fixed (D2) |
| `.devcontainer.json` | `.devcontainer.json` | pin python 3.12 image |
| `banner.jpg` | `banner.jpg` | - |
| `issues/tissue.json` | (drop or `issues/`) | n2 decides |
| `agents/*.md` (8) | `agents/<seat>.md` regenerated by `scripts/generate-templates.py` from `prompts/bot-0N-<seat>.xml` | frontmatter contract kept (`name/title/description/seat/skills/writes_to_exchange`) |
| (none) | `prompts/_shared/core-directives.xml`, `prompts/bot-00-chief.xml` .. `bot-09-journal.xml`, `prompts-assembled/<SEAT>.xml` | new; constitution text from `agents/*.md` moves verbatim into core-directives |
| `rules/pumpgrok-team.mdc`, `rules/README.md` | same | kept (D2) |
| `skills/<name>/SKILL.md` (23) | `skills/<name>/SKILL.md` upgraded in place + new skills | frontmatter gains `bots:`/`gates:` |
| `skills/README.md` | `skills/README.md` | Map table in programming-desk shape |
| `hermes/README.md`, `hermes/profiles.yaml` | `hermes/` | kept |
| `hermes/cron/jobs.yaml` | `hermes/cron/jobs.yaml` | kept; prompts become thin wrappers |
| `hermes/cron/prompts/scout-discover.md` | wrapper over `pumpgrok scout discover` | |
| `hermes/cron/prompts/scout-pipeline.md` | wrapper over `pumpgrok scout pipeline` | |
| `hermes/cron/prompts/risk-audit.md` | wrapper over `pumpgrok risk audit` | |
| `hermes/cron/prompts/chief-pickup.md` | wrapper over `pumpgrok chief pickup` | |
| `hermes/cron/prompts/rug-watch.md` | wrapper over `pumpgrok rug watch` | |
| `hermes/cron/prompts/chief-journal.md` | wrapper over `pumpgrok journal rollup` | owner moves to bot-09-journal [INFERENCE: D3 gives journal to bot-09] |
| `scripts/check.sh` | `scripts/check.sh` (thin) + `ci/gates/check_desk_integrity.py` | dead `pass` checks replaced |
| `scripts/hermes-bootstrap.sh`, `hermes-install-cron.sh`, `hermes-verify-isolation.sh` | `scripts/hermes-*.sh` | kept; `skills_for()` reads rosters |
| `scripts/README.md` | `scripts/README.md` | |
| `tools/jupiter_quote.py` | `src/pumpgrok/tools/market/jupiter.py` (`market.quote`) | CLI `pumpgrok` wrapper |
| `tools/authority_check.py` | `src/pumpgrok/tools/safety/authority.py` | |
| `tools/holder_check.py` | `src/pumpgrok/tools/onchain/holders.py` | |
| `tools/priority_fee.py` | `src/pumpgrok/tools/onchain/priority_fee.py` | adds real `max_micro` |
| `tools/paper_sim.py` | `src/pumpgrok/execution/paper.py` + `pumpgrok paper buy\|sell` | writes the ledger, not markdown |
| `tools/ticket_helper.py` | `src/pumpgrok/ledger/tickets.py` + `pumpgrok ticket next\|create\|list` | id allocation in sqlite txn |
| `tools/desk_state.py` | `src/pumpgrok/supervisor/state.py` + `pumpgrok state status\|halt`, `pumpgrok killswitch set\|clear\|status` | |
| `tools/pipeline_evidence.py` | `src/pumpgrok/replay/evidence.py` | reads ledger/JSONL export |
| `tools/README.md` | `docs/TOOL_CATALOG.md` | |
| `tests/test_tools_cli.py` | `tests/test_cli_contracts.py` (+ `tests/desk/`) | |
| `tools/__pycache__/*.pyc`, `tests/__pycache__/*.pyc` (tracked) | deleted; `.gitignore` | |
| (none) | `AGENTS.md SECURITY.md CHANGELOG.md ownership.yaml .pre-commit-config.yaml .gitignore desk_cli.py pyproject.toml uv.lock Makefile Dockerfile docker-compose.yml .env.example` | new per D2 |
| (none) | `.github/workflows/{gates,security-pr,ci}.yml`, `ci/{gates,hooks,security,tests}/` | new |
| (none) | `contracts/{README.md,tool-rosters/*.yaml,events/,changes/}` | new |
| (none) | `services/desk-gateway/` | new, thin per-seat wrapper |
| (none) | `.receipts/<seat>/.gitkeep` (10 seats), `var/` (gitignored) | new |
| `/workspace/trading-desk/*` (runtime, outside repo) | `var/` (ledger.sqlite, snapshots, journal, KILLSWITCH, health) + JSONL export | runtime path moves into repo-relative `var/` [INFERENCE] |

### 8.2 vendor/grokbot-pumpfun modules

| Vendor module | Target under `src/pumpgrok/` | Seat |
|---|---|---|
| `src/pipeline.py` (orchestrator, CLI, healthz JSON) | `supervisor/pipeline.py` + `cli.py` (`pumpgrok run`) | bot-00-chief |
| `src/monitor.py` (PumpPortal WS, launch filter) | `engine/monitor.py`; WS client in `tools/market/pumpportal.py` | bot-01-scout |
| `src/analyzer.py` (pump.fun REST fetch, metrics, vetoes) | `engine/analyzer.py`; REST client in `tools/market/pumpfun.py` | bot-01-scout / bot-05-rug |
| `src/scoring.py` | `engine/scoring.py` | bot-08-signal |
| `src/agents/base.py` (Grok httpx client, retries) | `engine/agents/base.py` (LLM failure -> rule-based, D5) | bot-08-signal |
| `src/agents/auditor.py` | `engine/agents/auditor.py` | bot-05-rug |
| `src/agents/narrative.py` | `engine/agents/narrative.py` | bot-07-shill |
| `src/agents/timing.py` | `engine/agents/timing.py` | bot-08-signal |
| `src/agents/checker.py` | `engine/agents/checker.py` | bot-08-signal |
| `src/executor.py` `DryRunExecutor` | `execution/paper.py` `PaperAdapter` (adds fee/slippage/impact model) | bot-04-sniper / bot-06-exit |
| `src/executor.py` `LiveExecutor` | `execution/live.py` disabled stub raising `LiveGateError` (D4) | bot-04-sniper |
| `src/risk.py` `RiskManager` | `risk/manager.py` (+ D6 limits, breakers) | bot-02-risk |
| `src/risk.py` `PositionWatcher`, `exit_signal` | `engine/exits.py` | bot-06-exit |
| `src/reputation.py` | `risk/reputation.py` | bot-02-risk |
| `src/state.py` `StateStore` | `ledger/store.py` (sqlite WAL) + snapshots | bot-09-journal |
| `src/log.py` `TradeLog` | `ledger/journal.py` (JSONL export) | bot-09-journal |
| `src/alerts.py` `Notifier` | `tools/notify/` (abstract Notifier; stdout+file; telegram/webhook adapters) | bot-00-chief |
| `src/ops.py` (`Metrics`, `RateLimiter`, `CircuitBreaker`, `CallBudget`, `HealthServer`, `Heartbeat`) | `supervisor/{metrics,breakers,health}.py` (prometheus_client, D5) | bot-00-chief |
| `src/models.py` (domain + `Config`) | `config/settings.py` (pydantic-settings) + `core/models.py` | bot-02-risk (config), bot-00-chief |
| `scripts/dashboard.py` | `reporting/dashboard.py` (`pumpgrok report`) | bot-09-journal |
| `scripts/replay.py` | `replay/summary.py` | bot-09-journal |
| `scripts/tune.py` | `replay/tune.py` | bot-08-signal |
| `tests/*.py` (264) | `tests/engine/`, `tests/execution/`, `tests/risk/`, `tests/ledger/` as characterization tests | - |
| `config.example.yaml`, `.env.example` | `config/{dev,paper,live}.toml` + `.env.example` | - |
| `Dockerfile`, `docker-compose.yml`, `Makefile` | root `Dockerfile`, `docker-compose.yml`, `Makefile` | - |
| `.github/workflows/ci.yml` | `.github/workflows/ci.yml` (3.12 only) | - |
| `README.md`, `RUNBOOK.md`, `PUMPGROK.md` | `docs/runbooks/engine.md`; `PUMPGROK.md` rules into `docs/SAFETY_INVARIANTS.md` | - |
| `pyproject.toml`, `requirements*.txt`, `conftest.py`, `LICENSE` (MIT upstream) | root `pyproject.toml`/`uv.lock`; upstream MIT notice retained in `CHANGELOG.md`/`docs/MIGRATION_MAP.md` attribution | - |

`vendor/grokbot-pumpfun/` is removed only when zero inbound references remain
(D2). Today's inbound references: `tools/pipeline_evidence.py` (`DEFAULT_LOG`),
`scripts/check.sh` (existence check of `src/pipeline.py` and `PUMPGROK.md`),
`skills/grokbot-pipeline/SKILL.md:12`, `hermes/cron/prompts/scout-pipeline.md`.

## 9. Clarifications resolved from evidence

- **q1 chains/venues:** keep all existing, Solana only. Evidence: every endpoint in
  section 3.4 (`tools/*.py:22-24`, `vendor/.../src/models.py:279,298,309,310`); no
  other chain appears in any URL scan. Jito stays config-only and uncalled.
- **q2 alert channel:** reuse existing. Telegram token profile on chief
  (`hermes/profiles.yaml:16,29`) and vendor `AlertsConfig.webhook_url`
  (`vendor/.../src/models.py:356-368`, env `GROKBOT_ALERT_WEBHOOK` `:413`). D6's
  abstract Notifier wraps both plus stdout/file.
- **q3 paper sizing:** no repo evidence for equity or per-trade caps in SOL
  (`risk-limits.md` is created empty by `tools/desk_state.py ensure`; vendor defaults
  are per-trade `max_sol_per_trade` with a >5 SOL warning at `models.py:576-580`).
  Assumed Conservative 10 SOL-equivalent + D6 limits; every number REVIEW.
- **q4 coupling:** mirror shape only, no cross-repo imports. Both are Python 3.12
  (programming-desk CI `gates.yml:65`; pumpgrok target D1). programming-desk's
  registry is repo-local YAML (`contracts/tool-rosters/*.yaml`) plus an unpublished uv
  package (`services/desk-gateway/pyproject.toml:1-30`, no publish workflow in
  `.github/workflows/`), so nothing is importable across repos anyway.

## Unverified Items

| Unknown | Default assumed |
|---|---|
| Vendor 264 tests currently pass on Python 3.12 with latest deps (not run; assignment forbids tests) | assumed passing at the pinned upstream versions; re-run is the main agent's check |
| websockets >=15 compatibility of `monitor.py:218` async-iteration pattern (not executed) | compatible; characterization test will prove |
| The 14 `xai-` shaped strings in vendor tests are synthetic fixtures (values not inspected) | synthetic; G-3 allowlist pragma to be added if they trip the gate |
| PyPI "latest" values are a 2026-10-20 snapshot; pins will drift by implementation time | re-query during n5 lockfile creation |
| Whether `/workspace/trading-desk` runtime data must be migrated into `var/` or discarded | discard (research/paper data only, no real fills by construction) |
| Owner of `chief-journal-rollup` after the seat split (chief today) | bot-09-journal per D3 |
| programming-desk `src/desk/telemetry/` may contain a JSON log formatter precedent (only `audit_tracer.py` seen, not read) | treated as `no precedent` for logging format |
| `issues/tissue.json` purpose (20-byte version stub) | drop |
