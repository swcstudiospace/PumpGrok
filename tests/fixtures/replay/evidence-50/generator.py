"""Generate the SYNTHETIC evidence-50 replay fixture (PumpGrok v4 phase 14, plan 14-04).

Not market evidence. Every value is deterministic and derives from the smoke fixtures:

- token facts (name, image_uri, S, T, unique_buyers) come from the entry rows of
  ``tests/fixtures/replay/smoke/events.jsonl``, whose sha256 the smoke manifest pins;
- the timeline starts at the first tick of ``tests/fixtures/replay/smoke-10m`` and runs at its
  ninety-second arrival cadence;
- mints are domain-separated base58 digests, the same derivation smoke-10m uses.

Each candidate is one tick row. The gateway prefilter (``pumpgrok.grok.gateway.prefilter``)
decides admission, and every admitted candidate gets one ``llm.jsonl`` record keyed by the
gateway's own request key. Candidates the prefilter must reject are included on purpose
(one reason each, cycled), so the fixture exercises the filter instead of admitting everything.

Run from the repository root; the output is byte-stable:

    .venv/bin/python tests/fixtures/replay/evidence-50/generator.py
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
from pumpgrok.grok.gateway import GrokGateway, GrokRequest, _request_key, prefilter, sanitize
from pumpgrok.replay.clock import FixtureClock, parse_ts_utc
from pumpgrok.replay.fixtures import read_jsonl, verify_manifest

DATASET = "evidence-50"
DIR = Path(__file__).resolve().parent
SMOKE_DIR = DIR.parent / "smoke"
SMOKE10M_DIR = DIR.parent / "smoke-10m"
COMMAND = ".venv/bin/python tests/fixtures/replay/evidence-50/generator.py"
SEED_HINT = 20260101
CADENCE_S = 90
CANDIDATES = 300
ADMITTED = 50
ADMITTED_EVERY = 6  # rows at index % 6 == 0 are admitted; every other row is a planned rejection
DECOY_REASONS = (
    "too_young",
    "too_old",
    "market_window_closed",
    "too_few_buyers",
    "low_prerank",
)
LLM_LATENCY_S = 1.2

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_SCORE_FIELDS = ("trend_fit", "virality", "community_signals", "launch_timing")


@dataclass(frozen=True)
class Observation:
    """One candidate row read back into the gateway's own request and prefilter inputs."""

    row: dict[str, Any]
    now: float
    request: GrokRequest


def _derive_mint(label: str, length: int = 44) -> str:
    out: list[str] = []
    counter = 0
    while len(out) < length:
        first = hashlib.sha256(f"{DATASET}/{label}:{counter}".encode()).digest()
        second = hashlib.sha256(first).digest()
        for byte in first + second:
            if len(out) >= length:
                break
            out.append(_B58[byte % 58])
        counter += 1
    return "".join(out)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _prerank_text(hundredths: int) -> str:
    return f"{hundredths // 100}.{hundredths % 100:02d}"


def _smoke_sources() -> tuple[list[dict[str, Any]], float, dict[str, str]]:
    """Verify both smoke manifests, then return the token templates, the start and the pins."""
    verify_manifest(SMOKE_DIR)
    verify_manifest(SMOKE10M_DIR)
    smoke_rows = read_jsonl(SMOKE_DIR / "events.jsonl")
    templates = [row for row in smoke_rows if "unique_buyers" in row and not row.get("complete")]
    assert templates, "smoke events hold no entry token rows"
    start = parse_ts_utc(read_jsonl(SMOKE10M_DIR / "events.jsonl")[0]["ts_utc"])
    pins = {
        "smoke": json.loads((SMOKE_DIR / "manifest.json").read_text())["sha256"]["events.jsonl"],
        "smoke-10m": json.loads((SMOKE10M_DIR / "manifest.json").read_text())["sha256"][
            "events.jsonl"
        ],
    }
    return templates, start, pins


def _intended(index: int) -> str:
    """The reason row ``index`` must get from the prefilter: admitted, or its planned rejection."""
    if index % ADMITTED_EVERY == 0:
        return "admitted"
    # Rejected rows are numbered 0..249 in order and cycle the five reasons: 50 each.
    ordinal = index - index // ADMITTED_EVERY - 1
    return DECOY_REASONS[ordinal % len(DECOY_REASONS)]


def _row(index: int, template: dict[str, Any], start: float) -> dict[str, Any]:
    now = start + CADENCE_S * index
    reason = _intended(index)
    # Admitted rows: age 300..3240 s, first trade 60..599 s ago, prerank 0.50..1.00. The base
    # values come from the row's slot (index // ADMITTED_EVERY), so every row stays in range.
    slot = index // ADMITTED_EVERY
    age = 300 + 60 * slot
    first_trade_age = 60 + 11 * slot
    buyers = template["unique_buyers"]
    prerank = _prerank_text(50 + (7 * index) % 51)
    if reason == "too_young":
        age = 60
    elif reason == "too_old":
        age = 3700
    elif reason == "market_window_closed":
        first_trade_age = 3700
    elif reason == "too_few_buyers":
        buyers = 4
    elif reason == "low_prerank":
        prerank = _prerank_text(10 + (3 * index) % 40)
    return {
        "ts_utc": _iso(now),
        "kind": "tick",
        "mint": _derive_mint(f"candidate-{index:03d}"),
        "name": f"{template['name']} {index:03d}",
        "image_uri": template["image_uri"],
        "created_ts_utc": _iso(now - age),
        "first_trade_ts_utc": _iso(now - first_trade_age),
        "unique_buyers": buyers,
        "prerank": prerank,
        "S": template["S"],
        "T": template["T"],
        "complete": False,
        "source": "rest" if index % 2 == 0 else "pumpportal",
    }


def _narrative_at(now: float) -> NarrativeAgent:
    # build_user_message and the prompt, schema and model properties never touch the gateway,
    # so the generator needs no admission stack. Requests use the production agent's constants.
    return NarrativeAgent(
        GrokSettings(),
        gateway=cast(GrokGateway, None),
        clock=FixtureClock(start=now),
    )


def observe(rows: list[dict[str, Any]]) -> list[Observation]:
    """Rebuild each row's gateway request exactly as ``GrokAgent.run`` builds it."""
    observations: list[Observation] = []
    for row in rows:
        now = parse_ts_utc(row["ts_utc"])
        token = Token(
            mint=row["mint"],
            name=row["name"],
            image_uri=row["image_uri"],
            created_timestamp=parse_ts_utc(row["created_ts_utc"]),
            unique_buyers=row["unique_buyers"],
        )
        agent = _narrative_at(now)
        request = GrokRequest(
            event_id=f"{DATASET}-{len(observations):03d}",
            agent=agent.name,
            model=agent.model,
            prompt_sha=agent.prompt_sha,
            schema=agent.schema_sha,
            input={},
            text=agent.build_user_message(token),
            candidate=gateway_candidate(
                token,
                prerank=Decimal(row["prerank"]),
                first_trade_at=parse_ts_utc(row["first_trade_ts_utc"]),
                last_decision_at=None,
            ),
        )
        observations.append(Observation(row=row, now=now, request=request))
    return observations


def request_key(request: GrokRequest) -> str:
    """The gateway's own request key, which ``llm.jsonl`` records are indexed by."""
    return _request_key(request, sanitize(request.text))


def _answer(mint: str) -> str:
    digest = hashlib.sha256(mint.encode("utf-8")).digest()
    body: dict[str, Any] = {
        field: round(0.5 + (digest[position] % 50) / 100, 2)
        for position, field in enumerate(_SCORE_FIELDS)
    }
    body["reasoning"] = "SYNTHETIC evidence-50 answer. Not a model result."
    NarrativeResult.model_validate(body)
    return json.dumps(body, sort_keys=True)


def _jsonl(records: list[dict[str, Any]]) -> bytes:
    return "".join(json.dumps(record) + "\n" for record in records).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_files() -> dict[str, bytes]:
    """Every output file as bytes. Pure: no clock, no network, no randomness."""
    templates, start, pins = _smoke_sources()
    rows = [_row(index, templates[index % len(templates)], start) for index in range(CANDIDATES)]
    events_bytes = _jsonl(rows)
    # Derive from the serialized bytes, so the fixture and its readers see the same facts.
    observations = observe([json.loads(line) for line in events_bytes.decode("utf-8").splitlines()])

    admitted: list[Observation] = []
    rejections: Counter[str] = Counter()
    for index, observation in enumerate(observations):
        verdict = prefilter(observation.request.candidate, now=observation.now)
        if verdict.reason != _intended(index):
            raise RuntimeError(
                f"row {index} got prefilter reason {verdict.reason!r}, planned {_intended(index)!r}"
            )
        if verdict.admit:
            admitted.append(observation)
        else:
            rejections[verdict.reason] += 1
    if len(admitted) != ADMITTED:
        raise RuntimeError(
            f"only {len(admitted)} candidates admitted; evidence-50 needs {ADMITTED}"
        )

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
    rejected = len(observations) - len(admitted)
    mix = ", ".join(f"{reason} {rejections[reason]}" for reason in DECOY_REASONS)
    notes = (
        "SYNTHETIC. Not market evidence. Regenerate with "
        f"`{COMMAND}` from the repository root. Built from tests/fixtures/replay/smoke "
        f"(events.jsonl sha256 {pins['smoke']}) and tests/fixtures/replay/smoke-10m "
        f"(events.jsonl sha256 {pins['smoke-10m']}). {len(observations)} candidate rows: "
        f"{len(admitted)} admitted by pumpgrok.grok.gateway.prefilter, "
        f"one row in {ADMITTED_EVERY}, "
        f"and {rejected} rejected by it ({mix}). Arrivals every {CADENCE_S} s from the "
        "smoke-10m start. Token facts come from smoke token rows; prerank, first trade and "
        "answers are deterministic synthetic values. Each admitted request has one llm.jsonl "
        "record keyed by the gateway request key; llm answers are synthetic, not model output."
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
