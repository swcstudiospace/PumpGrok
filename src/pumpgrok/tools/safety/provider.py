"""safety.provider: paid-RPC-provider record for BLIND advisory handling.

While no paid RPC provider is recorded, SAFE-4 holder-concentration and
SAFE-8 deployer-history BLIND results are advisory (amendment 2026-10-25).
The record is the one line `paid_rpc_provider: <value>` in
.planning/STATE.md, read relative to the working directory. The value `none`
means no provider is recorded. Any other state counts as recorded and fails
closed: a missing or unreadable file, no key line, two or more key lines, or
an empty value. The value is never logged or returned.
"""

from __future__ import annotations

import re
from pathlib import Path

PROVIDER_RECORD_PATH = Path(".planning/STATE.md")
_PROVIDER_LINE_RE = re.compile(r"^paid_rpc_provider:(.*)$", re.MULTILINE)


def paid_rpc_provider_recorded(path: Path = PROVIDER_RECORD_PATH) -> bool:
    """True unless the record holds exactly one key line whose value is ``none``."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True
    values: list[str] = [match.strip() for match in _PROVIDER_LINE_RE.findall(text)]
    if len(values) != 1:
        return True
    return values[0] != "none"
