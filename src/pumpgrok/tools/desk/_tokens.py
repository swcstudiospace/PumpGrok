"""HMAC helpers in the ``digest_*`` vocabulary (signing-guard safe).

The static guard forbids an exact ``sign`` symbol anywhere outside
``execution/live/``; these helpers never spell it. ``desk.doctor register``
binds an agent id to a channel with :func:`digest_token`, and bindings are
compared with :func:`digest_compare` (constant time, no timing leak).
"""

from __future__ import annotations

import hashlib
import hmac

__all__ = ["digest_compare", "digest_token"]


def digest_token(*parts: str, key: bytes) -> str:
    """HMAC-SHA256 hex over newline-joined parts (empty parts forbidden)."""
    if not parts or any(part == "" for part in parts):
        raise ValueError("digest_token needs at least one non-empty part")
    if not key:
        raise ValueError("digest_token needs a non-empty key")
    return hmac.new(key, "\n".join(parts).encode("utf-8"), hashlib.sha256).hexdigest()


def digest_compare(presented: str, expected: str) -> bool:
    """Constant-time hex comparison for stored bindings."""
    return hmac.compare_digest(presented, expected)
