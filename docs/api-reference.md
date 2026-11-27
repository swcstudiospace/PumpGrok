# PumpGrok gateway API reference

Contract: docs/architecture/contracts/pumpgrok-gateway.yaml v1.0.0.
Base URL: http://127.0.0.1:8787. Paper-only. ASCII only.

## Endpoints

### GET /healthz

Liveness probe without a token. Operation ID getHealthz.

- Response 200: gateway is up, content type application/json, body holds
  the Health schema.
- Response 503: gateway is not serving, body holds the Refusal schema.
- No request body. No token.

### POST /mcp/{short}

JSON-RPC tools/list and tools/call for one seat roster. Operation ID
postMcpToolsCall.

- Path parameter short: type string, pattern ^[a-z0-9-]+$, required.
- Auth runs before the body is read. No token is 401. Cross-seat token
  is 403. Seat without a configured token is 503 fail-closed. Body over
  1 MiB is 413.
- Request body is application/json and holds the JSON-RPC object with
  name and arguments. Every tool input forbids extra fields, so an
  unknown field is rejected with a named error and exit code 1.
- Uncertain state denies ordering and returns a named refusal with
  0 fills.
- Money is integer base units. Timestamps are ISO 8601 UTC from the
  injected Clock only.
- Live mode is refused with exit 3. 0 live adapters register.

## Coverage

Total endpoints from contract: 2. Documented endpoints: 2.
GET /healthz and POST /mcp/{short} are both documented.
Covered percentage is 100. Undocumented list is empty.
Unmatched documented list is empty.
