# 07-05 SUMMARY: doc-consistency and historical-banner tests (DOC-03, DOC-04)

Wave 3, depends on 07-01..07-04. Implements the two 07-05 plan tasks:
the machine-checked doc-consistency test suite and the historical-banner
test plus banners on the three root historical design records.

## Commits

- `1d19aaf` test(07-05): [DOC-03] add doc-consistency machine checks
  (`tests/docs/test_doc_consistency.py`)
- `46142dd` feat(07-05): [DOC-04] banner root historical records and add
  banner test (`tests/docs/test_historical_banners.py`,
  `docs/DISCOVERY.md`, `docs/MIGRATION_MAP.md`,
  `docs/upgrade-plan-desk-v2.md`)
- This summary is committed separately per brief rule 7.

## Changed files

Created in worktree `/root/src/repos/pumpgrok-wt/p7-05` only:

- `tests/docs/test_doc_consistency.py` (new, DOC-03). Four checks:
  1. The four plugin manifests (`plugin.json`, `.claude-plugin`,
     `.cursor-plugin`, `.grok-plugin`) carry the same `version` as
     `pyproject.toml` (all `0.1.0` at write time, verified by grep).
  2. `docs/VENDOR_PIN.md` contains pin
     `409e74c905faa0e9de42e918efe2c604f206856e` and a retirement
     statement (OVERRIDE-D, see below).
  3. Every `pumpgrok VERB` command named in `README.md`,
     `ARCHITECTURE.md`, `SETUP.md` and
     `skills/replay-and-backtest/SKILL.md` exists in `pumpgrok --help` /
     `pumpgrok tools --help` output, collected via subprocess with
     `--help` flags only; no verb is ever executed. A negative lookbehind
     keeps the `/workspace/pumpgrok` path in SETUP.md from reading as a
     verb. Documented verbs at write time: `paper`, `run`, `scout`,
     `ticket`, `tools` (all registered in `src/pumpgrok/cli.py`).
  4. None of the corrected contradiction strings (`eight-role`,
     `Eight specialist`, `--rpc`, `Version 1.0.0`,
     `same code path as live paper`, `identical path`,
     `no server, queue, or daemon`) appears in those four docs
     (case-insensitive; all absent at write time, verified by grep).
  Deterministic, offline, no network, no full suite.
- `tests/docs/test_historical_banners.py` (new, DOC-04). Fixed five-file
  set from CONTEXT D-05; each file must begin with the exact first line
  `Historical design record`. The two `docs/design/` files are intentionally
  left unbannered for plan 07-06, so this test is expected to fail until
  07-06 lands; acceptance in this plan is collection without error.
- `docs/DISCOVERY.md`, `docs/MIGRATION_MAP.md`,
  `docs/upgrade-plan-desk-v2.md` (bannered, DOC-04). First line is exactly
  `Historical design record`; second line is
  `This file describes the design at the time, not current behaviour.`
  No other lines touched.

## Deviations from plan

### Plan correction OVERRIDE-D (from brief, supersedes plan text)

Plan check (2) required `docs/VENDOR_PIN.md` to match a vendored snapshot
marker. That snapshot was deleted in Phase 4 (STRUCT-006); `vendor/` does
not exist on disk. The test therefore asserts instead that
`docs/VENDOR_PIN.md` contains the pin
`409e74c905faa0e9de42e918efe2c604f206856e` and a retirement statement,
and the test itself references no `vendor/` directory path. Recorded here
as the OVERRIDE-D plan correction.

### Process deviation: misdirected edits, reverted

The first banner-prepend pass resolved relative paths against the
orchestrator checkout `/root/src/repos/pumpgrok` instead of the worktree.
The three files were restored there with a targeted
`git checkout --` of exactly those paths (verified `git status --short`
empty afterwards), and the banners were re-applied with absolute worktree
paths. No orchestrator-checkout content was changed: final
`git -C /root/src/repos/pumpgrok status --short` output is empty.
No other file outside `files_modified` was edited.

## Acceptance commands (for the orchestrator; not run here per brief rule 2)

- `uv run pytest -q tests/docs/test_doc_consistency.py` (plan acceptance:
  exits 0)
- `uv run pytest -q tests/docs/test_historical_banners.py --collect-only`
  (plan acceptance: exits 0)
- `head -n1 docs/DISCOVERY.md docs/MIGRATION_MAP.md docs/upgrade-plan-desk-v2.md`
  (each line reads `Historical design record`)

Known state: the full banner test (without `--collect-only`) fails until
plan 07-06 banners `docs/design/interfaces.md` and
`docs/design/paper-engine.md`. That failure is expected and owned by 07-06.

## Verification performed here (read-only, per brief rule 2)

Grep only: manifest and `pyproject.toml` versions equal (`0.1.0`); pin and
retirement wording present in `docs/VENDOR_PIN.md`; documented verbs all
registered in `src/pumpgrok/cli.py`; banned strings absent from the four
docs; banner first lines present in the worktree; design files still
unbannered; new test files contain no `vendor/` path reference and no
authored placeholder brackets. No test runner, linter, binary, or network
command was executed.
