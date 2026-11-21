"""Paper-only operator console (A06 frontend, T1482-fe).

Server-rendered ASCII HTML for the seven ``ux.spec`` screens
(docs/design/ux-spec.json, tokens docs/design/tokens.json v1.0.0), bound to
the gateway contract docs/architecture/contracts/pumpgrok-gateway.yaml
v1.0.0 (digest 1491d8b4). Stdlib only: no JavaScript, no external asset,
no inline script, no client-side storage.

Design: Wave 3 frontend against the A03 blueprint and A04 tokens. No
brand guide and no real ``ds/*`` registry exist, so the ``ds/*`` refs in
ux-spec are provisional lofi primitives; this module reconciles them to
the five primitives below (Button, Badge, Alert, Table, Input) plus the
Progress frame used by loading states. A real registry, when it lands,
replaces CATALOG entries without changing the render functions.

Paper-only (ADR-0001, NFR-C1): no live-trade control, no seed phrase,
no private key, no fund movement surface exists on any screen.

Component catalog (consumed by A08; Storybook has no host in this repo,
so each entry is a data record plus the render function that story-tests
exercised):
- ds/Button@1.0.0  props: label: str, variant: "primary"|"secondary", id: str
- ds/Badge@1.0.0   props: text: str, variant: "status"|"success"
- ds/Alert@1.0.0   props: variant: "info"|"error", message: str (single-line ASCII)
- ds/Table@1.0.0   props: columns: list[str] (non-empty), rows: list[list[str]], id: str
- ds/Input@1.0.0   props: id: str, label: str, value: str = "", name: str = id
- Progress frame   props: label: str, percent: int 0..100 (determinate only)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from typing import Any

import httpx

CONTRACT_VERSION = "1.0.0"
CONTRACT_DIGEST_PREFIX = "1491d8b4"
TOKENS_VERSION = "1.0.0"
TARGET = "WCAG-2.2-AA"
MIN_CONTRAST = 5.69
ASCII_MAX = 127
EVENT_HASH_LENGTH = 64
PROGRESS_MAX = 100

# Screen data transcribed from docs/design/ux-spec.json (tests assert parity
# against that file, so any spec drift fails the suite).
STATES: tuple[str, ...] = (
    "default",
    "loading",
    "error.network",
    "error.validation",
    "success",
)


@dataclass(frozen=True)
class Screen:
    """One ux.spec screen: states, columns, focus order and frame copy."""

    screen_id: str
    title: str
    states: tuple[str, ...]
    columns: tuple[str, ...]
    focus_order: tuple[str, ...]
    empty_state: str
    empty_message: str
    success_message: str
    error_network: str
    error_validation: str


SCREENS: tuple[Screen, ...] = (
    Screen(
        screen_id="SCR-MilestoneTracker",
        title="Milestone tracker",
        states=(*STATES, "empty.milestones"),
        columns=("milestone", "units", "evidence", "owner"),
        focus_order=("filter-milestone", "refresh-tracker", "milestone-row-1", "milestone-row-2"),
        empty_state="empty.milestones",
        empty_message="No milestones match filter.",
        success_message="16 of 16 milestone groups tracked",
        error_network="ERROR code=1 msg=tracker-unavailable",
        error_validation="ERROR code=1 msg=invalid-filter",
    ),
    Screen(
        screen_id="SCR-GateDashboard",
        title="Gate dashboard",
        states=(*STATES, "empty.gates"),
        columns=("gate", "exit-code", "job", "status"),
        focus_order=("rerun-gates", "gate-row-1", "gate-row-2", "gate-row-3"),
        empty_state="empty.gates",
        empty_message="No gate runs recorded.",
        success_message="4 of 4 canonical gates exit 0",
        error_network="ERROR code=1 msg=ci-unavailable",
        error_validation="ERROR code=1 msg=invalid-gate-selection",
    ),
    Screen(
        screen_id="SCR-QualitySweeps",
        title="Quality sweeps",
        states=(*STATES, "empty.sweeps"),
        columns=("sweep", "check", "count", "result"),
        focus_order=("export-sweep-report", "sweep-row-1", "sweep-row-2"),
        empty_state="empty.sweeps",
        empty_message="No sweeps in scope.",
        success_message="0 open findings",
        error_network="ERROR code=1 msg=sweep-source-unavailable",
        error_validation="ERROR code=1 msg=invalid-sweep-selection",
    ),
    Screen(
        screen_id="SCR-ReplayDesk",
        title="Replay desk",
        states=(*STATES, "empty.replay"),
        columns=("run", "seed", "event-hash", "cycle"),
        focus_order=("seed", "run-replay-smoke", "replay-row-1"),
        empty_state="empty.replay",
        empty_message="No replay runs yet.",
        success_message="hash identical on rerun",
        error_network="ERROR code=1 msg=replay-data-unavailable",
        error_validation="ERROR code=1 msg=invalid-seed",
    ),
    Screen(
        screen_id="SCR-AuditEvidence",
        title="Audit evidence",
        states=(*STATES, "empty.evidence"),
        columns=("claim", "command", "exit-code", "output-hash"),
        focus_order=("rerun-transcript", "evidence-row-1", "evidence-row-2"),
        empty_state="empty.evidence",
        empty_message="No evidence recorded.",
        success_message="8 of 8 commands exit 0",
        error_network="ERROR code=1 msg=transcript-store-unavailable",
        error_validation="ERROR code=1 msg=invalid-claim-selection",
    ),
    Screen(
        screen_id="SCR-OperatorDocs",
        title="Operator docs",
        states=(*STATES, "empty.docs"),
        columns=("document", "command", "expected-exit", "actual-exit"),
        focus_order=("verify-doc-commands", "doc-row-1", "doc-row-2"),
        empty_state="empty.docs",
        empty_message="No documents in scope.",
        success_message="24 of 24 documented exit codes",
        error_network="ERROR code=1 msg=docs-unavailable",
        error_validation="ERROR code=1 msg=invalid-document-selection",
    ),
    Screen(
        screen_id="SCR-SafetyPaperOnly",
        title="Safety: paper only",
        states=(*STATES, "empty.receipts"),
        columns=("check", "precondition", "result", "exit-code"),
        focus_order=("check-live-refusal", "safety-row-1", "safety-row-2", "safety-row-3"),
        empty_state="empty.receipts",
        empty_message="No receipts recorded.",
        success_message="paper-only holds: 0 fund-moving paths",
        error_network="ERROR code=1 msg=safety-store-unavailable",
        error_validation="ERROR code=1 msg=invalid-check-selection",
    ),
)

STATES_BY_SCREEN: dict[str, tuple[str, ...]] = {
    screen.screen_id: screen.states for screen in SCREENS
}

FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "seed phrase",
    "private key",
    "live trade",
    "exec.live",
)


def screen_by_id(screen_id: str) -> Screen:
    """Return the screen spec or raise ValueError (unknown screen fails closed)."""
    for screen in SCREENS:
        if screen.screen_id == screen_id:
            return screen
    raise ValueError(f"unknown screen: {screen_id}")


def token_css(tokens: dict[str, Any]) -> str:
    """Build the :root custom properties from tokens.json v1.0.0.

    Every style declaration below the token layer references a var(--token);
    no raw colour or spacing literal appears outside this function.
    """
    color = tokens["color"]
    space = tokens["space"]
    size = tokens["size"]
    font = tokens["font"]
    motion = tokens["motion"]
    lines = [
        ":root{",
        f"--color-background-primary:{color['background']['primary']['$value']};",
        f"--color-text-default:{color['text']['default']['$value']};",
        f"--color-text-muted:{color['text']['muted']['$value']};",
        f"--color-action-primary:{color['action']['primary']['$value']};",
        f"--color-action-focus:{color['action']['focus']['$value']};",
        f"--color-status-success:{color['status']['success']['$value']};",
        f"--color-status-danger:{color['status']['danger']['$value']};",
        f"--color-status-warning:{color['status']['warning']['$value']};",
        f"--color-border-default:{color['border']['default']['$value']};",
        f"--space-0:{space['scale-0']['$value']};",
        f"--space-1:{space['scale-1']['$value']};",
        f"--space-2:{space['scale-2']['$value']};",
        f"--space-3:{space['scale-3']['$value']};",
        f"--space-4:{space['scale-4']['$value']};",
        f"--space-6:{space['scale-6']['$value']};",
        f"--space-8:{space['scale-8']['$value']};",
        f"--space-10:{space['scale-10']['$value']};",
        f"--space-12:{space['scale-12']['$value']};",
        f"--size-target-min:{size['target-min']['$value']};",
        f"--size-target-small:{size['target-small']['$value']};",
        f"--size-icon:{size['icon']['$value']};",
        f"--font-family-mono:{font['family-mono']['$value']};",
        f"--font-size-base:{font['size-base']['$value']};",
        f"--font-size-small:{font['size-small']['$value']};",
        f"--motion-fade:{motion['fade']['$value']};",
        f"--motion-slide:{motion['slide']['$value']};",
        f"--motion-max:{motion['max']['$value']};",
        "}",
    ]
    return "\n".join(lines)


def page_css() -> str:
    """Component styles; every value is a token reference var(--*)."""
    rules = [
        "body{background:var(--color-background-primary);color:var(--color-text-default);"
        "font-family:var(--font-family-mono);font-size:var(--font-size-base);"
        "margin:var(--space-6);padding:var(--space-0);}",
        "h1{font-size:var(--font-size-base);margin:var(--space-4);}",
        "h2{font-size:var(--font-size-small);margin:var(--space-3);}",
        "main{margin:var(--space-4);}",
        ".toolbar{margin:var(--space-4);}",
        ".toolbar label{margin:var(--space-2);}",
        ".toolbar input,.toolbar button{min-height:var(--size-target-min);"
        "padding:var(--space-2);margin:var(--space-2);}",
        "button{background:var(--color-action-primary);color:var(--color-background-primary);"
        "border:var(--space-0) solid var(--color-action-focus);}",
        "button:focus,input:focus{outline:var(--space-2) solid var(--color-action-focus);}",
        ".muted{color:var(--color-text-muted);font-size:var(--font-size-small);}",
        ".alert-error{color:var(--color-status-danger);font-size:var(--font-size-small);}",
        ".badge-success{color:var(--color-status-success);font-size:var(--font-size-small);}",
        ".badge-status{color:var(--color-action-primary);font-size:var(--font-size-small);}",
        "table{border-collapse:collapse;}",
        "th,td{border:var(--space-1) solid var(--color-border-default);"
        "padding:var(--space-2);font-size:var(--font-size-small);}",
        "progress{width:var(--space-12);height:var(--size-target-small);}",
        ".reduced-motion{transition:var(--motion-fade);}",
        "@media (prefers-reduced-motion:reduce){.reduced-motion{transition:none;}}",
    ]
    return "\n".join(rules)


def render_button(button_id: str, label: str, variant: str = "secondary") -> str:
    """ds/Button@1.0.0: a text button with a visible accessible name."""
    if variant not in ("primary", "secondary"):
        raise ValueError(f"unsupported Button variant: {variant}")
    if not label.strip():
        raise ValueError("Button label must be non-empty")
    return f'<button type="submit" id="{escape(button_id, quote=True)}">{escape(label)}</button>'


def render_input(input_id: str, label: str, value: str = "") -> str:
    """ds/Input@1.0.0: labelled text input (label element, never placeholder-only)."""
    if not input_id or not label.strip():
        raise ValueError("Input needs an id and a non-empty label")
    return (
        f'<label for="{escape(input_id, quote=True)}">{escape(label)}</label>'
        f'<input type="text" id="{escape(input_id, quote=True)}" '
        f'name="{escape(input_id, quote=True)}" value="{escape(value, quote=True)}">'
    )


def render_table(table_id: str, columns: tuple[str, ...], rows: list[list[str]]) -> str:
    """ds/Table@1.0.0: header row plus one scope=col header per column."""
    if not columns:
        raise ValueError("Table needs at least one column")
    head = "".join(f'<th scope="col">{escape(column)}</th>' for column in columns)
    body = []
    for index, row in enumerate(rows, start=1):
        if len(row) != len(columns):
            raise ValueError(f"row {index} has {len(row)} cells, expected {len(columns)}")
        cells = "".join(f"<td>{escape(cell)}</td>" for cell in row)
        body.append(f'<tr id="{escape(table_id, quote=True)}-row-{index}">{cells}</tr>')
    rows_html = "".join(body)
    table_attrs = escape(table_id, quote=True)
    head_html = f"<thead><tr>{head}</tr></thead>"
    return f'<table id="{table_attrs}">{head_html}<tbody>{rows_html}</tbody></table>'


def render_alert(variant: str, message: str) -> str:
    """ds/Alert@1.0.0: single-line ASCII message, role=alert on errors."""
    if variant not in ("info", "error"):
        raise ValueError(f"unsupported Alert variant: {variant}")
    if not message or "\n" in message or any(ord(char) > ASCII_MAX for char in message):
        raise ValueError("Alert message must be single-line ASCII")
    css_class = "alert-error" if variant == "error" else "alert-info"
    return f'<p class="{css_class}" role="alert">{escape(message)}</p>'


def render_badge(text: str, variant: str = "status") -> str:
    """ds/Badge@1.0.0: text status badge (never colour-only)."""
    if variant not in ("status", "success"):
        raise ValueError(f"unsupported Badge variant: {variant}")
    css_class = "badge-success" if variant == "success" else "badge-status"
    return f'<span class="{css_class}">{escape(text)}</span>'


def render_progress(label: str, percent: int) -> str:
    """Determinate progress frame for loading states (0..100)."""
    if not 0 <= percent <= PROGRESS_MAX:
        raise ValueError(f"percent out of range: {percent}")
    if not label.strip():
        raise ValueError("Progress needs a label")
    return (
        f'<label for="progressbar">{escape(label)}</label>'
        f'<progress id="progressbar" max="100" value="{percent}" '
        f'aria-valuenow="{percent}" aria-label="{escape(label, quote=True)}"></progress>'
    )


CATALOG: dict[str, dict[str, object]] = {
    "ds/Button@1.0.0": {"props": ["label: str", "variant: primary|secondary", "id: str"]},
    "ds/Badge@1.0.0": {"props": ["text: str", "variant: status|success"]},
    "ds/Alert@1.0.0": {"props": ["variant: info|error", "message: single-line ASCII str"]},
    "ds/Table@1.0.0": {
        "props": ["columns: non-empty list[str]", "rows: list[list[str]]", "id: str"]
    },
    "ds/Input@1.0.0": {"props": ["id: str", "label: str", "value: str", "name: str"]},
    "Progress": {"props": ["label: str", "percent: int 0..100"]},
}

_ROW_PREFIX: dict[str, str] = {
    "SCR-MilestoneTracker": "milestone",
    "SCR-GateDashboard": "gate",
    "SCR-QualitySweeps": "sweep",
    "SCR-ReplayDesk": "replay",
    "SCR-AuditEvidence": "evidence",
    "SCR-OperatorDocs": "doc",
    "SCR-SafetyPaperOnly": "safety",
}


def render_screen(screen: Screen, state: str, tokens: dict[str, Any], rows: list[list[str]]) -> str:
    """Render one screen in one ux.spec state as a complete ASCII HTML page."""
    if state not in screen.states:
        raise ValueError(f"state {state} not in ux.spec states for {screen.screen_id}")
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" '
        "content=\"default-src 'none'; style-src 'unsafe-inline'\">",
        f"<title>{escape(screen.title)} - PumpGrok operator console</title>",
        f"<style>{token_css(tokens)}\n{page_css()}</style>",
        "</head>",
        "<body>",
        f"<h1>{escape(screen.title)}</h1>",
        "<main>",
        "<h2>Controls</h2>",
        '<form method="get" action="">',
        '<div class="toolbar">',
    ]
    has_input = screen.screen_id in ("SCR-MilestoneTracker", "SCR-ReplayDesk")
    button_id = screen.focus_order[1] if has_input else screen.focus_order[0]
    if screen.screen_id == "SCR-MilestoneTracker":
        parts.append(render_input("filter-milestone", "Filter milestone"))
    if screen.screen_id == "SCR-ReplayDesk":
        parts.append(render_input("seed", "Seed"))
    parts.append(render_button(button_id, _primary_label(screen)))
    parts.append("</div>")
    parts.append("</form>")
    parts.append("<h2>Records</h2>")
    table_id = _ROW_PREFIX[screen.screen_id]
    if state in ("default", "success"):
        parts.append(render_table(table_id, screen.columns, rows))
    elif state == "loading":
        parts.append(render_progress("Loading data", 50))
    elif state == "error.network":
        parts.append(render_alert("error", screen.error_network))
    elif state == "error.validation":
        parts.append(render_alert("error", screen.error_validation))
    elif state == screen.empty_state:
        parts.append(f'<p class="muted">{escape(screen.empty_message)}</p>')
    if state == "success":
        parts.append(render_badge(screen.success_message, "success"))
    parts.append("</main>")
    parts.append("</body>")
    parts.append("</html>")
    page = "\n".join(parts)
    _assert_ascii_paper_only(page)
    return page


def _primary_label(screen: Screen) -> str:
    labels = {
        "SCR-MilestoneTracker": "Refresh tracker",
        "SCR-GateDashboard": "Rerun gates",
        "SCR-QualitySweeps": "Export sweep report",
        "SCR-ReplayDesk": "Run replay smoke",
        "SCR-AuditEvidence": "Rerun transcript",
        "SCR-OperatorDocs": "Verify doc commands",
        "SCR-SafetyPaperOnly": "Check live refusal",
    }
    label = labels.get(screen.screen_id)
    if label is None:
        raise ValueError(f"no primary label for {screen.screen_id}")
    return label


def _assert_ascii_paper_only(page: str) -> None:
    if any(ord(char) > ASCII_MAX for char in page):
        raise ValueError("page must be ASCII-only (NFR-A1)")
    lowered = page.lower()
    for forbidden in FORBIDDEN_SUBSTRINGS:
        if forbidden in lowered:
            raise ValueError(f"paper-only violation: page mentions {forbidden!r}")


@dataclass(frozen=True)
class Health:
    """GET /healthz schema: exactly {ok: bool, service: 'desk-gateway'}."""

    ok: bool
    service: str

    @classmethod
    def from_json(cls, payload: object) -> Health:
        if not isinstance(payload, dict):
            raise ValueError("Health payload must be an object")
        unknown = set(payload) - {"ok", "service"}
        if unknown:
            raise ValueError(f"Health payload has unknown fields: {sorted(unknown)}")
        ok_value = payload.get("ok")
        service = payload.get("service")
        if not isinstance(ok_value, bool) or service != "desk-gateway":
            raise ValueError("Health payload does not match the v1.0.0 schema")
        if "service" not in payload or "ok" not in payload:
            raise ValueError("Health payload is missing required fields")
        return cls(ok=ok_value, service=service)


@dataclass(frozen=True)
class JsonRpcResult:
    """POST /mcp/{short} JsonRpcResponse.result: exactly ok plus optional fields."""

    ok: bool
    error: str | None = None
    event_hash: str | None = None
    amount_lamports: int | None = None

    @classmethod
    def from_json(cls, payload: object) -> JsonRpcResult:
        if not isinstance(payload, dict):
            raise ValueError("JsonRpcResult must be an object")
        allowed = {"ok", "error", "event_hash", "amount_lamports"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"JsonRpcResult has unknown fields: {sorted(unknown)}")
        ok_value = payload.get("ok")
        if not isinstance(ok_value, bool):
            raise ValueError("JsonRpcResult.ok must be a boolean")
        event_hash = payload.get("event_hash")
        if event_hash is not None and not (
            isinstance(event_hash, str)
            and len(event_hash) == EVENT_HASH_LENGTH
            and all(char in "0123456789abcdef" for char in event_hash)
        ):
            raise ValueError("JsonRpcResult.event_hash must be 64 lowercase hex chars")
        amount = payload.get("amount_lamports")
        amount_ok = amount is None or (isinstance(amount, int) and not isinstance(amount, bool))
        if not amount_ok:
            raise ValueError("JsonRpcResult.amount_lamports must be an integer")
        return cls(
            ok=ok_value, error=payload.get("error"), event_hash=event_hash, amount_lamports=amount
        )


class GatewayClient:
    """Typed client for pumpgrok-gateway.yaml v1.0.0 (GET /healthz, POST /mcp/{short}).

    Every request and response is validated against the contract: unknown
    fields are rejected fail-closed and money stays integer base units.
    The per-seat bearer token is sent in the Authorization header only and
    is never stored on disk, in the page, or in a log line.
    """

    def __init__(self, base_url: str, timeout_s: float = 10.0) -> None:
        cleaned = base_url
        if cleaned.endswith("/"):
            cleaned = cleaned[:-1]
        if not cleaned.startswith(("http://127.0.0.1", "http://localhost")):
            raise ValueError(f"base_url must be a loopback gateway: {base_url}")
        self._base_url = cleaned
        self._timeout_s = timeout_s

    def health(self) -> Health:
        """GET /healthz without a token (operationId getHealthz)."""
        with httpx.Client(timeout=self._timeout_s) as client:
            response = client.get(f"{self._base_url}/healthz")
            response.raise_for_status()
            payload = response.json()
        return Health.from_json(payload)

    def call(
        self, short: str, token: str, method: str, params: dict[str, Any] | None = None
    ) -> JsonRpcResult:
        """POST /mcp/{short} JSON-RPC tools/list or tools/call (postMcpToolsCall)."""
        if method not in ("tools/list", "tools/call"):
            raise ValueError(f"method {method} is not in the v1.0.0 contract")
        if not short or not all(char in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in short):
            raise ValueError(f"seat short does not match ^[a-z0-9-]+$: {short}")
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": "console", "method": method}
        if params is not None:
            body["params"] = params
        with httpx.Client(timeout=self._timeout_s) as client:
            response = client.post(
                f"{self._base_url}/mcp/{short}",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("JsonRpcResponse must be an object")
        return JsonRpcResult.from_json(payload.get("result"))


def load_tokens(path: str) -> dict[str, Any]:
    """Load tokens.json v1.0.0 from disk (fails closed on a bad file)."""
    with open(path, "rb") as handle:
        payload = json.loads(handle.read().decode("utf-8"))
    if not isinstance(payload, dict) or "color" not in payload:
        raise ValueError(f"not a v1.0.0 tokens file: {path}")
    return payload
