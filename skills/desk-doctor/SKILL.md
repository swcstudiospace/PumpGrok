---
name: desk-doctor
description: Run `pumpgrok doctor --json` to prove the operator inputs for the effective mode before any trading claim, and run the prompt drift checks before trusting a seat's instructions.
bots:
  - all
gates:
  - G-7
required_tools:
  - desk.doctor
required_data: []
permissions:
  max_side_effect: read
  network: true
  filesystem: none
fixtures:
  - tests/fixtures/replay/smoke
---

# Desk Doctor

## L1 - Summary

Run the doctor before claiming the desk is healthy. Two different commands answer two different questions:

- `uv run pumpgrok doctor --json` is the gate. It names each operator input with its requirement, status and source. It exits 1 when a required input is missing or a forbidden input is present. It never prints a value.
- `uv run pumpgrok doctor` is a text report. It prints the mode, one line per subsystem (present, or not yet implemented as a warning), the RPC source line and a summary. It exits 0 whenever it prints. Read it; do not treat its exit code as health.

No ticket moves until the gate passes.

```
doctor --json exit 0  -> every required operator input for the effective mode is present
doctor --json exit 1  -> STOP: read the failing name and status, fix the cause, re-run; never trade on a sick desk
```

## L2 - Method

1. S1 - Gate: run `uv run pumpgrok doctor --json`. Read each record's `name`, `required_for_mode`, `status` and `source`. A failing record is one whose `required_for_mode` is `required` and whose `status` is not `present`, or whose input is `forbidden` and present. Exit 1 means at least one failing record.
2. S2 - Subsystems and prompt drift:
   - Read the text report with `uv run pumpgrok doctor`. Its `info mode=` line gives the effective mode. Its `warn` lines name subsystems or endpoints that are not yet implemented or not served; they are known warnings, not gate failures.
   - This release's doctor does not report a prompt SHA. The prompt check is drift: `scripts/assemble-prompts.sh --check` and `python3 scripts/generate-templates.py --check`. A drift exit means a seat would run instructions that were not built from `prompts/`. Regenerate from the source and check again; never trade on the mismatch.
3. S3 - Seat tool grants: run `uv run pumpgrok onboarding list`. Each seat lists its roster tools (from `contracts/tool-rosters/`) with a state. Only `granted` means an allow decision is recorded. `not_granted`, `denied`, `unbound` and `unavailable` all mean the tool is not granted. A tool that is not granted is not used; do not work around it.
4. S4 - Mode: the effective mode must be `paper`. Paper is the mode this desk runs. A live path is refused by the live gate in this release: `run` exits 3 when its live preconditions are unmet. If any check reports a live path, halt new tickets and escalate to CHIEF and RISK. Stay in paper.
5. S5 - Attach the receipt: store the passing `doctor --json` output with `desk.receipt_check` before the first ticket of the session, so the receipt chain shows a healthy desk at start.

## Failure modes

| Symptom | Cause | Action |
|---|---|---|
| `doctor --json` exit 1, `xai_api_key` missing | A Grok seat is enabled without a key | Supply a non-empty `PUMPGROK_GROK__API_KEY` by name in the environment; re-run. Never paste the key |
| `doctor --json` exit 1, `seat_tool_access` missing | Roster tools without a bound decision | Ask the operator to record each tool with `uv run pumpgrok onboarding access --seat <seat> --tool <tool> --allow` (or `--deny`); re-run |
| `onboarding list` shows `not_granted` or `denied` for a needed tool | No allow decision, or a revoke | Record the decision as the operator, or accept the denial; never bypass it |
| `onboarding list` shows `unbound` or `unavailable` | Recorded authority the ledger does not authenticate, or an unreadable operator key | Stop; escalate. Do not re-create or edit the authority files |
| Prompt drift check exits nonzero | A prompt or generated agent file differs from its source | Regenerate with the two commands in S2; check again |
| `doctor --json` exit 1 with `forbidden` input present | A forbidden input is set for the mode | Remove the input from the environment; re-run |
| Mode reports live, or `run` exits 3 | Live preconditions unmet | Halt tickets; escalate to CHIEF and RISK; stay in paper |
| Doctor passes but receipt missing | Operator skipped the receipt step | Re-run with `desk.receipt_check` attached; unreceipted health is unproven |

## References

- CLI: `uv run pumpgrok doctor` (text report) and `uv run pumpgrok doctor --json` (gate)
- Input inventory: `src/pumpgrok/doctor.py` (`REQUIREMENTS`, `input_inventory`, `failing_inputs`)
- Seat grants: `uv run pumpgrok onboarding list`; `src/pumpgrok/cli/onboarding.py`
- Skill contract: `src/pumpgrok/core/skill.py:32-52` (`SkillManifest`, `SkillPermissions`)
- Rosters: `contracts/tool-rosters/bot-00-chief.yaml` (seat grants plus core merge)
- Gate G-7: setup and doctor gate for desk changes
- Companion skills: `pumpgrok-setup` (bootstrap and paper start), `tool-connections` (RPC source), `verification-receipts` (receipt chain)
