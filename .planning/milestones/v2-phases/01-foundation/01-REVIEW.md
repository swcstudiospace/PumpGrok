---
phase: 01-foundation
reviewed: 2026-10-21T06:18:28Z
depth: standard
files_reviewed: 101
files_reviewed_list:
  - .dockerignore
  - .github/workflows/ci.yml
  - .github/workflows/gates.yml
  - .github/workflows/security-pr.yml
  - .gitignore
  - .pre-commit-config.yaml
  - .python-version
  - .receipts/bot-00-chief/.gitkeep
  - .receipts/bot-01-scout/.gitkeep
  - .receipts/bot-02-risk/.gitkeep
  - .receipts/bot-03-whale/.gitkeep
  - .receipts/bot-04-sniper/.gitkeep
  - .receipts/bot-05-rug/.gitkeep
  - .receipts/bot-06-exit/.gitkeep
  - .receipts/bot-07-shill/.gitkeep
  - .receipts/bot-08-signal/.gitkeep
  - .receipts/bot-09-journal/.gitkeep
  - AGENTS.md
  - CHANGELOG.md
  - Dockerfile
  - Makefile
  - SECURITY.md
  - agents/exit.md
  - agents/journal.md
  - agents/shill.md
  - agents/signal.md
  - ci/gates/check_contracts.py
  - ci/gates/check_desk_integrity.py
  - ci/gates/check_ownership.py
  - ci/gates/check_receipt.py
  - ci/gates/check_rollback.py
  - ci/gates/check_secrets.py
  - ci/gates/run_all.py
  - ci/security/bandit.ini
  - ci/security/bandit_json_to_sarif.py
  - ci/security/gitleaks.toml
  - ci/security/semgrep.yml
  - ci/tests/test_gates.py
  - ci/tests/test_security_workflows.py
  - contracts/README.md
  - contracts/changes/README.md
  - contracts/tool-rosters/_core.yaml
  - contracts/tool-rosters/bot-00-chief.yaml
  - contracts/tool-rosters/bot-01-scout.yaml
  - contracts/tool-rosters/bot-02-risk.yaml
  - contracts/tool-rosters/bot-03-whale.yaml
  - contracts/tool-rosters/bot-04-sniper.yaml
  - contracts/tool-rosters/bot-05-rug.yaml
  - contracts/tool-rosters/bot-06-exit.yaml
  - contracts/tool-rosters/bot-07-shill.yaml
  - contracts/tool-rosters/bot-08-signal.yaml
  - contracts/tool-rosters/bot-09-journal.yaml
  - docker-compose.yml
  - docs/DISCOVERY.md
  - docs/VENDOR_PIN.md
  - docs/cross-bot-protocol.md
  - docs/desk-operating-model.md
  - docs/quality-gates.md
  - ownership.yaml
  - prompts/_shared/core-directives.xml
  - pyproject.toml
  - scripts/assemble-prompts.sh
  - scripts/check.sh
  - scripts/generate-event-schemas.py
  - scripts/generate-templates.py
  - scripts/prompt_sources.py
  - src/pumpgrok/__init__.py
  - src/pumpgrok/cli.py
  - src/pumpgrok/config/settings.py
  - src/pumpgrok/core/__init__.py
  - src/pumpgrok/core/adapter.py
  - src/pumpgrok/core/correlation.py
  - src/pumpgrok/core/ids.py
  - src/pumpgrok/doctor.py
  - src/pumpgrok/execution/__init__.py
  - src/pumpgrok/execution/live/__init__.py
  - src/pumpgrok/execution/live/live_adapter.py
  - src/pumpgrok/execution/live/live_gate.py
  - src/pumpgrok/logging/__init__.py
  - src/pumpgrok/logging/json.py
  - src/pumpgrok/logging/redaction.py
  - src/pumpgrok/replay/__init__.py
  - src/pumpgrok/replay/clock.py
  - src/pumpgrok/replay/fixtures.py
  - src/pumpgrok/replay/rng.py
  - tests/config/test_forbidden_keys.py
  - tests/config/test_settings.py
  - tests/conftest.py
  - tests/fixtures/replay/smoke/events.jsonl
  - tests/fixtures/replay/smoke/manifest.json
  - tests/harness/__init__.py
  - tests/harness/faults.py
  - tests/replay/test_clock.py
  - tests/replay/test_fixtures.py
  - tests/safety/test_static_guards.py
  - tests/test_correlation.py
  - tests/test_live_gate.py
  - tests/test_logging.py
  - tests/test_network_block.py
  - tests/test_skip_cycle.py
  - uv.lock
findings:
  critical: 1
  warning: 7
  info: 8
  total: 16
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-10-21T06:18:28Z
**Depth:** standard
**Files Reviewed:** 101
**Status:** issues_found
**Scope:** 84f0bd3 (prior review) to HEAD, task-commit evaluation scope (SUMMARY.md tier). Incremental scope from the prior review's commit.

## Summary

Review performed inline by the orchestrator; no subagent was available to spawn. No tests, linters, formatters or gate scripts were executed. Gate functions were probed only with pure-function calls on scratch input; no repository file was modified.

Coverage, stated plainly:

- Read in full: every Python module under `src/pumpgrok/` in scope, all of `ci/gates/*.py`, `scripts/*.py` and `scripts/*.sh`, `ci/security/bandit_json_to_sarif.py`, `Dockerfile`, `docker-compose.yml`, `Makefile`, `.github/workflows/*.yml`, `.pre-commit-config.yaml`, `pyproject.toml`, `tests/safety/test_static_guards.py`, `tests/conftest.py`.
- Structure and cross-references checked, not line-by-line: remaining tests and `ci/tests/`, contract roster YAML (checked by G-7 logic), `docs/*.md`, `agents/*.md` (generated from `prompts/`), `contracts/README.md`, `prompts/_shared/core-directives.xml`, `.receipts/*/.gitkeep`, `tests/fixtures/replay/smoke/*`.
- Excluded from review by scope rules: `uv.lock` (lock file), `.python-version` and `.gitignore` (configuration only).

The most serious issue is a governance bypass, not a crash: the path-ownership gate exempts contract surfaces from the owner check, and the contract gate accepts acknowledgements written by the change author. Several gates also fail open or miss common forms. No defect was found in the ledger, the live gate, or the replay clock.

## Critical Issues

### CR-01: Contract surfaces bypass path ownership; contract gate accepts self-written acknowledgements

**File:** `ci/gates/check_ownership.py:187-194`, `ci/gates/check_contracts.py:121-123`, `ci/gates/check_contracts.py:185-186`, `ownership.yaml:149-151`, `docs/cross-bot-protocol.md:20-32`
**Issue:** In `check_ownership.main`, a path that matches a `contract_surface` rule is appended to `contracts` by the `elif is_contract:` branch, which comes before `elif owner != args.bot:`. A file owned by another seat is therefore never reported FOREIGN, and G-1 passes with only a NOTE. Confirmed with `resolve_owner`: `contracts/tool-rosters/bot-03-whale.yaml` resolves to `('bot-02-risk', True)`, so a `bot-04-sniper` branch that edits bot-03's tool roster passes G-1. G-4 then validates a change document written by the same author. `acks` is built from that document (line 123) and each required consumer's acknowledgement is read from it (lines 185-186). `check_contracts` takes no `--bot` argument, never compares `proposed_by` to the acting seat, and never rejects an acknowledgement from the proposer. Protocol rule 2 says seats never reach into another seat's files, and rule 4 says a seat cannot acknowledge for another seat. The gates enforce neither.
**Fix:** Report non-owner paths as FOREIGN before applying the contract classification, so only the owner of a surface, or CHIEF's routed change, can edit it. In `check_contracts.py`, add `--bot`, require `proposed_by == --bot`, and reject any acknowledgement whose `bot` equals `proposed_by`:

```python
# check_ownership.main: classify ownership first, then note contract surfaces
elif owner != args.bot:
    foreign.append((path, owner))
elif is_contract:
    contracts.append(path)
```

Acknowledgement provenance cannot be verified from repository contents alone; state that limit in the gate documentation.

## Warnings

### WR-01: Secret and contract gates pass when the diff cannot be computed

**File:** `ci/gates/check_secrets.py:238-245` and `:248-255`, `ci/gates/check_contracts.py:95-102`
**Issue:** `changed_files` and `staged_files` call `subprocess.run` without `check=True` and ignore the return code. When git fails (unknown base ref, shallow clone, missing remote), stdout is empty, the function returns `[]`, and the gate prints `G-3 PASS — no files to scan` or `G-4 PASS — no contract surfaces touched`. `check_ownership.changed_files` (lines 75-86) already exits on the same failure. CI sets `fetch-depth: 0` and fetches the base, so the exposure is local and misconfigured runs, but a security gate should fail closed.
**Fix:** Mirror `check_ownership.changed_files`:

```python
try:
    out = subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=REPO_ROOT)
except subprocess.CalledProcessError as exc:
    sys.exit(f"check_secrets: git diff failed: {exc.stderr}")
```

### WR-02: Single-star ownership globs cross directory separators

**File:** `ci/gates/check_ownership.py:36-59`, `ci/gates/check_contracts.py:47-58`
**Issue:** The `_match` docstring (lines 37-41) says `web/*` must not match `web/a/b.ts`, but the final `fnmatch.fnmatch(path, pattern)` lets `*` match `/`. Verified: `_match('web/*', 'web/a/b.ts')` and `_match('src/*.py', 'src/a/b.py')` both return True. No current rule in `ownership.yaml` uses a single-star path segment, so nothing is misattributed today. The next such rule will silently claim nested directories. `check_contracts._match` has the same defect.
**Fix:** Match segment by segment: split on `/`, treat `**` as any depth, and apply `fnmatch` to each segment. Add a test with `web/*` against `web/a/b.ts`.

### WR-03: Rollback gate misses `rm -fr` and `rm --recursive`

**File:** `ci/gates/check_rollback.py:34`
**Issue:** `\brm\s+-rf?\b` matches only `-r` or `-rf` as the first flag. `rm -fr dir`, `rm -f -r dir` and `rm --recursive dir` are not classified as destructive, so G-6 requires no approval for them.
**Fix:** Match any short-flag cluster containing `r` or the long form:

```python
((r"\brm\s+(?:-[a-zA-Z]*[rR][a-zA-Z]*\b|--recursive\b)", "fs", "recursive delete"),)
```

Add cases for `rm -fr`, `rm -f -r` and `rm --recursive`.

### WR-04: Static clock and randomness guard misses common ambient calls

**File:** `tests/safety/test_static_guards.py:23-33` and `:84-95`; `src/pumpgrok/replay/rng.py:3-5`
**Issue:** `_AMBIENT_RANDOM` lists only `random.random` and `random.SystemRandom`, and `_CLOCK_PRIMITIVES` lists only `datetime.now`. Probe run through `find_violations` on a scratch package returned no violations for `random.randint(1, 6)`, `random.choice([1, 2])` and `datetime.utcnow()`. The `rng.py` docstring says ambient randomness is rejected by this guard. Nothing in `src/pumpgrok` uses these calls today (grep found none), so this is latent.
**Fix:** Flag every attribute access on the `random` module except `Random`, and add `datetime.utcnow`, `datetime.today` and `date.today` to the clock set. Add probe cases for each.

### WR-05: Dev text logging does not redact tracebacks

**File:** `src/pumpgrok/logging/json.py:119-120`; `src/pumpgrok/logging/redaction.py:86-91`
**Issue:** With `PUMPGROK_LOG_JSON=false` under the `dev` profile, `setup_logging` installs a plain `logging.Formatter`. `RedactionFilter` redacts `record.msg` and extras but not `exc_info`, and `logging.Formatter` appends the formatted traceback without redaction. `JsonFormatter` redacts `exc` (`json.py:93-97`), so only the dev text path leaks: an exception message containing a key-bearing URL or a base58 key prints verbatim. Production profiles always use JSON, so the exposure is limited to developer machines.
**Fix:** Subclass `logging.Formatter` and pass `formatException` output through `redact_text`, or redact `record.exc_info` text inside `RedactionFilter`.

### WR-06: Fixture digest is not bound to the bytes parsed

**File:** `src/pumpgrok/replay/fixtures.py:85-112` and `:138-144`
**Issue:** `verify_manifest` hashes each listed file, then `load_dataset` opens `events.jsonl` again through `read_jsonl` and parses that second read. A file replaced between the two opens passes verification. `_sha256` and `is_file()` also follow symlinks, so a listed name can point outside the dataset directory. The module docstring promises that a dataset is trusted only after its listed files match.
**Fix:** Read each listed file once into memory, hash those bytes, and parse events from the same buffer. Reject symlinks with `Path.is_symlink()` before reading.

### WR-07: Emoji scan silently skips unreadable files

**File:** `scripts/check.sh:165-173`
**Issue:** The emoji check wraps each read in `except Exception: pass`. A file that fails to read is never checked and does not produce an error, so the instruction lint reports the file as clean. The same loop is the only check of `.planning/**/*.md` and `rules/*.mdc`.
**Fix:** Replace `pass` with `err(f"{path}: unreadable: {exc}")` and keep the `UnicodeDecodeError` path explicit.

## Info

### IN-01: Malformed change documents crash G-4 instead of reporting

**File:** `ci/gates/check_contracts.py:115-116`, `:123`, `:279-284`
**Issue:** An empty change document parses to `None`, and `field not in doc` raises `TypeError`. An acknowledgement without a `bot` key raises `KeyError` at line 123. Both exit 1 with a traceback rather than a G-4 message.
**Fix:** In `main`, check `isinstance(doc, dict)` and that each acknowledgement is a mapping with `bot` before calling `check_change_doc`.

### IN-02: Empty or non-mapping roster raises `AttributeError`

**File:** `scripts/prompt_sources.py:206-215`
**Issue:** `load_roster` calls `doc.get` on the result of `yaml.safe_load`. An empty roster yields `None` and an `AttributeError` traceback, not a `PromptError` naming the file.
**Fix:** `if not isinstance(doc, dict): raise PromptError(f"{path.name}: top level is not a mapping")`.

### IN-03: Skill names are interpolated without escaping

**File:** `scripts/assemble-prompts.sh:66`; `scripts/prompt_sources.py:195`
**Issue:** `<skill>{s}</skill>` and `  - {s}` are written verbatim. `check_skills` confirms only that a directory exists, so a name containing `<`, `&` or YAML-special characters produces malformed output that the drift check then accepts as current.
**Fix:** Use `xml.sax.saxutils.escape` for the XML element and the `_scalar` helper for the YAML list item.

### IN-04: Bandit SARIF converter leaks handles and indexes unchecked keys

**File:** `ci/security/bandit_json_to_sarif.py:24`, `:29`, `:42`, `:66`
**Issue:** `open()` is called without a context manager for both input and output. `r["test_id"]` and `r["filename"]` raise `KeyError` on a malformed report.
**Fix:** Use `with open(...)` blocks and `r.get(...)` with an explicit error for missing required fields.

### IN-05: HEALTHCHECK does not test liveness; loopback port has no listener

**File:** `Dockerfile:28-29`; `docker-compose.yml:55-56`
**Issue:** `pumpgrok doctor` verifies that settings load and modules import; it does not check the process, the ledger or any live state. The compose file publishes `127.0.0.1:8080` for a `/healthz` endpoint that this release does not serve.
**Fix:** Document the HEALTHCHECK as a configuration check only, or remove the port mapping until an endpoint exists.

### IN-06: Audit target writes to a fixed `/tmp` path

**File:** `Makefile:29-30`
**Issue:** `make audit` exports requirements to `/tmp/pumpgrok-req.txt`. A pre-existing symlink or a concurrent run can redirect the write or make `pip-audit` read a stale file.
**Fix:** Use `mktemp` inside the recipe, or write under `var/`.

### IN-07: Security and gate tooling installed without version pins

**File:** `.github/workflows/security-pr.yml:93`, `:106-107`; `.github/workflows/gates.yml:50`
**Issue:** `pip install semgrep`, `pip install bandit` and `pip install pyyaml` are unpinned, and Semgrep fetches the registry packs `p/security-audit` and `p/secrets` at run time. A gate's outcome can change without a repository change. `ci.yml` already pins `uv==0.13.4`, so the pattern exists.
**Fix:** Pin the tool versions, and pin registry rulesets by commit or vendor them into `ci/security/`.

### IN-08: Gate overlay does not remove PR-added files

**File:** `.github/workflows/gates.yml:40-43`
**Issue:** `git checkout origin/$BASE_REF -- ci/gates/` restores files that exist on the base, but a file added under `ci/gates/` by the PR stays on disk. No current gate imports such a file, so this is latent. `ci/tests/` is not overlaid at all, which matches its role as the PR's own test suite.
**Fix:** Recreate `ci/gates/` from the base tree (for example `git archive origin/$BASE_REF ci/gates | tar -x` into a clean directory) before running the gates.

---

_Reviewed: 2026-10-21T06:18:28Z_
_Reviewer: Claude (gsd-code-reviewer, inline review; no subagent)_
_Depth: standard_
