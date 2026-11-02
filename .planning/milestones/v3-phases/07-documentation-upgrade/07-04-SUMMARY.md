# Phase 7 Plan 4: Plugin manifests + vendor pin (DOC-03, part 2) — Summary

Plan `07-04` (wave 1, no dependencies) aligned the four plugin manifests with
`pyproject.toml` and corrected the vendor pin record. Executed in worktree
`/root/src/repos/pumpgrok-wt/p7-04` on branch `bot-00-chief/p7-04`.

## What changed

- `plugin.json`, `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json`,
  `.grok-plugin/plugin.json`: `"version"` set to `"0.1.0"` to match
  `pyproject.toml` (`version = "0.1.0"`); description strings changed from
  eight-role/Eight-role to ten-seat/Ten-seat.
- `docs/VENDOR_PIN.md`: pin line
  `409e74c905faa0e9de42e918efe2c604f206856e` kept byte-identical; the
  present-tense vendored statements now say the tree was retired in Phase 4
  (STRUCT-006) and the pin is the historical provenance record of the retired
  oracle.

## Commits

- `8a01a67` — docs(07-04): align plugin manifests to 0.1.0 and correct vendor
  pin record [DOC-03] (5 files: the four manifests + `docs/VENDOR_PIN.md`).

## Changed files

- `plugin.json`
- `.claude-plugin/plugin.json`
- `.cursor-plugin/plugin.json`
- `.grok-plugin/plugin.json`
- `docs/VENDOR_PIN.md`
- `.planning/phases/07-documentation-upgrade/07-04-SUMMARY.md` (this file)

## Deviations

None from the file set — only the five plan-listed source files plus this
summary were touched. No `src/`, `rules/`, `agents/`, `CHANGELOG.md`,
`STATE.md`, or `ROADMAP.md` edits.

## Plan corrections (orchestrator overrides, supersede plan text)

- OVERRIDE-A: version field set to `0.1.0` in all four manifests, matching
  `pyproject.toml`. The `$schema` URL (`schemas/1.0.0/plugin.schema.json`)
  is a schema version, not the package version, and was left untouched.
- OVERRIDE-B: no vendored snapshot was searched for (the tree was retired in
  Phase 4, STRUCT-006; `vendor/` is absent from the tree). The pin line
  `409e74c905faa0e9de42e918efe2c604f206856e` was kept present in
  `docs/VENDOR_PIN.md`; only the present-tense vendored statements were
  corrected to past tense (retired in Phase 4, pin as historical provenance
  record of the retired oracle). Desk rules and runtime-artefacts paragraphs
  left byte-identical.
- OVERRIDE-C: description strings changed from eight-role to ten-seat in all
  four manifests (root `an eight-role` → `a ten-seat`; the three dot-plugin
  `Eight-role` leads → `Ten-seat`). The agent-name parenthetical in
  `.claude-plugin/plugin.json` was left as-is (out of override scope).

## Acceptance commands (exact, run in worktree root)

```
for f in plugin.json .claude-plugin/plugin.json .cursor-plugin/plugin.json .grok-plugin/plugin.json; do grep -q '"version": "0.1.0"' $f || exit 1; done; grep -q "409e74c905faa0e9de42e918efe2c604f206856e" docs/VENDOR_PIN.md
```

Result: exit 0 (`ACCEPTANCE-OK`). Supporting greps: no `eight-role`/`Eight-role`
remains in the four manifests; all four carry `ten-seat`/`Ten-seat`;
`vendor/` absent; STRUCT-006 retirement commit present in history; ten-seat
language confirmed in `AGENTS.md` and `src/pumpgrok/supervisor/scheduler.py`.

## Self-check

- All five plan files plus this summary exist in the worktree.
- Commit `8a01a67` present on `bot-00-chief/p7-04`; no deletions in the diff;
  no untracked files left behind.
- Main checkout `/root/src/repos/pumpgrok` untouched (verified via
  `git -C /root/src/repos/pumpgrok status --short`, empty).

## Self-Check: PASSED
