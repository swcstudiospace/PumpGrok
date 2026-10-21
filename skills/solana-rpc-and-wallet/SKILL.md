---
name: solana-rpc-and-wallet
description: Safe patterns for reading balances, token accounts, metadata, Token-2022 extensions, and managing the throwaway wallet connection without ever handling private keys.
bots:
  - bot-02-risk
  - bot-04-sniper
gates:
  - G-3
---

# Solana RPC and Wallet

## L1 - Summary
Safe read patterns for balances, token accounts, metadata, and Token-2022 extensions, plus the throwaway-wallet connection rules. Reads chain state; never handles private keys.

## L2 - Method
1. Wallet rules (non-negotiable):
   - Only a dedicated throwaway wallet (at most $200 USDC plus SOL for fees).
   - Private keys and seed phrases never enter chat, files, or memory.
   - Connection is performed by the human via screen hand-off only.
   - The public address is recorded in `desk.md` after successful connection.
2. Priority fees and compute: prefer the output of `tools/priority_fee.py`. Cap the maximum fee so a spike cannot drain the wallet.

## Failure modes
- Key material requested, offered, or pasted: abort the flow and escalate.
- Wallet connection outside human hand-off: refuse; no seat connects a wallet itself.
- Unbounded fee: any send path without a fee cap is refused.

## References
- Tools: `tools/priority_fee.py` (`--rpc`, `--percentile`, `--multiplier`); `tools/authority_check.py`
- Gate: G-3; constitution: `prompts/_shared/core-directives.xml`
