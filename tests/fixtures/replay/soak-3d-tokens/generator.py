"""Generate the SYNTHETIC soak-3d-tokens replay fixture (PumpGrok v4 phase 14, plan 14-04: GRK-11).

Not market evidence. ``tests/fixtures/replay/soak-3d`` carries price ticks but no token facts, so
this dataset derives them from that file's ticks. The source is verified against its manifest
first and is never written. soak-3d itself stays byte-identical.

Mapping. Each tick row is one candidate: one sighting of a mint at the tick's time.

- ``ts_utc``, ``mint``, ``S``, ``T``, ``complete``, ``source``: copied from the tick.
- ``name``: ``"Soak 3d "`` plus the first six characters of the mint.
- ``image_uri``: ``fixture://soak-3d-tokens/token.png``.
- ``created_ts_utc`` and ``first_trade_ts_utc``: the time of the mint's first tick. The soak holds
  no separate creation or first-trade record, so its first observed tick stands for both.
- ``unique_buyers``: the tick's 1-based ordinal within its mint. The soak carries no wallet
  identities, so each tick is taken as one buy by a distinct buyer.
- ``prerank``: ``min(S, G) / G`` floored to two decimals, where ``G`` is the reserve ``S`` of the
  soak's first ``complete`` tick (its graduation). Derived from the source, never typed in.
- ``launch`` and ``creator`` fields are dropped: the prefilter reads neither.

Admission. ``pumpgrok.grok.gateway.prefilter`` decides every row. ``last_decision_at`` is the time
of the mint's previous admitted row, because an admitted row is the decision the caller records.
Each admitted request gets one ``llm.jsonl`` record keyed by the gateway's own request key.

Run from the repository root; the output is byte-stable:

    .venv/bin/python tests/fixtures/replay/soak-3d-tokens/generator.py
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from pumpgrok.config.settings import GrokSettings
from pumpgrok.engine.agents.base import gateway_candidate
from pumpgrok.engine.agents.narrative import NarrativeAgent
from pumpgrok.engine.models import NarrativeResult, Token
from pumpgrok.grok.gateway import (
    GrokGateway,
    GrokRequest,
    PrefilterVerdict,
    _request_key,
    prefilter,
    sanitize,
)
from pumpgrok.replay.clock import FixtureClock, parse_ts_utc
from pumpgrok.replay.fixtures import read_jsonl, verify_manifest

DATASET = "soak-3d-tokens"
DIR = Path(__file__).resolve().parent
SOURCE_DIR = DIR.parent / "soak-3d"
COMMAND = ".venv/bin/python tests/fixtures/replay/soak-3d-tokens/generator.py"
SEED_HINT = 20260101
IMAGE_URI = "fixture://soak-3d-tokens/token.png"
LLM_LATENCY_S = 1.9  # the soak-3d recorded LLM latency
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_SCORE_FIELDS = ("trend_fit", "virality", "community_signals", "launch_timing")


@dataclass(frozen=True)
class Observation:
    """One candidate row read back into the gateway's request, with the real prefilter verdict."""

    row: dict[str, Any]
    now: float
    request: GrokRequest
    verdict: PrefilterVerdict


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _jsonl(records: list[dict[str, Any]]) -> bytes:
    return "".join(json.dumps(record) + "\n" for record in records).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _answer(mint: str) -> str:
    digest = hashlib.sha256(mint.encode("utf-8")).digest()
    body: dict[str, Any] = {
        field: round(0.5 + (digest[position] % 50) / 100, 2)
        for position, field in enumerate(_SCORE_FIELDS)
    }
    body["reasoning"] = "SYNTHETIC soak-3d-tokens answer. Not a model result."
    NarrativeResult.model_validate(body)
    return json.dumps(body, sort_keys=True)


def _source_rows() -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Verify the soak-3d source, then return its tick rows and the hashes the notes record."""
    verify_manifest(SOURCE_DIR)
    events_path = SOURCE_DIR / "events.jsonl"
    manifest_path = SOURCE_DIR / "manifest.json"
    rows = read_jsonl(events_path)
    if not rows:
        raise RuntimeError("soak-3d holds no ticks")
    if any(row.get("kind") != "tick" for row in rows):
        raise RuntimeError("soak-3d holds a non-tick row; the token mapping only reads ticks")
    hashes = {
        "events": _sha(events_path.read_bytes()),
        "manifest": _sha(manifest_path.read_bytes()),
    }
    return rows, hashes


def _token_rows(source: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map each soak-3d tick to one candidate row, per the mapping in the module docstring."""
    graduation = next((int(row["S"]) for row in source if row.get("complete")), None)
    if not graduation:
        raise RuntimeError("soak-3d has no complete tick; the prerank scale is undefined")
    first_seen: dict[str, str] = {}
    ordinal: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for tick in source:
        mint = str(tick["mint"])
        first_seen.setdefault(mint, str(tick["ts_utc"]))
        ordinal[mint] += 1
        hundredths = min(int(tick["S"]), graduation) * 100 // graduation
        rows.append(
            {
                "ts_utc": tick["ts_utc"],
                "kind": "tick",
                "mint": mint,
                "name": f"Soak 3d {mint[:6]}",
                "image_uri": IMAGE_URI,
                "created_ts_utc": first_seen[mint],
                "first_trade_ts_utc": first_seen[mint],
                "unique_buyers": ordinal[mint],
                "prerank": f"{hundredths // 100}.{hundredths % 100:02d}",
                "S": tick["S"],
                "T": tick["T"],
                "complete": tick["complete"],
                "source": tick["source"],
            }
        )
    return rows


def observe(rows: list[dict[str, Any]]) -> list[Observation]:
    """Rebuild each row's gateway request as ``NarrativeAgent`` builds it, and run the prefilter.

    Rows are processed in time order. Each admitted row becomes the ``last_decision_at`` of the
    next row for the same mint, so the mint cooldown rule sees the decisions it would see live.
    """
    clock = FixtureClock(start=parse_ts_utc(rows[0]["ts_utc"]))
    agent = NarrativeAgent(GrokSettings(), gateway=cast(GrokGateway, None), clock=clock)
    last_admitted: dict[str, float] = {}
    observations: list[Observation] = []
    for index, row in enumerate(rows):
        now = parse_ts_utc(row["ts_utc"])
        clock.advance_to(now)
        token = Token(
            mint=row["mint"],
            name=row["name"],
            image_uri=row["image_uri"],
            created_timestamp=parse_ts_utc(row["created_ts_utc"]),
            unique_buyers=row["unique_buyers"],
        )
        candidate = gateway_candidate(
            token,
            prerank=Decimal(row["prerank"]),
            first_trade_at=parse_ts_utc(row["first_trade_ts_utc"]),
            last_decision_at=last_admitted.get(row["mint"]),
        )
        verdict = prefilter(candidate, now=now)
        if verdict.admit:
            last_admitted[row["mint"]] = now
        request = GrokRequest(
            event_id=f"{DATASET}-{index:04d}",
            agent=agent.name,
            model=agent.model,
            prompt_sha=agent.prompt_sha,
            schema=agent.schema_sha,
            input={},
            text=agent.build_user_message(token),
            candidate=candidate,
        )
        observations.append(Observation(row=row, now=now, request=request, verdict=verdict))
    return observations


def request_key(request: GrokRequest) -> str:
    """The gateway's own request key, which ``llm.jsonl`` records are indexed by."""
    return _request_key(request, sanitize(request.text))


def build_files() -> dict[str, bytes]:
    """Every output file as bytes. Pure: no clock, no network, no randomness."""
    source, source_hashes = _source_rows()
    rows = _token_rows(source)
    events_bytes = _jsonl(rows)
    # Derive from the serialized bytes, so the fixture and its readers see the same facts.
    observations = observe([json.loads(line) for line in events_bytes.decode("utf-8").splitlines()])

    admitted = [observation for observation in observations if observation.verdict.admit]
    if not admitted:
        raise RuntimeError("the real prefilter admitted no soak-3d-tokens candidate")
    rejections = Counter(o.verdict.reason for o in observations if not o.verdict.admit)

    llm_bytes = _jsonl(
        [
            {
                "request_hash": request_key(observation.request),
                "outcome": "ok",
                "latency_s": LLM_LATENCY_S,
                "response": {
                    "model": observation.request.model,
                    "content": _answer(observation.row["mint"]),
                },
            }
            for observation in admitted
        ]
    )
    mix = ", ".join(f"{reason} {count}" for reason, count in sorted(rejections.items()))
    notes = (
        "SYNTHETIC. Not market evidence. Regenerate with "
        f"`{COMMAND}` from the repository root. Built from tests/fixtures/replay/soak-3d "
        f"(events.jsonl sha256 {source_hashes['events']}, manifest.json sha256 "
        f"{source_hashes['manifest']}). Each soak-3d tick is one candidate; token facts are "
        "derived as the module docstring of generator.py maps them: created and first trade at "
        "the mint's first tick, buyers by tick ordinal, prerank from the reserve against the "
        f"soak graduation tick. {len(observations)} raw candidates: {len(admitted)} admitted by "
        "pumpgrok.grok.gateway.prefilter with the mint cooldown fed by earlier admissions, and "
        f"{len(observations) - len(admitted)} rejected by it ({mix}). Each admitted request has "
        "one llm.jsonl record keyed by the gateway request key; llm answers are synthetic, not "
        "model output."
    )
    manifest = {
        "dataset": DATASET,
        "provenance": "synthetic",
        "recorded_from_utc": rows[0]["ts_utc"],
        "recorded_to_utc": rows[-1]["ts_utc"],
        "seed_hint": SEED_HINT,
        "sources": {"rest": "synthetic", "pumpportal": "synthetic"},
        "sha256": {"events.jsonl": _sha(events_bytes), "llm.jsonl": _sha(llm_bytes)},
        "notes": notes,
    }
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    return {
        "events.jsonl": events_bytes,
        "llm.jsonl": llm_bytes,
        "manifest.json": manifest_bytes,
    }


def main() -> None:
    files = build_files()
    for name, data in files.items():
        (DIR / name).write_bytes(data)
    print(f"wrote {len(files)} files to {DIR}")


if __name__ == "__main__":
    main()
