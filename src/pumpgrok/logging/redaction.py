"""Redaction for log messages and structured data (FOUNDATION_STACK 5.3, OBS-001).

Value-based: the G-3 trading families and the precedent `private_key`, `jwt` and
`conn_string` families (programming-desk `ci/gates/check_secrets.py`), bearer tokens and
secret-named `key=value` pairs (free text and URL queries) are masked wherever they occur
in a string. Key-based: any data key shaped like a secret name has its value
replaced with `[redacted]`. A masked span keeps its first four characters, the
`_redact` shape of `check_secrets.py:123-126`.

Applied by :class:`RedactionFilter` on every handler before formatting, so the
JSON and text formatters only ever see redacted text.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[redacted]"
KEEP = 4

# Key names that carry secrets: check_secrets.py SECRET_NAME_RE, plus the trading
# names from FOUNDATION_STACK 5.3 (keypair, mnemonic, seed, wallet_secret) and the
# auth names (authorization, passphrase, cookie). camelCase names are split first.
SECRET_NAME_RE = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9]|_)(?:secret|password|passwd|pwd|token|api[_-]?key|apikey|auth|"
    r"authorization|passphrase|cookie|credential|private[_-]?key|access[_-]?key|"
    r"client[_-]?secret|encryption[_-]?key|keypair|mnemonic|seed|wallet[_-]?secret)"
    r"(?:[^A-Za-z0-9]|_|$)"
)
_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

# Secret-named `key=value` pairs in free text and URL queries: `token=...`, `api_key=...&`,
# `"password": "..."`, `Authorization: Basic ...`. The key word must end at a word boundary,
# so `author=` and `tokenizer=` stay readable. A `Bearer` or `Basic` scheme stays visible;
# only the credential after it is masked (the `value` group).
_SECRET_KEY_WORD = (
    # Regex alternation of secret key words for the key=value pattern; not a credential.
    r"(?i:secret|password|passwd|pwd|token|api[_-]?key|apikey|auth|authorization|passphrase|"  # noqa: S105
    r"cookie|credential|private[_-]?key|access[_-]?key|client[_-]?secret|"
    r"encryption[_-]?key|keypair|mnemonic|seed|wallet[_-]?secret)"
)
KEY_VALUE_PATTERN = (
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]*" + _SECRET_KEY_WORD + r"(?i:s)?(?![a-z])[A-Za-z0-9_-]*"
    r"(?P<sep>[\"']?\s*[=:]\s*[\"']?)"
    r"(?P<scheme>(?i:bearer|basic)\s+)?"
    r"(?!\[redacted\])(?P<value>[^\s\"'&<>,;}]{4,})"
)

# Value shapes. The G-3 trading families are the synthetic-testable set from FOUNDATION_STACK
# section 4; the last three are the precedent private_key, jwt and conn_string families.
VALUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?"
        r"(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)",  # private_key_block
        r"\b[1-9A-HJ-NP-Za-km-z]{86,88}\b",  # solana_base58_key
        r"\[\s*(?:\d{1,3}\s*,\s*){63}\d{1,3}\s*\]",  # solana_json_keypair
        r"(?i)helius(?:-rpc)?\.com/[^\s\"']*api-key=[A-Za-z0-9-]{20,}",  # helius_url_key
        r"(?i)[a-z0-9-]+\.solana-mainnet\.quiknode\.pro/[A-Za-z0-9]{20,}",  # quicknode_url
        r"(?:(?<=bot)|\b)\d{8,10}:[A-Za-z0-9_-]{35}\b",  # telegram_bot_token (also /bot<token>/)
        r"\bxai-[A-Za-z0-9]{32,}\b",  # xai_key
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",  # private_key
        r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",  # jwt
        r"(?i)\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp)://"
        r"[^:\s/]+:[^@\s/]+@",  # conn_string
        r"(?i)\bbearer\s+(?P<value>[A-Za-z0-9._~+/=-]{8,})",  # bearer_token
        KEY_VALUE_PATTERN,  # secret_key_value
    )
)

# Standard LogRecord attributes: anything else on a record is caller `extra`.
STANDARD_ATTRS: frozenset[str] = frozenset(
    vars(logging.makeLogRecord({})).keys() | {"message", "asctime"}
)


def mask(secret: str) -> str:
    """Keep the first KEEP characters and replace the rest with stars."""
    if len(secret) <= KEEP:
        return "****"
    return secret[:KEEP] + "*" * max(4, len(secret) - KEEP)


def _mask_match(match: re.Match[str]) -> str:
    """Mask a whole match, or only its `value` group when the pattern names one."""
    if "value" not in match.re.groupindex:
        return mask(match.group(0))
    start, end = match.span("value")
    text = match.string
    return text[match.start() : start] + mask(text[start:end]) + text[end : match.end()]


def redact_text(text: str) -> str:
    """Mask every value-shaped secret inside one string."""
    for pattern in VALUE_PATTERNS:
        text = pattern.sub(_mask_match, text)
    return text


def redact_value(key: str | None, value: object) -> Any:
    """Redact one data value: secret-shaped keys lose their value; strings are scanned."""
    if key is not None and (
        SECRET_NAME_RE.search(key) or SECRET_NAME_RE.search(_CAMEL_BOUNDARY_RE.sub("_", key))
    ):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {str(k): redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(None, item) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    # Other objects reach the JSON formatter as str() (default=str): redact that rendering here.
    return redact_text(str(value))


class RedactionFilter(logging.Filter):
    """Redact the rendered message and every caller-supplied field of a record in place.

    Never raises into the caller: a message whose format string or arguments do not render is
    kept as its raw template with the arguments dropped, and a field that cannot be redacted is
    replaced whole.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
        except Exception:  # a bad format string or argument must not reach the caller
            rendered = _template_text(record.msg)
        record.msg = redact_text(rendered)
        record.args = ()
        for key in [name for name in vars(record) if name not in STANDARD_ATTRS]:
            try:
                redacted: Any = redact_value(key, getattr(record, key))
            except Exception:  # fail closed: a value that cannot render is never emitted
                redacted = _unrenderable_field()
            setattr(record, key, redacted)
        return True


def _template_text(msg: object) -> str:
    """Render a message without its arguments; never raises."""
    try:
        return str(msg)
    except Exception:
        return f"<unprintable {type(msg).__name__}>"


def _unrenderable_field() -> str:
    """Placeholder for a field that cannot render: its value is never emitted."""
    return REDACTED
