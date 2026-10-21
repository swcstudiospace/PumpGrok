"""Recorded LLM outcomes keyed by canonical request hash (paper-engine.md 4.4).

Live-paper recording captures each model call as ``{canonical_request_hash,
outcome, latency_s, response}``; replay looks the request up instead of
calling the model. The hash strips every volatile field (timestamps,
correlation ids, ULIDs, per-run ids) before hashing, so the same logical
request matches across runs. A request with no record fails the run with
:class:`ReplayMissingRecord`: replay never invents a model answer.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pumpgrok.core.errors import ReplayMissingRecord
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import CorruptFixture, read_jsonl, verify_manifest

__all__ = [
    "LLM_OUTCOMES",
    "LlmRecord",
    "LlmResult",
    "ReplayLlm",
    "canonical_request_hash",
    "load_llm_records",
]

LLM_FILE = "llm.jsonl"
LLM_OUTCOMES = frozenset({"ok", "timeout", "error"})

_HASH_RE = re.compile(r"[0-9a-f]{64}")
_VOLATILE_RE = re.compile(
    r"(?i)(timestamp|^ts$|_ts$|^ts_|_ts_|_at$|_time$|time_utc|utc_now"
    r"|correlation|ulid|decision_id|order_id|request_id|nonce|seed|span)"
)


def _strip(value: Any) -> Any:
    """Drop volatile keys recursively; pass scalars through."""
    if isinstance(value, Mapping):
        return {
            key: _strip(item) for key, item in value.items() if not _VOLATILE_RE.search(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [_strip(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    """Reduce to JSON scalars; floats ride as repr strings (deterministic)."""
    if isinstance(value, Mapping):
        return {str(key): _freeze(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_freeze(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return repr(value)
    raise TypeError(f"canonical request holds an unhashable {type(value).__name__}")


def canonical_request_hash(request: Mapping[str, Any]) -> str:
    """sha256 over the stripped, deterministically serialized request."""
    body = json.dumps(_freeze(_strip(dict(request))), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LlmRecord:
    """One recorded model outcome, exactly as one llm.jsonl line."""

    request_hash: str
    outcome: str
    latency_s: float
    response: dict[str, Any]


@dataclass(frozen=True)
class LlmResult:
    """Outcome returned to the runner: virtual latency already applied."""

    outcome: str
    response: dict[str, Any]
    latency_s: float


def _parse_record(raw: dict[str, Any], number: int) -> LlmRecord:
    if not isinstance(raw.get("request_hash"), str) or not _HASH_RE.fullmatch(
        str(raw.get("request_hash"))
    ):
        raise CorruptFixture("llm record has no request_hash", file=LLM_FILE, line=number)
    if raw.get("outcome") not in LLM_OUTCOMES:
        raise CorruptFixture("llm record has a bad outcome", file=LLM_FILE, line=number)
    latency = raw.get("latency_s")
    if isinstance(latency, bool) or not isinstance(latency, (int, float)) or latency < 0:
        raise CorruptFixture("llm record has a bad latency_s", file=LLM_FILE, line=number)
    response = raw.get("response")
    if not isinstance(response, dict):
        raise CorruptFixture("llm record has no response object", file=LLM_FILE, line=number)
    return LlmRecord(
        request_hash=str(raw["request_hash"]),
        outcome=str(raw["outcome"]),
        latency_s=float(latency),
        response=dict(response),
    )


class ReplayLlm:
    """Serve recorded outcomes; unknown requests fail the run."""

    def __init__(self, records: Mapping[str, LlmRecord]) -> None:
        self._records = dict(records)

    @classmethod
    def from_rows(cls, rows: list[dict[str, Any]]) -> ReplayLlm:
        """Validate parsed llm.jsonl rows into a lookup table."""
        parsed = [_parse_record(raw, number) for number, raw in enumerate(rows, 1)]
        return cls({record.request_hash: record for record in parsed})

    def __len__(self) -> int:
        return len(self._records)

    def complete(self, request: Mapping[str, Any], clock: FixtureClock) -> LlmResult:
        """Return the recorded outcome, advancing virtual time by its latency.

        Raises :class:`ReplayMissingRecord` when the fixture holds no record
        for the request hash; the runner must fail instead of inventing one.
        """
        wanted = canonical_request_hash(request)
        record = self._records.get(wanted)
        if record is None:
            raise ReplayMissingRecord(
                "no recorded LLM outcome for request hash",
                request_hash=wanted,
            )
        if record.latency_s > 0:
            clock.advance_to(clock.now() + record.latency_s)
        return LlmResult(
            outcome=record.outcome,
            response=dict(record.response),
            latency_s=record.latency_s,
        )


def load_llm_records(dataset_dir: str | Path) -> ReplayLlm | None:
    """Load a dataset's recorded LLM outcomes, or None when it records none.

    The manifest is verified before any line is trusted; a listed but
    malformed llm.jsonl fails as a corrupt fixture. Datasets without the file
    (for example the hand-minimal smoke set) skip the model-resolution step.
    """
    target = Path(dataset_dir)
    manifest = verify_manifest(target)
    if LLM_FILE not in manifest.sha256:
        return None
    return ReplayLlm.from_rows(read_jsonl(target / LLM_FILE))
