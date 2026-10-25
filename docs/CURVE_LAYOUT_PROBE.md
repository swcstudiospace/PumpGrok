# Bonding-curve layout probe (INT-10, R65)

Status: ASSUMED
Error: probe not run in this worktree: live network call deferred to the orchestrator after merge; run `uv run python scripts/probe_curve_layout.py` against the configured public RPC to refresh this fixture; layout stays ASSUMED

Endpoint: https://api.mainnet-beta.solana.com
Method: getAccountInfo (read-only, no keys)
Layout: ASSUMED until a live probe decodes under it; RPC-derived entries fail closed with data_unavailable.
