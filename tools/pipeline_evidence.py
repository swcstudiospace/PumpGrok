#!/usr/bin/env python3
"""
pipeline_evidence.py – Read vendored grokbot-pumpfun JSONL as desk evidence.

Usage:
  python tools/pipeline_evidence.py
  python tools/pipeline_evidence.py --candidates --limit 5
  python tools/pipeline_evidence.py --mint <mint> --type buy --block

Reads vendor/grokbot-pumpfun/logs/trades.jsonl only. Never signs, sends,
or reads secrets. tx_hash dry_run is not a fill.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_LOG = "vendor/grokbot-pumpfun/logs/trades.jsonl"
SOURCES = "vendor/grokbot-pumpfun logs/trades.jsonl"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_log(log_arg: str) -> Path:
    path = Path(log_arg)
    if path.is_absolute():
        return path
    return (repo_root() / path).resolve()


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def atom(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if is_number(value):
        return json.dumps(value)
    if value is None:
        return "unavailable"
    return str(value)


def utc_iso(ts: Any) -> str:
    if not is_number(ts):
        return "unavailable"
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except (OverflowError, OSError, ValueError):
        return "unavailable"


def fmt_pct(share: Any) -> str:
    if not is_number(share):
        return "unavailable"
    return f"{float(share) * 100:.1f}%"


def as_dict(value: Any) -> Optional[Dict[str, Any]]:
    return value if isinstance(value, dict) else None


def display_or_dash(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def analyzer_line(metrics: Optional[Dict[str, Any]]) -> str:
    if metrics is None:
        return "unavailable"
    risk = metrics.get("risk_score")
    risk_part = f"{atom(risk)}/10" if is_number(risk) else "unavailable"
    creator = fmt_pct(metrics.get("creator_share"))
    top5 = fmt_pct(metrics.get("top5_share"))
    return f"{risk_part}, creator holding {creator}, top-5 {top5}"


def audit_line(audit: Optional[Dict[str, Any]]) -> str:
    if audit is None:
        return "unavailable"
    coordinated = audit.get("coordinated_buying")
    wash = audit.get("wash_trading")
    dump = audit.get("creator_dump_prep")
    bundled = audit.get("bundled_launch")
    return (
        f"coordinated_buy={atom(coordinated) if isinstance(coordinated, bool) else 'unavailable'} "
        f"wash={atom(wash) if isinstance(wash, bool) else 'unavailable'} "
        f"creator_dump={atom(dump) if isinstance(dump, bool) else 'unavailable'} "
        f"bundled_first_second={atom(bundled) if isinstance(bundled, bool) else 'unavailable'}"
    )


def narrative_line(narrative: Optional[Dict[str, Any]]) -> str:
    if narrative is None:
        return "unavailable"
    trend = narrative.get("trend_fit")
    virality = narrative.get("virality")
    community = narrative.get("community_signals")
    timing = narrative.get("launch_timing")
    return (
        f"trend={atom(trend) if is_number(trend) else 'unavailable'} "
        f"virality={atom(virality) if is_number(virality) else 'unavailable'} "
        f"community={atom(community) if is_number(community) else 'unavailable'} "
        f"timeliness={atom(timing) if is_number(timing) else 'unavailable'}"
    )


def checker_approve(checker: Optional[Dict[str, Any]]) -> str:
    if checker is None:
        return "unavailable"
    approve = checker.get("approve")
    if isinstance(approve, bool):
        return "true" if approve else "false"
    return "unavailable"


def total_score(scores: Optional[Dict[str, Any]]) -> str:
    if scores is None:
        return "unavailable"
    total = scores.get("total")
    if is_number(total):
        return atom(total)
    return "unavailable"


def desk_action(record: Dict[str, Any]) -> str:
    rtype = record.get("type")
    if rtype == "buy":
        return "hand off as LEAD to RISK"
    if rtype == "skip":
        stage = record.get("stage")
        reason = record.get("reason")
        stage_s = str(stage).strip() if stage not in (None, "") else ""
        reason_s = str(reason).strip() if reason not in (None, "") else ""
        if stage_s and reason_s:
            return f"discard with reason: {stage_s}/{reason_s}"
        if reason_s:
            return f"discard with reason: {reason_s}"
        if stage_s:
            return f"discard with reason: {stage_s}"
        return "discard with reason"
    return "context-only"


def evidence_block(record: Dict[str, Any]) -> str:
    mint = display_or_dash(record.get("mint"))
    symbol = display_or_dash(record.get("symbol"))
    ts = record.get("ts")
    iso = utc_iso(ts)
    rtype = record.get("type")
    type_label = rtype if rtype in ("buy", "skip", "close") else display_or_dash(rtype)
    tx_hash = display_or_dash(record.get("tx_hash"))
    ts_raw = atom(ts) if is_number(ts) else "unavailable"
    return "\n".join(
        [
            "PIPELINE-EVIDENCE",
            f"Token: {mint}",
            f"Symbol: {symbol}",
            f"Log window: {iso} .. {iso}",
            f"Record type: {type_label}",
            f"Analyzer: {analyzer_line(as_dict(record.get('metrics')))}",
            f"Audit flags: {audit_line(as_dict(record.get('audit')))}",
            f"Narrative: {narrative_line(as_dict(record.get('narrative')))}",
            f"Checker approve: {checker_approve(as_dict(record.get('checker')))}",
            f"Total score: {total_score(as_dict(record.get('scores')))}",
            f"tx_hash: {tx_hash}",
            f"Desk action: {desk_action(record)}",
            f"Sources: {SOURCES} ts={ts_raw}",
        ]
    )


def load_records(path: Path) -> Tuple[List[Dict[str, Any]], int]:
    records: List[Dict[str, Any]] = []
    skipped = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(parsed, dict):
                skipped += 1
                continue
            records.append(parsed)
    return records, skipped


def matches(
    record: Dict[str, Any],
    mint: Optional[str],
    rtype: Optional[str],
    candidates: bool,
) -> bool:
    if mint is not None and record.get("mint") != mint:
        return False
    if rtype is not None and record.get("type") != rtype:
        return False
    if candidates:
        if record.get("type") != "buy" or record.get("tx_hash") != "dry_run":
            return False
    return True


def fail(error: str) -> int:
    print(json.dumps({"ok": False, "error": error}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read vendored grokbot-pumpfun JSONL as PIPELINE-EVIDENCE. "
            "Never signs or sends."
        )
    )
    parser.add_argument(
        "--log",
        default=DEFAULT_LOG,
        help=f"JSONL path (default: {DEFAULT_LOG} from repo root)",
    )
    parser.add_argument(
        "--mint",
        default=None,
        help="Case-sensitive exact mint filter",
    )
    parser.add_argument(
        "--type",
        choices=["buy", "skip", "close"],
        default=None,
        help="Record type filter",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Most-recent matching records (default: 20)",
    )
    parser.add_argument(
        "--candidates",
        action="store_true",
        help="Only type=buy records whose tx_hash is dry_run (not fills)",
    )
    parser.add_argument(
        "--block",
        action="store_true",
        help="Include PIPELINE-EVIDENCE text blocks",
    )
    args = parser.parse_args()

    log_path = resolve_log(args.log)
    if not log_path.is_file():
        return fail(f"log not found: {log_path}")

    try:
        records, skipped = load_records(log_path)
    except OSError as exc:
        return fail(str(exc))

    filtered = [
        rec
        for rec in records
        if matches(rec, args.mint, args.type, args.candidates)
    ]
    limit = max(0, args.limit)
    selected = filtered[-limit:] if limit else []

    payload: Dict[str, Any] = {
        "ok": True,
        "log": str(log_path),
        "count": len(selected),
        "skipped_lines": skipped,
        "records": selected,
    }
    if args.block or args.candidates:
        payload["evidence_blocks"] = [evidence_block(rec) for rec in selected]

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
