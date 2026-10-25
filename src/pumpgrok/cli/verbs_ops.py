"""Read and human-gated verbs: doctor, live, report, verify."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import logging
import os
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pumpgrok.cli.codes import EXIT_CONFIG, EXIT_OK
from pumpgrok.cli.errors import UsageError, _not_implemented, _say
from pumpgrok.cli.validators import (
    _human_by,
    _jsonable,
    _ledger_id_or_none,
    _report_date,
    _utc_now,
)
from pumpgrok.cli.wiring import _repo_root
from pumpgrok.config.settings import ConfigError, Settings
from pumpgrok.core.errors import DataStale, ReplayMissingRecord
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.core.units import sol_to_lamports
from pumpgrok.doctor import doctor_report
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.reporting.daily import DailyReport
from pumpgrok.reporting.render import render_daily, render_weekly
from pumpgrok.reporting.weekly import WeeklyReport
from pumpgrok.supervisor.scheduler import run_once_replay

log = logging.getLogger("pumpgrok.cli")


def _doctor_verb(_args: argparse.Namespace, settings: Settings) -> int:
    _say(sys.stdout, *doctor_report(settings))
    return EXIT_OK


def _live_verb(args: argparse.Namespace, settings: Settings) -> int:
    if args.cmd == "confirm":
        return _live_confirm(args, settings)
    return _not_implemented(f"live {args.cmd}")


def _live_confirm(args: argparse.Namespace, settings: Settings) -> int:
    """Write the HMAC-signed human confirmation record (paper-engine.md 7.3).

    Binds the record to the config hash with the operator-held
    ``PUMPGROK_CONFIRMATION_KEY`` that no seat or tool can read, and appends
    ``ApprovalRecorded(kind=live_gate)`` to the ledger. Never changes the
    effective mode.
    """
    by = _human_by(args.by, "live confirm")
    try:
        cap_sol = Decimal(str(args.notional_cap))
    except InvalidOperation as exc:
        raise UsageError(f"bad --notional-cap {args.notional_cap!r}: want decimal SOL") from exc
    if not (Decimal("0") < cap_sol <= Decimal("1.0")):
        raise UsageError(f"bad --notional-cap {args.notional_cap!r}: want 0 < cap <= 1.0")
    try:
        expires = datetime.fromisoformat(str(args.expires).replace("Z", "+00:00"))
    except ValueError as exc:
        raise UsageError(f"bad --expires {args.expires!r}: want ISO-8601 UTC") from exc
    if expires.tzinfo is None:
        raise UsageError(f"bad --expires {args.expires!r}: want an offset or Z, not a naive time")
    try:
        expires_utc = expires.astimezone(UTC)
    except (OverflowError, ValueError) as exc:
        raise UsageError(f"bad --expires {args.expires!r}: expiry is out of range") from exc
    if expires_utc <= _utc_now():
        raise UsageError(f"bad --expires {args.expires!r}: expiry is in the past")
    key = os.environ.get("PUMPGROK_CONFIRMATION_KEY", "")
    if not key:
        _say(sys.stderr, "live confirm refused: PUMPGROK_CONFIRMATION_KEY is not set")
        return EXIT_CONFIG

    config_hash = hashlib.sha256(
        canonical_json(_jsonable(settings.model_dump(mode="json"))).encode("utf-8")
    ).hexdigest()
    cap_lamports = sol_to_lamports(cap_sol)
    confirmed_at = _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
    body = {
        "ledger_id": _ledger_id_or_none(),
        "config_hash": config_hash,
        "confirmed_by": by,
        "confirmed_at": confirmed_at,
        "expires_at": expires_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notional_cap_lamports": cap_lamports,
        "wallet_allowlist_sha256": hashlib.sha256(b"[]").hexdigest(),
        "statement": (
            "I confirm live trading with the listed wallet and cap. "
            "I have read SECURITY.md and RISK_POLICY.md."
        ),
    }
    signature = hmac.new(
        key.encode("utf-8"), canonical_json(body).encode("utf-8"), hashlib.sha256
    ).digest()
    record: dict[str, Any] = dict(body)
    record["signature"] = base64.b64encode(signature).decode("ascii")
    target = Path.cwd() / "var" / "live_confirmation.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    _append_live_approval(by, cap_lamports, record["signature"])
    _say(sys.stdout, json.dumps({"confirmation_record": str(target), "config_hash": config_hash}))
    return EXIT_OK


def _append_live_approval(by: str, cap_lamports: int, signature: str) -> None:
    """Append ApprovalRecorded(kind=live_gate) with the confirmation signature."""
    store = LedgerStore(PAPER_LEDGER_PATH)
    try:
        now = _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
        store.append(
            ts_utc=now,
            source="manual",
            correlation_id="desk",
            idempotency_key=f"live-confirm-{signature[:16]}",
            type="ApprovalRecorded",
            payload={
                "source": "manual",
                "id": f"apr-live-{signature[:16]}",
                "kind": "live_gate",
                "approved_by": by,
                "at": now,
                "size_lamports": cap_lamports,
                "token_units": 0,
                "raw_message": "live confirm",
            },
        )
    finally:
        store.close()


def _report_verb(args: argparse.Namespace, settings: Settings) -> int:
    """Emit the daily or weekly ASCII paper report to stdout (PAPER-006).

    Reads the ledger read-only: the path is guarded and sqlite opens it with
    ``mode=ro``, so reporting never creates ``var/`` files.
    """
    ledger = Path.cwd() / PAPER_LEDGER_PATH
    mode = settings.effective_mode
    if args.daily:
        day = _report_date(args.day, "--day")
        body = render_daily(DailyReport.build(ledger, day, mode=mode))
    else:
        week = _report_date(args.week, "--week")
        body = render_weekly(WeeklyReport.build(ledger, week, mode=mode, root=Path.cwd(), now=week))
    if args.out:
        target = Path(str(args.out))
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, target)
    _say(sys.stdout, body.rstrip("\n"))
    return EXIT_OK


def _verify_verb(args: argparse.Namespace, settings: Settings) -> int:
    """Replay a fixture dataset into its canonical replay ledger and verify it.

    ``--fixture`` names a directory or a dataset bundled under
    ``tests/fixtures/replay/<name>``. The run recreates
    ``var/replay/<dataset>/ledger.sqlite``, prints the ``events.hash`` of the
    chain, and exits 0 only when the chain verifies CONSISTENT.
    """
    raw = str(args.fixture)
    candidate = Path(raw)
    if candidate.is_dir():
        dataset_dir = candidate
    else:
        bundled = _repo_root() / "tests" / "fixtures" / "replay" / raw
        if not bundled.is_dir():
            raise ConfigError([f"unknown fixture dataset: {raw!r}"])
        dataset_dir = bundled
    try:
        result = run_once_replay(
            dataset_dir,
            settings.filter,
            seed=settings.replay.seed,
            exits=settings.exits,
            budget=settings.risk,
            limits=settings.limits,
        )
    except (DataStale, ReplayMissingRecord) as exc:
        _say(sys.stderr, f"replay failed: {exc.code}: {exc.message}")
        return EXIT_CONFIG
    _say(sys.stdout, f"events.hash={result.events_hash}")
    _say(sys.stdout, f"verify=CONSISTENT seq={result.seq} events={result.events_read}")
    return EXIT_OK
