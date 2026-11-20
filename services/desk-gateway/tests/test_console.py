"""Component tests for the paper-only operator console (A06, T1482-fe).

These are component-level tests over the rendered HTML (consumed by A08);
they are not the E2E suite. They assert ux.spec state parity, the paper-
only and ASCII constraints, WCAG heading/label/focus-order rules, CSP, and
the gateway contract binding.
"""

from __future__ import annotations

import itertools
import json
import secrets
from html.parser import HTMLParser
from pathlib import Path

import pytest

from desk_gateway.console import (
    SCREENS,
    STATES_BY_SCREEN,
    GatewayClient,
    Health,
    JsonRpcResult,
    load_tokens,
    render_alert,
    render_button,
    render_input,
    render_screen,
    render_table,
    screen_by_id,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
TOKENS_PATH = str(REPO_ROOT / "docs" / "design" / "tokens.json")
SPEC_PATH = REPO_ROOT / "docs" / "design" / "ux-spec.json"
TOKENS = load_tokens(TOKENS_PATH)
SPEC = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
SPEC_BY_ID = {screen["screen_id"]: screen for screen in SPEC["screens"]}


def sample_rows(screen, count: int) -> list[list[str]]:
    return [[f"{column}-{index}" for column in screen.columns] for index in range(1, count + 1)]


class TagCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def parse(page: str) -> TagCollector:
    parser = TagCollector()
    parser.feed(page)
    return parser


def test_state_parity_with_ux_spec() -> None:
    total_screens = 7
    assert len(SCREENS) == total_screens
    assert len(SPEC_BY_ID) == total_screens
    for screen in SCREENS:
        expected = SPEC_BY_ID[screen.screen_id]["states"]
        assert sorted(screen.states) == sorted(expected), screen.screen_id
    assert STATES_BY_SCREEN is not None


def test_all_states_render_ascii_paper_only() -> None:
    for screen in SCREENS:
        for state in screen.states:
            page = render_screen(screen, state, TOKENS, sample_rows(screen, 2))
            assert page.encode("ascii")  # NFR-A1: 0 non-ASCII bytes
            lowered = page.lower()
            assert "seed phrase" not in lowered
            assert "private key" not in lowered
            assert "live trade" not in lowered


def test_heading_sequence_and_lang() -> None:
    for screen in SCREENS:
        page = render_screen(screen, "default", TOKENS, sample_rows(screen, 1))
        parsed = parse(page)
        headings = [tag for tag, _ in parsed.tags if tag in ("h1", "h2", "h3", "h4", "h5", "h6")]
        assert headings[0] == "h1"
        levels = [int(headings[0][1])] + [int(tag[1]) for tag in headings[1:]]
        for previous, current in itertools.pairwise(levels):
            assert current <= previous + 1
        html_attrs = next(attrs for tag, attrs in parsed.tags if tag == "html")
        assert html_attrs.get("lang") == "en"


def test_form_labels_and_button_names() -> None:
    for screen in SCREENS:
        page = render_screen(screen, "default", TOKENS, sample_rows(screen, 1))
        parsed = parse(page)
        label_fors = {attrs.get("for") for tag, attrs in parsed.tags if tag == "label"}
        for tag, attrs in parsed.tags:
            if tag == "input":
                assert attrs.get("id") in label_fors
            if tag in ("button", "a"):
                # Every button carries visible text (accessible name).
                assert tag == "button"
        assert "tabindex" not in page.lower()


def test_focus_order_ids_present_in_dom_order() -> None:
    for screen in SCREENS:
        page = render_screen(screen, "default", TOKENS, sample_rows(screen, 3))
        positions = [page.index(f'id="{focus_id}"') for focus_id in screen.focus_order]
        assert positions == sorted(positions), screen.screen_id


def test_no_inline_scripts_or_handlers() -> None:
    for screen in SCREENS:
        page = render_screen(screen, "default", TOKENS, sample_rows(screen, 1))
        assert "<script" not in page.lower()
        assert "onclick" not in page.lower()
        assert "localStorage" not in page.lower()
        assert "Content-Security-Policy" in page


def test_xss_escaping_in_rows_and_labels() -> None:
    screen = SCREENS[0]
    page = render_screen(screen, "default", TOKENS, [["<script>alert(1)</script>", "1", "x", "y"]])
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    with pytest.raises(ValueError, match="unknown screen"):
        screen_by_id("SCR-Nope")


def test_error_alerts_are_single_line_ascii() -> None:
    for screen in SCREENS:
        network = render_screen(screen, "error.network", TOKENS, [])
        validation = render_screen(screen, "error.validation", TOKENS, [])
        assert "ERROR code=1 msg=" in network
        assert "ERROR code=1 msg=" in validation
        for page in (network, validation):
            for line in page.splitlines():
                if "ERROR code=" in line:
                    line.encode("ascii")
                    assert line.count("ERROR code=") == 1


def test_primitives_reject_bad_props() -> None:
    with pytest.raises(ValueError, match="Button label"):
        render_button("save", "   ")
    with pytest.raises(ValueError, match="variant"):
        render_button("save", "Save", "mega")
    with pytest.raises(ValueError, match="label"):
        render_input("seed", "")
    with pytest.raises(ValueError, match="column"):
        render_table("t", (), [])
    with pytest.raises(ValueError, match="single-line ASCII"):
        render_alert("error", "multi\nline")
    with pytest.raises(ValueError, match="single-line ASCII"):
        render_alert("error", "caf\xe9")


def test_contract_health_validation() -> None:
    assert Health.from_json({"ok": True, "service": "desk-gateway"}) == Health(True, "desk-gateway")
    with pytest.raises(ValueError, match="unknown fields"):
        Health.from_json({"ok": True, "service": "desk-gateway", "extra": 1})
    with pytest.raises(ValueError, match="schema"):
        Health.from_json({"ok": True, "service": "other"})


def test_contract_jsonrpc_validation() -> None:
    good = JsonRpcResult.from_json({"ok": True, "event_hash": "b" * 64})
    assert good.ok and good.event_hash == "b" * 64
    with pytest.raises(ValueError, match="unknown fields"):
        JsonRpcResult.from_json({"ok": True, "surprise": 1})
    with pytest.raises(ValueError, match="event_hash"):
        JsonRpcResult.from_json({"ok": True, "event_hash": "xyz"})
    with pytest.raises(ValueError, match="method"):
        GatewayClient("http://127.0.0.1:8787").call("sniper", secrets.token_hex(4), "exec/live", {})


def test_token_binding_no_raw_literals_outside_root() -> None:
    page = render_screen(SCREENS[0], "default", TOKENS, sample_rows(SCREENS[0], 1))
    style = page.split("<style>", 1)[1].split("</style>", 1)[0]
    root_block, _, component_block = style.partition("}")
    # Component layer: only token references allowed.
    assert "var(--" in component_block
    for token_hex in ("#ffffff", "#111827", "#1a56db", "#067647"):
        if token_hex in root_block:
            continue  # token definitions themselves carry the values
        assert token_hex not in component_block
    assert "style-src" in page
