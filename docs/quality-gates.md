# Quality gates

PumpGrok uses the programming-desk gate set, retargeted to a trading desk. Every gate is a
script under `ci/gates/`. `ci/gates/run_all.py` runs them in order and is the single entry point
for CI and for local pre-flight. A gate that fails is fixed at its cause. Nobody bypasses it.

## The gates

| Gate | Script | What it proves | Input |
|---|---|---|---|
| G-1 Path ownership | `check_ownership.py` | Every path the change touches has exactly one owning seat in `ownership.yaml`; an unowned path fails. | `--bot`, `--base` |
| G-2 Verification receipt | `check_receipt.py` | The seat ran the commands it claims and they exited 0. CI re-runs the commands. | `--receipt`, `--bot` |
| G-3 Committed secrets | `check_secrets.py` | No key material, token shape or secret-bearing URL is committed. | `--base` |
| G-4 Contract-first changes | `check_contracts.py` | A change to a contract surface carries a change document; a breaking change has an acknowledgement from every consumer. | `--base`, optional `--change` |
| G-5/G-6 Rollback and destructive ops | `check_rollback.py` | A deployment names a rollback command, recovery time and data implications (G-5). A destructive operation has human approval recorded before execution (G-6). | `--receipt` |
| G-7 Desk integrity | `check_desk_integrity.py` | The desk's own description is sound: rosters, tool schemas, prompt sources and templates. Reads the repo as it is; no diff, no receipt. | `--repo` |

Gate self-tests live in `ci/tests/` and run under pytest. G-7 always runs, because a bad roster
is bad on every commit and not only on the one that introduced it.

## Running the gates

```bash
python3 ci/gates/run_all.py --bot bot-04-sniper --base origin/main \
    --receipt .receipts/bot-04-sniper/feat-paper-fill.json
```

Stdlib Python and PyYAML only, the same as CI. The Makefile wraps it as `make gates BOT=... TASK=...`.
The canonical suite, which CI also runs, is:

```bash
uv sync --frozen --group dev
make lint typecheck test audit          # ruff, mypy --strict, pytest, pip-audit
./scripts/check.sh                      # instruction-file lint, no network
```

`make check` runs the same lint, typecheck, test and audit targets, then the prompt-assembly and
template drift checks, the event-schema drift check, and `./scripts/check.sh`.

## Receipts (G-2)

A completion claim needs a receipt at `.receipts/<seat>/<task-id>.json`. Required fields are
`task_id`, `bot`, `commands`, `claims` and `unverified`.

- `commands` lists what was actually run, with the exit code observed.
- `claims` lists what the commands prove. Each claim must be backed by a command.
- `unverified` is mandatory and must be specific. An empty list is allowed but rarely honest.
- `approved_by` names a reviewer other than the authoring bot. A self-approval fails the gate.
- The receipt gate rejects commands that bypass the checks they stand in for, such as
  `--no-verify`, which skips the secret scanner.

Receipts are gitignored by default (`.receipts/**/*.json`). Track a new receipt with `git add -f`.

## Branch convention

Work lands on `bot-0N-<seat>/<unit>` branches, one PR per batch. The gates workflow
(`.github/workflows/gates.yml`) derives the acting seat from the branch prefix and fails a branch
that does not start with a seat id. G-1 then checks the seat's paths against `ownership.yaml`.

## Engagement levels

The desk runs at one of two engagement levels, `research` or `paper` (R16). Live execution is a
configuration mode, not an engagement level. `pumpgrok run --mode live` exits 3 unless every
precondition of the live gate holds, and in this release the live gate never holds. A gate or
document that names any other level is wrong. No gate enforces this wording yet; review does.

## Waivers

There are none. A failing gate is a defect in the change or in the gate, and the fix goes to the
owning file. A gate that is wrong gets a fix plus a self-test that pins the corrected behaviour.
The phase verifier records gaps; it does not waive them.

## Exit codes of the runtime

These are not gates, but the replay gate and the container health check depend on them.
`pumpgrok` exits 0 on success, 1 on config or usage error, 2 on ledger inconsistency, 3 when the
live gate refuses, 4 on a corrupt replay fixture, and 5 for verbs not yet implemented.
`pumpgrok doctor` exits 0 whenever settings are valid; subsystems that have not landed are
reported as warnings.
