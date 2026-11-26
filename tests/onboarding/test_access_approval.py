<<<<<<< HEAD
"""Seat access grants exist only as operator-choice ledger rows."""

from pathlib import Path

from pumpgrok.onboarding.access import has_access, record_access


def test_no_grant_by_default(tmp_path: Path) -> None:
    assert not has_access(tmp_path / "access.jsonl", "bot-01-scout")


def test_grant_is_recorded(tmp_path: Path) -> None:
    path = tmp_path / "access.jsonl"
    record_access(path, "bot-01-scout")
    assert has_access(path, "bot-01-scout")
    assert not has_access(path, "bot-02-risk")
=======
"""ONB-04: roster-derived tool choices, no default grant, authenticated revocable decisions.

Authority comes only from protected, operator-authenticated records (HMAC under the operator
key) bound to a ConfigChanged row in the ledger. A ledger row alone grants nothing.
"""

from __future__ import annotations

import json
import random
import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from pumpgrok.core.bot import BotManifest
from pumpgrok.core.errors import PermissionDenied
from pumpgrok.core.ids import CorrelationId, IdFactory, bind_correlation
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, load_bot_manifests, roster_tool_names
from pumpgrok.core.registry import GrantAudit, ToolRegistry
from pumpgrok.core.side_effect import SideEffect
from pumpgrok.core.tool import ToolInput, ToolMeta, ToolOutput, ToolSpec, tool
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.store import LedgerStore

REPO_ROSTERS = Path(__file__).resolve().parents[2] / "contracts" / "tool-rosters"
SEAT = "bot-01-scout"
LEDGER = Path("var") / "ledger.sqlite"
CHOICES = Path("var") / "operator" / oc.CHOICES_NAME
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def operator_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory whose operator key is owned by the running account."""
    monkeypatch.chdir(tmp_path)
    oc.init_key(Path("var") / "operator")
    return tmp_path


@pytest.fixture
def bound_correlation() -> Iterator[None]:
    """ToolRegistry.find refuses to run without an ambient correlation id."""
    factory = IdFactory(_Clock(), random.Random(3))
    with bind_correlation(CorrelationId.new(factory)):
        yield


def _tool_names(seat: str = SEAT) -> list[str]:
    return sorted(roster_tool_names(REPO_ROSTERS, seat))


def _own_tool(seat: str = SEAT) -> str:
    """A tool the seat file itself lists (not one inherited from the core eight)."""
    doc = yaml.safe_load((REPO_ROSTERS / f"{seat}.yaml").read_text(encoding="utf-8"))
    return str(doc["tools"][0]["name"])


def _grants(contracts: Path = REPO_ROSTERS) -> oc.OperatorGrants:
    return oc.OperatorGrants(contracts_dir=contracts)


def _record(decision: str, seat: str = SEAT, tool_name: str | None = None) -> None:
    store = LedgerStore(LEDGER)
    try:
        oc.record_tool_choice(
            store,
            seat=seat,
            tool=tool_name or _tool_names(seat)[0],
            decision=decision,
            contracts_dir=REPO_ROSTERS,
            now=NOW,
        )
    finally:
        store.close()


def test_every_seat_lists_its_roster_and_grants_nothing_by_default(operator_home: Path) -> None:
    grants = _grants()
    for seat in EXPECTED_SEAT_IDS:
        names = _tool_names(seat)
        assert names, seat
        for name in names:
            assert grants.allows(seat, name) is False
    assert not LEDGER.exists()


def test_roster_helper_rejects_unknown_seat() -> None:
    with pytest.raises(ValueError, match="unknown seat"):
        roster_tool_names(REPO_ROSTERS, "bot-99-ghost")


def test_authenticated_allow_grants_only_the_roster_tool(operator_home: Path) -> None:
    names = _tool_names()
    assert len(names) > 1
    _record("allow")
    assert _grants().allows(SEAT, names[0]) is True
    assert _grants().allows(SEAT, names[-1]) is False
    assert _grants().allows("bot-02-risk", names[0]) is False


def test_writer_refuses_a_tool_outside_the_roster(operator_home: Path) -> None:
    store = LedgerStore(LEDGER)
    try:
        with pytest.raises(oc.OperatorChoiceError, match="not in the roster"):
            oc.record_tool_choice(
                store,
                seat=SEAT,
                tool="exec.live_place",
                decision="allow",
                contracts_dir=REPO_ROSTERS,
                now=NOW,
            )
    finally:
        store.close()
    assert not CHOICES.exists()


def test_deny_and_revoke_take_effect_immediately_and_after_restart(operator_home: Path) -> None:
    name = _tool_names()[0]
    _record("allow")
    assert _grants().allows(SEAT, name) is True
    _record("deny")
    assert _grants().allows(SEAT, name) is False
    _record("allow")
    assert _grants().allows(SEAT, name) is True
    _record("revoke")
    assert _grants().allows(SEAT, name) is False
    # A fresh reader (process restart) sees the same durable revocation.
    assert oc.OperatorGrants(contracts_dir=REPO_ROSTERS).allows(SEAT, name) is False


def test_forged_ledger_row_grants_nothing(operator_home: Path) -> None:
    name = _tool_names()[0]
    store = LedgerStore(LEDGER)
    try:
        store.append(
            ts_utc="2026-11-13T12:00:00Z",
            source="manual",
            correlation_id="operator",
            idempotency_key="forged-1",
            type="ConfigChanged",
            payload={
                "source": "manual",
                "by": "human:root",
                "keys_changed": [f"operator_choice:tool:{SEAT}:{name}"],
                "old_hash": "",
                "new_hash": "f" * 64,
            },
        )
    finally:
        store.close()
    assert _grants().allows(SEAT, name) is False


def test_tampered_protected_record_fails_closed(operator_home: Path) -> None:
    name = _tool_names()[0]
    _record("deny")
    CHOICES.write_text(
        CHOICES.read_text(encoding="utf-8").replace('"decision":"deny"', '"decision":"allow"'),
        encoding="utf-8",
    )
    assert _grants().allows(SEAT, name) is False
    with pytest.raises(oc.OperatorChoiceError, match="authentication failed"):
        oc.read_authority(Path("var") / "operator", LEDGER)


def test_ledger_truncation_past_a_deny_is_denied(operator_home: Path) -> None:
    """Allow then deny. Deleting the deny's ledger row must not restore the earlier allow."""
    name = _tool_names()[0]
    _record("allow")
    _record("deny")
    deny_key = json.loads(CHOICES.read_text(encoding="utf-8").splitlines()[-1])["idempotency_key"]
    db = sqlite3.connect(str(LEDGER))
    try:
        # A file-level edit: the append-only trigger is removed, then the row is cut.
        db.execute("DROP TRIGGER IF EXISTS events_append_only_d")
        db.execute("DELETE FROM events WHERE idempotency_key = ?", (deny_key,))
        db.commit()
    finally:
        db.close()
    assert _grants().allows(SEAT, name) is False


def test_protected_store_rollback_is_denied(operator_home: Path) -> None:
    """Restoring an older protected file cannot re-grant: the latest ledger row no longer binds."""
    name = _tool_names()[0]
    _record("allow")
    snapshot = CHOICES.read_text(encoding="utf-8")
    _record("revoke")
    CHOICES.write_text(snapshot, encoding="utf-8")
    assert _grants().allows(SEAT, name) is False


def test_changed_roster_removes_a_stale_grant(operator_home: Path, tmp_path: Path) -> None:
    name = _own_tool()
    _record("allow", tool_name=name)
    assert _grants().allows(SEAT, name) is True

    contracts = tmp_path / "rosters"
    contracts.mkdir()
    for path in REPO_ROSTERS.glob("*.yaml"):
        (contracts / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    seat_file = contracts / f"{SEAT}.yaml"
    doc = yaml.safe_load(seat_file.read_text(encoding="utf-8"))
    doc["tools"] = [entry for entry in doc["tools"] if entry["name"] != name]
    seat_file.write_text(yaml.safe_dump(doc), encoding="utf-8")

    assert _grants(contracts).allows(SEAT, name) is False


def test_missing_or_loose_key_denies(operator_home: Path) -> None:
    name = _tool_names()[0]
    _record("allow")
    key = Path("var") / "operator" / oc.KEY_NAME
    key.chmod(0o644)
    assert _grants().allows(SEAT, name) is False
    key.chmod(0o600)
    assert _grants().allows(SEAT, name) is True
    key.unlink()
    assert _grants().allows(SEAT, name) is False


def test_corrupt_protected_store_denies_everything(operator_home: Path) -> None:
    name = _tool_names()[0]
    _record("allow")
    with CHOICES.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    assert _grants().allows(SEAT, name) is False


def test_writer_refuses_when_not_the_key_owner(
    operator_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = Path("var") / "operator" / oc.KEY_NAME
    monkeypatch.setattr(oc.os, "geteuid", lambda: owner.stat().st_uid + 1)
    store = LedgerStore(LEDGER)
    try:
        with pytest.raises(oc.OperatorChoiceError, match="owns"):
            oc.record_tool_choice(
                store,
                seat=SEAT,
                tool=_tool_names()[0],
                decision="allow",
                contracts_dir=REPO_ROSTERS,
                now=NOW,
            )
    finally:
        store.close()
    assert not CHOICES.exists()


class _Clock:
    def now(self) -> float:
        return 1469918176.385

    def monotonic(self) -> float:
        return 1469918176.385

    def utc_iso(self) -> str:
        return datetime.fromtimestamp(self.now(), UTC).isoformat()

    async def sleep(self, seconds: float) -> None:
        return None

    @asynccontextmanager
    async def timeout(self, seconds: float) -> AsyncIterator[None]:
        yield None


class _In(ToolInput):
    q: str = "x"


class _Out(ToolOutput):
    answer: str = "y"


async def _call(payload: _In) -> _Out:
    meta = ToolMeta(
        source="test",
        fetched_at=NOW,
        freshness_s=0.0,
        correlation_id="01ARYZ6S41TSV4RRFF7Q3V9J6Q",
    )
    return _Out(meta=meta)


def test_registry_resolves_a_tool_only_after_an_authenticated_allow(
    operator_home: Path, bound_correlation: None
) -> None:
    manifest: BotManifest = load_bot_manifests(REPO_ROSTERS)[SEAT]
    name = _tool_names()[0]
    spec = ToolSpec(
        name=name,
        description="Roster tool for the operator gate test.",
        input_model=_In,
        output_model=_Out,
        side_effect=SideEffect.READ,
        timeout_s=5.0,
        rate_limit_key="gate",
        backend="test",
    )
    audits: list[GrantAudit] = []

    async def _allow(request: object, bot_id: str) -> bool:
        return True

    registry = ToolRegistry(
        clock=_Clock(),  # type: ignore[arg-type]
        audit_sink=audits.append,
        limits_checker=_allow,
        operator_gate=_grants().allows,
    )
    registry.register(tool(spec)(_call))

    with pytest.raises(PermissionDenied):
        registry.find(name, max_side_effect=SideEffect.READ, bot=manifest)
    _record("allow")
    assert registry.find(name, max_side_effect=SideEffect.READ, bot=manifest) is not None
    _record("revoke")
    with pytest.raises(PermissionDenied):
        registry.find(name, max_side_effect=SideEffect.READ, bot=manifest)
    assert [a.reason for a in audits if not a.allowed] == [
        "not_operator_approved",
        "not_operator_approved",
    ]
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
