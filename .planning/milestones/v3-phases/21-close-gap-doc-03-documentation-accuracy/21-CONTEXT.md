# Phase 21 Context: Close gap DOC-03 (documentation accuracy)

## Gap

DOC-03 (REQUIREMENTS.md): "README, ARCHITECTURE, SETUP, skills/replay-and-backtest/SKILL.md, plugin version statements and docs/VENDOR_PIN.md match the code. Every contradiction from the 2026-10-25 docs audit is corrected, and each change appears in CHANGELOG.md."

Re-verification of phase 7 (`07-VERIFICATION.md`, verified at commit e58920b) found DOC-03 not satisfied. The earlier passed verification overstated it. The orchestrator checked each claim against the tree:

- ARCHITECTURE.md names `ticket_helper.py` and `paper_sim.py` (lines 172, 174, 184, 188, 196, 205). Neither file exists in the repository.
- ARCHITECTURE.md describes `vendor/grokbot-pumpfun/` as present (lines 15, 31, 33, 68, 87, 198, 209). The directory is absent, and `docs/VENDOR_PIN.md` records that it moved.
- ARCHITECTURE.md line 244 says "eight persistent Bots". The desk has ten seats (AGENTS.md, ownership.yaml, agents/).
- `.claude-plugin/marketplace.json` and `.grok-plugin/marketplace.json` carry version `1.0.0` (line 10) and describe an "Eight-role" desk (line 9). `pyproject.toml`, `plugin.json`, `.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json`, and `.grok-plugin/plugin.json` carry `0.1.0`. The phase 7 context named four manifests and missed both marketplace files.
- `tests/docs/test_doc_consistency.py` checks plugin versions for the four named manifests only, so the marketplace drift passed unnoticed.
- The `/workspace/trading-desk` rows in ARCHITECTURE and SETUP were flagged by the 2026-10-25 audit as paths to be replaced with verified current paths. They are still present.

## Decisions

- **D-01:** Scope is the DOC-03 named documents only: `README.md`, `ARCHITECTURE.md`, `SETUP.md`, `skills/replay-and-backtest/SKILL.md`, all six plugin manifests (`plugin.json`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.cursor-plugin/plugin.json`, `.grok-plugin/plugin.json`, `.grok-plugin/marketplace.json`), `docs/VENDOR_PIN.md` (verify only), `tests/docs/test_doc_consistency.py` (regression coverage), and one `CHANGELOG.md` entry. Nothing else changes.
- **D-02:** Red first. Extend `tests/docs/test_doc_consistency.py` so the plugin-version assertion covers all six manifests, and add an assertion that no plugin manifest description says "Eight-role". Run it and record the failure on the current tree (the two marketplace manifests) before any document change.
- **D-03:** Manifests. Set `version` to `0.1.0` in both marketplace manifests (line 10). Change "Eight-role" to "Ten-seat" in both descriptions (line 9) and keep the rest of each description unchanged.
- **D-04:** ARCHITECTURE.md. Produce a table covering every line that matches `eight|Eight|vendor/grokbot-pumpfun|trading-desk|ticket_helper|paper_sim|--rpc|no server, queue|started as a service|market.price`. For each line record: old text, new text, and the evidence path (the code, skill, or doc that supports the new text). Specifically:
  (a) `ticket_helper.py` and `paper_sim.py` are absent. Replace each mention with the mechanism the repository actually provides, or remove the mention. Do not describe a script that does not exist.
  (b) Vendor claims become "absent from this checkout; formerly vendored (see docs/VENDOR_PIN.md)".
  (c) `/workspace/trading-desk` stays only where a repository skill or script uses the same path (`skills/portfolio-ledger/SKILL.md`, `skills/desk-post-trade-review/SKILL.md`, `scripts/hermes-*.sh`). Where it stays, say it is the operator's host folder outside the repository.
  (d) Line 244 "eight persistent Bots" becomes "ten seats".
- **D-05:** SETUP.md. Lines 4 and 5 ("eight Bots", section 5) become "ten seats". The `/workspace/trading-desk` mkdir and touch steps (around lines 48 to 54 and 166 to 182) stay only if D-04(c) keeps the path. Every command in SETUP.md is checked against the CLI help (`uv run pumpgrok --help` and the verb help) and against the Makefile. Record each check.
- **D-06:** README.md. Confirm the phase 7 residuals are gone: no `--rpc` flag, no "eight" role or Bot wording, no vendor layer row in the present tense, no `/workspace/trading-desk` path without the D-04(c) condition. Fix any that remain.
- **D-07:** `skills/replay-and-backtest/SKILL.md`. Confirm the S2 wording overclaim from phase 7 CONTEXT line 26 is corrected (replay drives the supervisor, rule, and paper adapter with a fixture clock; the checkpoint path writes its verdict row first and does not run the paper adapter). Fix only if the overclaim remains.
- **D-08:** CHANGELOG.md. One entry under the v3 section listing each DOC-03 correction and the marketplace version fix. Keep the replay hash line `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` unchanged.
- **D-09:** Verification. `uv run python -m pytest tests/docs -q --junitxml=/tmp/phase21-docs.xml` (exit 0, counts read from the XML), `./scripts/verify_doc_commands.sh`, `./scripts/check.sh`, `make lint`, and `uv run pumpgrok verify --fixture smoke-10m` reporting CONSISTENT with the hash above. Run the D-04 grep table again: zero unresolved hits.
- **D-10:** Out of scope here. `docs/ROSTER.md` and `docs/FOUNDATION_STACK.md` are self-described design documents outside the DOC-04 fixed set. Their status is recorded as tech debt, not changed.
- **D-11:** Work on branch `bot-00-chief/v3-closeout` in `/root/src/repos/pumpgrok-wt/v3-closeout` only. Commit with explicit paths, one commit for the test (red then green) and one for the documents plus CHANGELOG. Do not push, merge, or touch `/root/src/repos/pumpgrok`. ASCII only. Planning and new text carry no placeholder markers.
