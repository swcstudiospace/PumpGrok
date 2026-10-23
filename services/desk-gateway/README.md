# Desk Gateway

Thin stdlib-HTTP projection over the in-process pumpgrok tool registry
(TOOL-010, Phase 3 plan 03-05).

- `POST /mcp/<short>` serves JSON-RPC 2.0: `initialize`,
  `notifications/initialized`, `tools/list`, `tools/call`.
- `tools/list` is the seat roster plus `_core` with transport names
  (dots to underscores) and verbatim `description`/`inputSchema`.
- Per-seat bearer tokens via `DESK_GATEWAY_TOKEN_<SHORT>`, compared with
  `hmac.compare_digest`; cross-seat tokens answer 403.
- No tool logic lives in this service; run the suite with `uv run pytest -q`.

## Run

`make gateway` (from the repo root) or `python -m desk_gateway` serves the gateway in the
foreground. The registry is built from the operator settings, loaded the same way as the CLI
(`PUMPGROK_PROFILE` overlay, `PUMPGROK_CONFIG` TOML, `PUMPGROK_*` env). Process settings:

- `DESK_GATEWAY_HOST` (default `127.0.0.1`), `DESK_GATEWAY_PORT` (default `8787`)
- `DESK_GATEWAY_DATA_DIR` (default `var/desk`, which holds the kill latch and the ledger)
- `DESK_GATEWAY_REPO_ROOT` (default: this checkout)

`GET /healthz` answers `{"ok": true, "service": "desk-gateway"}` without a token. Live mode is
refused (exit 3); bad configuration exits 1 with the reason on stderr. The paper gateway is also
the `desk-gateway` service in `docker-compose.yml`.
