---
name: risk-audit
description: Absolute safety gate for every Solana token. Runs a fail-closed checklist and returns only CLEAR, CONDITIONAL, or KILL. Used exclusively by the RISK Bot. A KILL cannot be overridden.
bots:
  - bot-05-rug
gates:
  - G-2
required_tools:
  - safety.score_report
  - onchain.authorities
  - onchain.top_holders
required_data:
  - solana_rpc
permissions:
  max_side_effect: read
  network: true
  filesystem: none
---

# Risk Audit

## L1 - Summary
The absolute safety gate for every token. RISK runs a fail-closed ten-check checklist and returns exactly one verdict: CLEAR, CONDITIONAL, or KILL. A KILL ends the token path permanently and cannot be overridden.

## L2 - Method
1. Run every check, every time, with the preferred tool path (operator registry;
`pumpgrok tools <id> --help` prints the schema):
```bash
pumpgrok tools onchain.authorities --help
```
Parse the JSON. If `hasMintAuthority` or `hasFreezeAuthority` is true, that is a strong KILL signal.
2. Mandatory checklist:
   - Mint authority: must be null / revoked.
   - Freeze authority: must be null / revoked.
   - LP status: burned or locked for 6-12 months; quantify the percentage.
   - Sell / transfer tax: preferably 0 %; hard fail above 5-10 %.
   - Honeypot / cannot-sell indicators.
   - Top-10 holders (ex-LP) concentration: flag above 20-25 %.
   - Bundler / insider cluster detection.
   - Deployer wallet history if visible.
   - Token-2022 extensions: document any.
   - Liquidity depth relative to intended size.
3. Emit the output schema:
```
LEAD / TICKET-ID: ...
Verdict: CLEAR | CONDITIONAL | KILL
Residual Risks:
1. ...
Evidence: [source plus UTC]
Conditions (if CONDITIONAL): ...
Self-Audit: All 10 checks completed: YES / NO
```

## Failure modes
- Any check cannot be completed with live data: the verdict is not CLEAR. Incomplete evidence is CONDITIONAL at best, KILL when the gap hides catastrophic risk.
- Narrative or FOMO pressure to soften: never soften a KILL; no other Bot may proceed past one.
- Skipped or approximated check: re-run. The self-audit line must read YES.

## References
- Tools: `onchain.authorities`, `onchain.top_holders` (operator registry); port: `src/pumpgrok/tools/onchain/`
- Gate: G-2; veto: absolute, non-appealable (`desk-operating-model`)
