---
name: pumpgrok-setup
description: Bootstrap the PumpGrok Solana memecoin trading desk from zero in paper mode. Clone the repository, sync dependencies, record the operator's seat tool decisions and RPC choice, then prove a paper start. This is the first skill a Bot must run when it receives the SETUP.md.
bots:
  - bot-00-chief
gates:
  - G-7
required_tools:
  - desk.doctor
required_data: []
permissions:
  max_side_effect: paper-write
  network: true
  filesystem: none
---

# PumpGrok Setup

## L1 - Summary
First-run bootstrap that turns a fresh checkout into a paper desk. The desk starts only when every operator input for paper is recorded. Runs once per desk, and again only for a step that failed. The desk starts in research mode; this skill leaves it there with no wallet connected. Setup never sets up a non-paper mode.

## L2 - Method
1. Follow `SETUP.md` top to bottom. Its clone section is normative. Key stages:
   - Clone the repository: `git clone --depth 1 <repo-url> pumpgrok`, then `cd pumpgrok`.
   - Read the constitution (`rules/pumpgrok-team.mdc`) and the `desk-operating-model` skill.
   - Sync dependencies from the committed lockfile: `uv sync --frozen`.
   - Check the subsystems: `uv run pumpgrok doctor`. The text report always exits 0; read its lines. The gate is `doctor --json` (see `desk-doctor`).
   - Create the operator key, once: `uv run pumpgrok onboarding init-key`. The operator types `create operator key` at the prompt. The key is a local HMAC authority secret under `var/operator/`. It is not a wallet key or a signing key, and it is never printed.
   - Record the seat tool decisions (see Missing decisions).
   - Confirm the RPC endpoint source (see Endpoint source).
   - Prove the paper start (see Start paper).
   - Write `desk.md` and starter risk numbers through `desk-risk-limits`; run the smoke checks; return the receipt (schema: `verification-receipts`).
2. Missing decisions. The paper start counts every seat tool decision:
   - `uv run pumpgrok onboarding list` prints each seat and each roster tool with its state: `granted`, `denied`, `not_granted`, `unbound` or `unavailable`. `not_granted` means no decision is recorded yet.
   - `uv run pumpgrok doctor --json` reports `seat_tool_access`. It is `present` only when every roster tool of every seat has a bound decision.
   - The operator records each missing tool at an interactive terminal, typing the phrase shown at the prompt:
     - Allow: `uv run pumpgrok onboarding access --seat <seat> --tool <tool> --allow`. Type `allow <seat> <tool>`.
     - Deny: `uv run pumpgrok onboarding access --seat <seat> --tool <tool> --deny`. Type `deny <seat> <tool>`.
   - Revoke a grant: `uv run pumpgrok onboarding revoke --seat <seat> --tool <tool>`. Type `revoke <seat> <tool>`. A revoked tool shows `denied` in `onboarding list` and grants nothing. The start gate counts a bound revoke as a recorded decision, so after a revoke check `onboarding list`; do not rely on the start gate to catch it.
   - `--seat` must be one of `bot-00-chief` to `bot-09-journal`. `--tool` must be in that seat's roster under `contracts/tool-rosters/`; the CLI refuses any other name.
   - Every onboarding write needs an interactive terminal on stdin and stdout, and the operator's typed phrase. Recording a tool decision or an RPC choice also needs the operator account that owns the key. `init-key` needs only the terminal. Agents and pipes get a refusal and nothing is written. An agent never types a phrase on the operator's behalf.
3. Endpoint source. The RPC source decides which endpoint is in effect:
   - `uv run pumpgrok onboarding rpc` prints `default`, `explicit` or `unbound`. `default` means no operator choice is recorded and the configured endpoint is used. `default` is not consent. `explicit` is an operator choice the ledger authenticates. `unbound` is a recorded choice the ledger does not authenticate, so none is in effect.
   - To choose: `uv run pumpgrok onboarding rpc --endpoint <url>`. The URL must already be a configured endpoint; no new provider is added. Only its scheme, host and port are recorded. The operator types the `rpc <endpoint>` phrase shown at the prompt.
4. Start paper:
   - One replay cycle, the health proof after setup: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke`. It prints one engine decision (`skip` or `buy`) and appends one journal note.
   - Serving form: `uv run pumpgrok run --mode paper --serve --replay tests/fixtures/replay/smoke`, with `PUMPGROK_HEALTH__PORT` set to a nonzero port. It replays the dataset in a loop and serves `/healthz` and `/metrics`. `--serve` never takes `--once`.
   - Before any supervisor starts, the paper gate checks the operator inputs. A missing input prints `paper start refused: required inputs are missing; no supervisor was started`, one line per input, and exits 1. Fix each named input and run again.
   - Any other `run` form exits 5 (not implemented in this release).
   - Autonomy is set only by a human: `uv run pumpgrok state autonomy <policy> --by <human>`, where `<policy>` is `manual-ticket` or `autonomous-paper`. Setup never sets it.
5. Paper and replay:
   - Paper is the only mode this skill sets up. Paper logs simulated fills only.
   - `--replay <dir>` names a recorded fixture directory that the run reads. Rows written from a replay carry `source=replay`. Paper-engine rows carry `source=paper`.
   - The live gate computes its paper-performance preconditions from `source=paper` rows only; any `source=replay` row refuses those metrics. A replay cycle proves the desk runs. It is not a trading record.
6. No secret is echoed:
   - The onboarding verbs, `doctor --json` and the paper gate print names, states and sources. They never print values, and no secret is accepted on the command line.
   - The x.ai key is needed only when a Grok seat is enabled. Enabling it requires `PUMPGROK_GROK_GATEWAY__ENABLED=true`. The key itself must be a non-empty x.ai key in `PUMPGROK_GROK__API_KEY`, supplied as an environment variable by name in the process environment (for example through the compose `env_file`). The CLI does not read `.env` files.
   - Check the key with `uv run pumpgrok doctor --json`: `xai_api_key` shows `present` with `source` `env`, or `missing` when it is required and absent. Read the status; never the value.
   - Never paste a key into chat, a file, a command or a commit. If one appears in chat or a log, stop, do not repeat it, and escalate per the constitution.
7. Paper never asks for or reads a wallet, a private key or a seed phrase. The paper inventory marks the wallet input not-read, so a missing or malformed wallet value never blocks a paper start. The operator key in step 1 is the HMAC authority key described there, not a wallet key.
8. Non-paper public-address confirmation (separate step, typed, explicit). Not part of paper setup, and this release has no non-paper start:
   - The human confirms the public address in its own step, typed explicitly by the human. The address is a public key only. Setup never asks for a key or phrase.
   - `uv run pumpgrok live confirm --by <human> --notional-cap <sol> --expires <iso-8601>` writes a signed live confirmation record. This release's live gate reports that record as unverified, and live stays refused. A configured wallet allowlist is not a confirmation.
9. Review gates stay explicit. G-7 covers setup and doctor. A gate passes only on evidence a human or the gate owner can see. No step passes a gate on the agent's own judgment. The constitution (`rules/pumpgrok-team.mdc`) governs every step.

## Failure modes
- Skipped constitution read: setup is void; re-run from the constitution step.
- Bots created without full standing instructions: recreate; partial instructions are not instructions.
- Engagement above `research` during setup: refuse. Setup never raises engagement.
- Seed phrase or private key requested, accepted, or stored: abort setup and escalate.
- Paper start refused: do not report the desk ready. List each named input and its status, fix the cause, and run again.
- Asked to type an onboarding phrase or to read a key on the operator's behalf: refuse. The operator types it.
- A key or secret pasted in chat or a log: stop, do not repeat it, escalate per the constitution.

## Output
```
PUMPGROK SETUP COMPLETE
Bots: [list]
Skills: [list]
Trading Floor: created
Engagement: research
Wallet: not yet connected
Operator inputs: [doctor --json status per input name, no values]
Status: ready for tool connections and risk-limits interview
```
Emit `Status: ready` only after the paper start in step 4 has passed.

## References
- Guide: `SETUP.md`; runbook: `docs/runbooks/setup.md`
- Constitution: `rules/pumpgrok-team.mdc`; roles: `desk-operating-model`
- Gate and checks: `desk-doctor`; event mode after setup: `docs/runbooks/events.md`
- Next: `tool-connections`, then the `desk-risk-limits` interview
