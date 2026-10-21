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
