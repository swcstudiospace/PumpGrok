"""Loud atomic file writes (PATTERNS C, ported from StateStore.save).

Ordering is vendor-exact: tmp file in the same directory, `json.dump`, `flush`,
`os.fsync`, `os.replace`, unlink tmp on failure. One change: OSError is never
swallowed — the ledger must fail loudly.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    """Write `payload` to `path` atomically. Raises OSError (loudly) on failure."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(dict(payload), fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
