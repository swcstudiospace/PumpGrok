"""RISK-007 guard: the desk cannot manipulate venue or social rails (SC4).

Proves the manipulation boundary in one owned file: the social directory
exists with real content (non-vacuous) and is scanned for write-verb and
manipulation helpers with the SC4 literal plus an AST pass; every POST target
in tools/notify is read from the configured allowlist setting, never a public
social endpoint; skills/browser-ops carries no posting or wallet-UI procedure
(refusal-framed lines only); no registered catalog tool and no roster entry
carries a manipulation name.
"""

from __future__ import annotations

import ast
import random
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import httpx

from pumpgrok.config.settings import NotifySettings
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.tools import build_registry, register_read_tools
from pumpgrok.tools.onchain.rpc import RpcClient

REPO = Path(__file__).resolve().parents[2]
SOCIAL = REPO / "src" / "pumpgrok" / "tools" / "social"
NOTIFY = REPO / "src" / "pumpgrok" / "tools" / "notify"
ROSTERS = REPO / "contracts" / "tool-rosters"
BROWSER_OPS = REPO / "skills" / "browser-ops"

# SC4 literal, verbatim: bare write verbs or a write-verb method argument.
_SC4 = re.compile(r"\b(post|put|patch|delete)\b|method=['\"](POST|PUT|PATCH|DELETE)")

# RISK-007 manipulation stems (substring match inside social/, registry and rosters).
_STEMS = (
    "post",
    "reply",
    "like",
    "follow",
    "dm",
    "broadcast",
    "wash",
    "volume",
    "promote",
    "shill",
)

# Public social endpoints: no notify POST target may name one. The Telegram
# Bot API host (api.telegram.org) is the allowlisted sink, not a social
# endpoint, so it is deliberately absent here.
_SOCIAL_ENDPOINT_RE = re.compile(
    r"(x\.com|twitter\.com|discord\.(com|gg)|t\.me|pump\.fun|facebook\.com|instagram\.com|tiktok\.com|youtube\.com|reddit\.com)",
    re.IGNORECASE,
)

# Posting-verb procedures forbidden in browser-ops skill text (word match).
_SKILL_POST_RE = re.compile(
    r"\b(post|publish|reply|like|follow|broadcast|promote)\b", re.IGNORECASE
)

# Wallet-UI procedures: only allowed when the same line frames them as a refusal.
_WALLET_UI_RE = re.compile(
    r"\b(connect\s+(?:a\s+|the\s+|your\s+)?wallet"
    r"|enter\s+(?:your\s+|the\s+|a\s+)?(?:credentials|seed|private\s+key)"
    r"|seed\s+phrase|private\s+key"
    r"|bypass\s+(?:the\s+|a\s+)?(?:captcha|2fa|security|login)"
    r"|sign\s+(?:the\s+|a\s+)?transaction)\b",
    re.IGNORECASE,
)
_REFUSAL_RE = re.compile(
    r"\b(never|refuse[sd]?|stop|hand to human|hand the screen|escalate[sd]?|BLIND|cannot|do not|don't)\b",
    re.IGNORECASE,
)


def test_social_directory_is_non_empty() -> None:
    assert SOCIAL.is_dir(), "tools/social/ must exist for the SC4 check to mean anything"
    py_files = sorted(p for p in SOCIAL.glob("*.py") if p.name != "__pycache__")
    assert len(py_files) >= 1, "tools/social/ must hold at least one module"
    assert any(p.read_text(encoding="utf-8").strip() for p in py_files)


def test_social_has_no_write_verbs_sc4_literal() -> None:
    for path in sorted(SOCIAL.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        hits = _SC4.findall(text)
        assert not hits, f"{path.name} matches the SC4 write-verb check: {hits[:3]}"


def test_social_has_no_manipulation_helpers() -> None:
    for path in sorted(SOCIAL.glob("*.py")):
        lowered = path.read_text(encoding="utf-8").lower()
        for stem in _STEMS:
            assert stem not in lowered, f"{path.name} mentions manipulation stem {stem!r}"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("post", "put", "patch", "delete"):
                raise AssertionError(f"{path.name} calls write-verb method {node.attr}")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in (*_STEMS, "post", "put", "patch", "delete"), (
                    f"{path.name} defines manipulation helper {node.name}"
                )


def test_registered_tools_carry_no_manipulation_names() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no network in the skeleton guard")

    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    rpc = RpcClient(
        ["https://rpc.invalid"],
        httpx.AsyncClient(transport=transport),
        FixtureClock(start=1469918176.385),
        rng=random.Random(21),
    )
    reg, _ = build_registry(clock=FixtureClock(start=1469918176.385), rng=random.Random(22))
    register_read_tools(reg, rpc)
    assert reg.names(), "registry must hold tools for the name scan to mean anything"
    for name in reg.names():
        for stem in _STEMS:
            assert stem not in name, f"tool {name} carries manipulation stem {stem!r}"
        spec = reg.spec(name)
        assert spec.side_effect is SideEffect.READ


def _code_string_constants(path: Path, text: str) -> list[str]:
    """String literals in code, excluding docstrings (module, class, function)."""
    tree = ast.parse(text, filename=str(path))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_roster_names_carry_no_manipulation_names() -> None:
    """No roster YAML entry matches a manipulation stem (INV-S-07)."""
    files = sorted(ROSTERS.glob("*.yaml"))
    assert files, "contracts/tool-rosters/ must hold rosters for the name scan to mean anything"
    checked = 0
    for path in files:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        tools = (data or {}).get("tools", [])
        assert tools, f"{path.name} must declare tools for the name scan to mean anything"
        for entry in tools:
            name = entry.get("name", "")
            assert name, f"{path.name} has a nameless tool entry"
            checked += 1
            for stem in _STEMS:
                assert stem not in name, (
                    f"{path.name} rosters manipulation name {name!r} (stem {stem!r})"
                )
    assert checked >= 30, f"roster scan covered only {checked} tools"


def test_notify_posts_only_to_allowlisted_destinations() -> None:
    """Every notify POST target comes from config, never a public social endpoint."""
    notify_files = sorted(NOTIFY.glob("*.py"))
    assert len(notify_files) >= 3, "tools/notify/ must hold modules for the scan to mean anything"
    post_calls: list[tuple[Path, ast.Call, str]] = []
    for path in notify_files:
        text = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text, filename=str(path))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "post"
            ):
                post_calls.append((path, node, text))
    assert post_calls, (
        "tools/notify/ must contain POST call sites for the allowlist check to mean anything"
    )
    for path, node, text in post_calls:
        assert node.args, f"{path.name}:{node.lineno} POST without a target"
        assert not isinstance(node.args[0], ast.Constant), (
            f"{path.name}:{node.lineno} POST target must be read from config, never a literal"
        )
        segment = ast.get_source_segment(text, node) or ""
        assert not _SOCIAL_ENDPOINT_RE.search(segment), (
            f"{path.name}:{node.lineno} POST target names a public social endpoint"
        )
    for path in notify_files:
        for literal in _code_string_constants(path, path.read_text(encoding="utf-8")):
            assert not _SOCIAL_ENDPOINT_RE.search(literal), (
                f"{path.name} names a public social endpoint in a string literal"
            )
    notifier_text = (NOTIFY / "notifier.py").read_text(encoding="utf-8")
    assert "partition_destinations" in notifier_text, "fan-out must gate through the allowlist"
    assert "allowlist" in NotifySettings.model_fields, "the allowlist setting must exist"


def test_browser_ops_skill_has_no_posting_or_wallet_procedure() -> None:
    """browser-ops skill text states detection only (R39); wallet UI is refusal-framed."""
    skill_files = sorted(BROWSER_OPS.glob("*.md"))
    assert skill_files, "skills/browser-ops/ must hold skill text for the scan to mean anything"
    assert any(path.read_text(encoding="utf-8").strip() for path in skill_files)
    for path in skill_files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            post = _SKILL_POST_RE.search(line)
            assert post is None, f"{path.name}:{lineno} posting-verb procedure {post.group(0)!r}"
            wallet = _WALLET_UI_RE.search(line)
            if wallet is not None:
                assert _REFUSAL_RE.search(line) is not None, (
                    f"{path.name}:{lineno} wallet-UI text without refusal framing: {wallet.group(0)!r}"
                )
