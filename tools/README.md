# Tools

Lightweight Python helpers that skills can call for reliable, structured data.
All tools are **read / prepare only**. They never sign, send, or handle private keys.

| Tool | Purpose | Primary users |
|------|---------|---------------|
| `jupiter_quote.py` | Best Jupiter route + expected out amount | SNIPER, EXIT |
| `authority_check.py` | Mint / freeze authority + Token-2022 flags | RISK |
| `priority_fee.py` | Median + recommended prioritization fee | SNIPER, EXIT |
| `ticket_helper.py` | Next ticket ID + optional proposal skeleton | CHIEF |
| `paper_sim.py` | Paper-trading fill logger | CHIEF, EXIT, strategy lab |
| `holder_check.py` | Top-holder concentration snapshot | WHALE, RISK |

## Common conventions

- CLI interface, clean JSON on stdout
- Fail closed (`"ok": false` + error message)
- Prefer a paid / private RPC via `--rpc` when available
- No private keys, no signing, no automatic sends

## Quick examples

```bash
# Quote
python tools/jupiter_quote.py \
  --input-mint So11111111111111111111111111111111111111112 \
  --output-mint <TOKEN_MINT> \
  --amount 100000000 \
  --slippage-bps 100

# Authority check
python tools/authority_check.py --mint <TOKEN_MINT>

# Priority fee
python tools/priority_fee.py --multiplier 1.25 --max-micro 50000

# Next ticket
python tools/ticket_helper.py --write

# Paper fill
python tools/paper_sim.py --action buy --ticket SOL-20260827-001 \
  --mint <TOKEN_MINT> --size-usd 25 --price 0.000012 --slippage-bps 80

# Holder concentration
python tools/holder_check.py --mint <TOKEN_MINT> --limit 20
```

## Dependency

Most tools need only the `requests` package:

```bash
pip install requests
```

## Safety

These tools improve reliability and speed. They do **not** change the desk’s security model:

- Human must still approve every real spend by exact ticket ID
- RISK KILL remains absolute
- SNIPER / EXIT still follow the single-send rule
- Throwaway wallet only; no seed phrases ever enter the system
- Paper mode never touches real capital
