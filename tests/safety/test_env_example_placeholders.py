"""Only placeholders in .env.example (INV-S-06).

Every key starts with ``PUMPGROK_``; no key is named like a private key;
every value is a placeholder. Bare numeric literals (``20``,
``20260101``) are accepted as documented non-secret numerics: they match
no G-3 secret shape and the secrets gate is the backstop for real key
material. Anything else must match the invariant placeholder grammar.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"

PLACEHOLDER_RE = re.compile(r"^(<[a-z_-]+>|changeme|0|1|false|true|paper|)$")
NUMERIC_RE = re.compile(r"^[0-9]+(\.[0-9]+)?$")

FORBIDDEN_KEY_PARTS = (
    "PRIVATE_KEY",
    "SECRET_KEY",
    "SEED",
    "MNEMONIC",
    "PHANTOM",
    "WALLET_SECRET",
    "KEYPAIR",
)


def _pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, rest = stripped.partition("=")
        # Values carry no `#` today; a trailing comment starts at the first
        # `#`, so strip it and surrounding whitespace before matching.
        value = rest.split("#", maxsplit=1)[0].strip()
        pairs.append((key.strip(), value))
    return pairs


def test_env_example_has_only_placeholders() -> None:
    """INV-S-06: placeholder keys and values only, no private-key names."""
    assert ENV_EXAMPLE.is_file(), ".env.example is missing"
    pairs = _pairs()
    assert pairs, ".env.example defines no keys"
    problems: list[str] = []
    for key, value in pairs:
        if not key.startswith("PUMPGROK_"):
            problems.append(f"key without PUMPGROK_ prefix: {key}")
        upper = key.upper()
        if upper == "PUMPGROK_REPLAY__SEED":
            pass
        elif any(part in upper for part in FORBIDDEN_KEY_PARTS):
            problems.append(f"forbidden key name: {key}")
        if PLACEHOLDER_RE.fullmatch(value) is None and NUMERIC_RE.fullmatch(value) is None:
            problems.append(f"non-placeholder value for {key}: {value!r}")
    assert problems == []


@pytest.mark.parametrize(
    ("key", "value", "bad"),
    [
        ("PUMPGROK_MODE", "paper", False),
        ("PUMPGROK_GROK__API_KEY", "", False),
        ("PUMPGROK_RISK__MAX_TRADES_PER_DAY", "20", False),
        ("WALLET_PRIVATE_KEY", "changeme", True),
        (
            "PUMPGROK_SOME__PRIVATE_KEY",
            "changeme",
            True,
        ),  # pragma: allowlist secret: forbidden-name probe
        ("PUMPGROK_MODE", "live", True),
        (
            "PUMPGROK_GROK__API_KEY",
            "xai-abcdef1234567890abcdef1234567890",
            True,
        ),  # pragma: allowlist secret: synthetic secret shape
    ],
)
def test_pair_is_classified(key: str, value: str, bad: bool) -> None:
    problems: list[str] = []
    if not key.startswith("PUMPGROK_"):
        problems.append("prefix")
    if any(part in key.upper() for part in FORBIDDEN_KEY_PARTS):
        problems.append("forbidden")
    if PLACEHOLDER_RE.fullmatch(value) is None and NUMERIC_RE.fullmatch(value) is None:
        problems.append("value")
    assert bool(problems) is bad, problems
