"""Redaction for log messages and structured data (FOUNDATION_STACK 5.3, OBS-001).

Value-based: the G-3 trading families and the precedent `private_key`, `jwt` and
`conn_string` families (programming-desk `ci/gates/check_secrets.py`) are masked wherever
they occur in a string. Key-based: any data key shaped like a secret name has its value
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
# names from FOUNDATION_STACK 5.3 (keypair, mnemonic, seed, wallet_secret).
SECRET_NAME_RE = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9]|_)(?:secret|password|passwd|pwd|token|api[_-]?key|apikey|auth|"
    r"credential|private[_-]?key|access[_-]?key|client[_-]?secret|encryption[_-]?key|"
    r"keypair|mnemonic|seed|wallet[_-]?secret)"
    r"(?:[^A-Za-z0-9]|_|$)"
)

# Value shapes. The G-3 trading families are the synthetic-testable set from FOUNDATION_STACK
# section 4; the last three are the precedent private_key, jwt and conn_string families.
VALUE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"\b[1-9A-HJ-NP-Za-km-z]{86,88}\b",  # solana_base58_key
        r"\[\s*(?:\d{1,3}\s*,\s*){63}\d{1,3}\s*\]",  # solana_json_keypair
        r"(?i)helius(?:-rpc)?\.com/[^\s\"']*api-key=[A-Za-z0-9-]{20,}",  # helius_url_key
        r"(?i)[a-z0-9-]+\.solana-mainnet\.quiknode\.pro/[A-Za-z0-9]{20,}",  # quicknode_url
        r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b",  # telegram_bot_token
        r"\bxai-[A-Za-z0-9]{32,}\b",  # xai_key
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",  # private_key
        r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",  # jwt
        r"(?i)\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp)://"
        r"[^:\s/]+:[^@\s/]+@",  # conn_string
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


def redact_text(text: str) -> str:
    """Mask every value-shaped secret inside one string."""
    for pattern in VALUE_PATTERNS:
        text = pattern.sub(lambda match: mask(match.group(0)), text)
    return text


def redact_value(key: str | None, value: object) -> Any:
    """Redact one data value: secret-shaped keys lose their value; strings are scanned."""
    if key is not None and SECRET_NAME_RE.search(key):
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {str(k): redact_value(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(None, item) for item in value]
    return value


class RedactionFilter(logging.Filter):
    """Redact the rendered message and every caller-supplied field of a record in place."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_text(record.getMessage())
        record.args = ()
        for key in [name for name in vars(record) if name not in STANDARD_ATTRS]:
            setattr(record, key, redact_value(key, getattr(record, key)))
        return True
