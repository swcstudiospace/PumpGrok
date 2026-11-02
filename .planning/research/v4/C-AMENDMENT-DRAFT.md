# Constitution amendment, DRAFT 2026-10-28 (milestone v4, dormant live path)

Status: DRAFT for owner approval. No agent applies, merges, or paraphrases this text. It becomes effective only when the owner approves the exact wording below in writing; the apply units C-13 and C-14 are blocked until then. Style and numbering follow `.planning/AMENDMENT-2026-10-25.md`.

## Principle

Minimal change. Each clause keeps every sentence that still holds and changes only what the segregated signer and the one-time human arm require. The paper-mode wording approved on 2026-10-25 is untouched.

## Scope

- Clauses 1, 2, 3, 8 and 9, the SNIPER bullet, and the closing paragraph of `rules/pumpgrok-team.mdc`.
- The constitution copies that quote them: `prompts/_shared/core-directives.xml` items 1, 2, 3 (both the trading-seats and risk variants), the regenerated `agents/*.md` and `prompts-assembled/*.xml`, `skills/desk-operating-model/SKILL.md` lines 24 and 39, `agents/sniper.md` item 3.
- `docs/RISK_POLICY.md` section 1 rows 1, 2, 3, 8, 9, section 3.3, section 5, section 6, change-control item 4; `docs/LIVE_READINESS.md`; `docs/SAFETY_INVARIANTS.md` INV-S-01 and INV-R-10 text; `SECURITY.md` Key custody; `.planning/PROJECT.md` out-of-scope rows for live trading, custody, signing and venues; `README.md` posture sentence.
- Unchanged: clauses 4, 5, 6, 7; the throwaway wallet limit; the kill switch; every human-only clear (`killswitch_clear`, `halt_clear`, UNKNOWN reconcile); the D6 fractions (2 percent per trade, 5 percent per token, 5 percent daily-loss floor, 15 percent drawdown); `live.notional_cap_sol` hard maximum 1.0; the nine-precondition live gate and exit 3; the rule that SNIPER and EXIT are the only senders; the role list.

## 1. rules/pumpgrok-team.mdc

SNIPER bullet, replace:

    - **SNIPER** is the only Bot that may send a buy transaction, and only after RISK CLEAR plus approval under clause 2.

Clause 1, replace the whole clause with:

    1. **No private keys.** Never request, accept, store, print, or reason about seed phrases, private keys, or recovery phrases. Only a dedicated throwaway wallet ≤ $200 USDC + SOL for fees is used. No agent, tool, or desk process holds key material. In live mode the wallet key exists only inside the separate desk-signer process, placed there by the human directly, never through chat, git, desk files, tool arguments, or the desk environment. Connection of the wallet is performed by the human only.

Clause 2, keep every sentence up to and including "Simulated paper fills are not sends. Their approval is the autonomy level a human sets with `pumpgrok state autonomy` (a ConfigChanged row with a human `by`).", then replace the final sentence ("This clause governs live sends only.") with:

    This clause governs live sends only. A live send requires either that exact approval message, or an arm record: a standing authorization the human signs once with the operator key, bound to the exact configuration hash, the wallet allowlist, the listed strategies, a notional cap of at most 1.0 SOL, and an expiry. Under an unexpired, verified arm record the desk may send autonomously for the listed strategies only, inside the written risk limits and the record's caps, and each send is recorded as an ApprovalRecorded row of kind autonomous_live. Agents never create, extend, or widen an arm record. A halt, kill switch, open breaker, strategy kill, demotion, or UNKNOWN hold suspends autonomous sends until a human clears it.

Clause 3, replace the whole clause with:

    3. **Single-send rule.** SNIPER (buys) and EXIT (sells) send once only. A send is recorded durably before it is submitted. On any unknown or timed-out result, report “UNKNOWN RESULT – reconcile by signature”, stop all new entries, and wait for a human to reconcile and clear. A result the chain proves did not land, or that failed, is recorded as rejected. Never auto-retry or resubmit the same order; a later decision is a new order and passes every check again.

Clause 8, replace the whole clause with:

    8. **No unproven live strategies and no return claims.** Live entries and exits run only under clause 2 and the written risk limits. A strategy trades live only at stage LIVE_ELIGIBLE, reached through BACKTEST and PAPER under thresholds in version-controlled config with evidence recorded in the ledger, and only while an arm record lists it. Promotion up to LIVE_ELIGIBLE and demotion are automatic; arming, and clearing a kill, halt, or UNKNOWN hold, are human-only. Paper parameter sets may be proposed by evaluation tooling and promoted in paper only under the autonomy level a human has set to autonomous-paper, within bounds declared in version-controlled config, with evidence recorded in the ledger and a one-operation rollback. Reports state facts with their data window, costs and trial count. No output claims an expected return.

Clause 9, replace the whole clause with:

    9. **Retired oracle is dry-run evidence only.** The grokbot-pumpfun engine (retired; pin 409e74c in docs/VENDOR_PIN.md, license at src/pumpgrok/engine/LICENSE-grokbot-pumpfun) is dry-run evidence only. Agents never set `mode: live`; the human sets it through the arm procedure. Never put keys in git, chat, or desk files. Never treat pipeline verdicts as RISK clearance or human approval. `tx_hash: dry_run` is not a fill. SNIPER (buys) and EXIT (sells) remain the only senders, and only after RISK clearance plus approval under clause 2. The desk bridge is `pumpgrok scout pipeline --candidates`.

Closing paragraph, replace "There is no live-capital level in these instructions." with:

    Live capital exists only through the arm procedure of clause 2; no default, overlay, or agent enables it.

## 2. Prompt and skill copies

`prompts/_shared/core-directives.xml`, both variants, item 1 append: ` In live mode only the separate desk-signer process holds a key, placed there by the human.`

Item 3, trading-seats variant, replace with:

    3. Human must explicitly approve the exact ticket (token CA + size + max slippage) for every live spend, or have signed an unexpired arm record that lists the strategy. Simulated paper fills follow the autonomy level a human sets with `pumpgrok state autonomy`.

Item 3, risk variant, replace with:

    3. Human must explicitly approve the exact ticket (token CA + size + max slippage) for every live spend, or have signed an unexpired arm record that lists the strategy. Simulated paper fills follow the autonomy level a human sets with `pumpgrok state autonomy`, recorded in the ledger.

`agents/*.md` and `prompts-assembled/*.xml` are regenerated only by `make prompts`. `agents/sniper.md` item 3 is regenerated from the same source.

`skills/desk-operating-model/SKILL.md` line 24, replace with:

    - A human must explicitly approve the exact ticket (token CA, size, max slippage) for every live spend, or sign an arm record once for the listed strategies. Simulated paper fills follow the autonomy level a human sets with `pumpgrok state autonomy`.

Line 39, replace with:

    - Engagement above `paper`: refused unless the live gate is open and an unexpired arm record exists. Without both, only `research` and `paper` exist on this desk.

## 3. Other quoting documents

- `docs/RISK_POLICY.md` rows 1, 2, 3, 8, 9: replace each quoted text with the verbatim clause above, and update the "Where it is enforced" cell to name `services/desk-signer` (rows 1, 3), `autonomous_live` and `execution/live/arm.py` (row 2), and the stage machine in `src/pumpgrok/promotion` (row 8). Section 3.3 and section 5: describe the arm record and the human-only clears. Section 6: add the signer key-custody rules (key file readable only by the signer uid, placed by the human, never in the desk environment, redacted from logs). Change-control item 4: replace "nothing in the current roadmap schedules it" with a pointer to this amendment and to `contracts/changes/v4-live-source.yaml`.
- `SECURITY.md` Key custody: replace "no key material exists in paper mode; nothing to custody" with: no key material exists in the desk; in live mode the key exists only in the desk-signer process, on a host the human provisions; the desk refuses key-like environment names as before.
- `docs/SAFETY_INVARIANTS.md` INV-S-01: the desk package never contains a signing symbol or a Solana client import, including `execution/live/`; the signer service is the only place.
- `.planning/PROJECT.md`: the live trading, custody, signing and venue out-of-scope rows move to in-scope with the sentence "dormant until the arm procedure; amendment 2026-10-28".
- A new frozen oracle `tests/safety/amendment_2026_10_28_frozen.txt` and its test extend the pattern of `tests/safety/test_constitution_amendment.py`; the 2026-10-25 oracle sections for clauses 2, 8, 3 and the core items are superseded by these sections and updated in the same change.

## Not in this amendment

- Enabling live: the arm and rollback runbook arms nothing; a human arms after the amendment and every live unit are merged and the live gate is open.
- Venue, fee and tip policy: engineering choices recorded in the v4 live design record (`C-risk-promotion-live.md`), not constitution text.
- Changes to clauses 4 to 7 or to any numeric limit.
- Regenerated prompts are produced by the repository generator (`make prompts`) and verified with `generate-templates --check`.
