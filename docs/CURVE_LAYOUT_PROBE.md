# Bonding-curve layout probe (INT-10, R65)

Status: ASSUMED
Error: no bonding-curve account configured; set BONDING_CURVE_ACCOUNT or pass --account <pubkey>; no RPC call made; layout stays ASSUMED

Endpoint: https://api.mainnet-beta.solana.com
Method: getAccountInfo (read-only, no keys)
Layout: ASSUMED until a live probe decodes under it; RPC-derived entries fail closed with data_unavailable.

This probe never writes VERIFIED. DECODED_PENDING_REVIEW means the account decoded under the ASSUMED layout and awaits human review. A human sets VERIFIED only through a reviewed change to this doc, made outside the probe after checking the decoded values.
