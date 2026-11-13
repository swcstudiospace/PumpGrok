"""Revocable operator authority for seat tools and the RPC endpoint (ONB-04, ONB-08; D-08, D-09).

Trust boundary (plan 14-05 approved design)
- Operator identity is the OS account that owns the operator key, ``var/operator/operator.key``:
  a regular file, mode 0600 with no group or other bits, at least 32 bytes, in ``var/operator/``
  whose owner matches and which has no group or other write bit. Self-asserted names, TTYs and
  journal text identify nobody.
- Only that account may record a choice (``os.geteuid()`` must equal the key owner). The CLI
  additionally requires an interactive terminal and an exact typed confirmation phrase.
- Each choice is a protected record in ``var/operator/choices.jsonl``: the canonical payload,
  its digest, and an HMAC-SHA256 over the record body under the operator key. The key is never
  written to the ledger, argv or output.
- The ledger receives an existing-schema ``ConfigChanged`` row (payload fields only): ``new_hash``
  is the SHA-256 of the canonical payload, ``keys_changed`` names the scope and ``by`` is
  ``human:<account>``. That row is a commit marker. It grants nothing by itself.
- Commit order is protected record (fsynced) first, then the ledger row. A crash between the two
  leaves the decision unbound, which fails closed.

Authority rule (fail closed)
- Per scope, the latest protected record decides, and only when the latest ledger operator-choice
  row for that scope carries the same idempotency key, digest and ``by``. Otherwise the scope is
  unbound and grants nothing. Truncating the ledger, restoring an older protected file, forging a
  ledger row or editing a protected record each leave the scope unbound or unauthenticated.
- A grant is an ``allow`` decision for a tool that is still in the seat's current roster. The
  roster is read at every check, so a removed tool loses its grant at once.
- Missing, unreadable, loosely permissioned or corrupt authority raises ``OperatorChoiceError``.
  ``OperatorGrants.allows`` turns every such failure into a denial.
- ``deny`` and ``revoke`` are ordinary later records, so revocations survive restart.

Residual limits (stated, not hidden)
- The desk process must run as the operator account to verify records (the key is mode 0600), so
  code in that process can read the key. Seats must be isolated from the operator account at the
  OS level, which this module cannot enforce.
- Rolling back both the ledger and the protected file to an earlier consistent pair is not
  detectable without an external anchor.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import pwd
import secrets
import sqlite3
import stat
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pumpgrok.core.idempotency import canonical_json
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore

__all__ = [
    "CHOICES_NAME",
    "DEFAULT_CONTRACTS_DIR",
    "KEY_NAME",
    "OPERATOR_DIR",
    "RPC_SCOPE",
    "Decision",
    "Endpoint",
    "OperatorChoiceError",
    "OperatorGrants",
    "canonical_endpoint",
    "init_key",
    "operator_label",
    "read_authority",
    "record_rpc_choice",
    "record_tool_choice",
    "rpc_status",
    "tool_scope",
]

OPERATOR_DIR = Path("var") / "operator"
KEY_NAME = "operator.key"
CHOICES_NAME = "choices.jsonl"
DEFAULT_CONTRACTS_DIR = Path(__file__).resolve().parents[3] / "contracts" / "tool-rosters"

KEY_MIN_BYTES = 32
SCOPE_PREFIX = "operator_choice:"
RPC_SCOPE = "rpc"
TOOL_DECISIONS: frozenset[str] = frozenset({"allow", "deny", "revoke"})
RPC_DECISION = "select"
DEFAULT_PORTS: dict[str, int] = {"http": 80, "https": 443, "ws": 80, "wss": 443}
_RECORD_KEYS = frozenset(
    {"scope", "by", "ts_utc", "idempotency_key", "keys_changed", "digest", "payload"}
)


class OperatorChoiceError(RuntimeError):
    """Authority is unavailable, corrupt or refused. Every grant is denied when this is raised."""


@dataclass(frozen=True)
class Endpoint:
    """An RPC endpoint reduced to what may be recorded: scheme, host and port."""

    scheme: str
    host: str
    port: int

    def as_dict(self) -> dict[str, Any]:
        return {"scheme": self.scheme, "host": self.host, "port": self.port}

    def label(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"


@dataclass(frozen=True)
class Decision:
    """The latest protected decision for one scope, and whether the ledger binds it."""

    scope: str
    decision: str
    by: str
    digest: str
    idempotency_key: str
    payload: dict[str, Any]
    bound: bool

    @property
    def allowed(self) -> bool:
        return self.bound and self.decision == "allow"


def tool_scope(seat: str, tool: str) -> str:
    return f"tool:{seat}:{tool}"


def canonical_endpoint(url: str) -> Endpoint:
    """Reduce a URL to scheme, host and port. Userinfo, path, query and fragment are dropped."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS:
        raise ValueError(f"endpoint scheme must be one of {sorted(DEFAULT_PORTS)}")
    host = (parts.hostname or "").lower()
    if not host:
        raise ValueError("endpoint needs a host")
    try:
        explicit = parts.port
    except ValueError as exc:
        raise ValueError("endpoint port is not valid") from exc
    return Endpoint(scheme, host, explicit if explicit is not None else DEFAULT_PORTS[scheme])


def operator_label(uid: int) -> str:
    """``human:<account name>`` for the operator account. Never a seat id."""
    try:
        name = pwd.getpwuid(uid).pw_name
    except KeyError:
        name = f"uid{uid}"
    return f"human:{name}"


def _private_stat(path: Path, *, directory: bool) -> os.stat_result:
    try:
        st = os.lstat(path)
    except OSError as exc:
        raise OperatorChoiceError(f"unavailable: {path.name} is missing or unreadable") from exc
    if directory:
        if not stat.S_ISDIR(st.st_mode):
            raise OperatorChoiceError(f"unavailable: {path.name} is not a directory")
        if st.st_mode & 0o022:
            raise OperatorChoiceError(f"unavailable: {path.name} is group or world writable")
    else:
        if not stat.S_ISREG(st.st_mode):
            raise OperatorChoiceError(f"unavailable: {path.name} is not a regular file")
        if st.st_mode & 0o077:
            raise OperatorChoiceError(
                f"unavailable: {path.name} must be mode 0600 with no group or other access"
            )
    return st


def _load_authority(operator_dir: Path) -> tuple[int, bytes]:
    """Return the operator uid and key bytes, or raise when the trust anchor is not sound."""
    dir_st = _private_stat(operator_dir, directory=True)
    key_path = operator_dir / KEY_NAME
    key_st = _private_stat(key_path, directory=False)
    if key_st.st_uid != dir_st.st_uid:
        raise OperatorChoiceError(
            "unavailable: operator key and its directory have different owners"
        )
    try:
        key = key_path.read_bytes()
    except OSError as exc:
        raise OperatorChoiceError(
            "unavailable: operator key cannot be read by this account"
        ) from exc
    if len(key) < KEY_MIN_BYTES:
        raise OperatorChoiceError("unavailable: operator key is too short")
    return key_st.st_uid, key


def _mac(key: bytes, body: Mapping[str, Any]) -> str:
    return hmac.new(key, canonical_json(dict(body)).encode("utf-8"), hashlib.sha256).hexdigest()


def _digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(dict(payload)).encode("utf-8")).hexdigest()


def _read_protected(key: bytes, path: Path) -> list[dict[str, Any]]:
    """Every protected record, each authenticated. Any bad line fails the whole store."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OperatorChoiceError("unavailable: choices.jsonl cannot be read") from exc
    records: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        try:
            raw = json.loads(line)
        except ValueError as exc:
            raise OperatorChoiceError(
                f"unavailable: choices.jsonl line {number} is corrupt"
            ) from exc
        if not isinstance(raw, dict) or set(raw) != _RECORD_KEYS | {"mac"}:
            raise OperatorChoiceError(f"unavailable: choices.jsonl line {number} is malformed")
        mac = raw.pop("mac", None)
        if not isinstance(mac, str) or not hmac.compare_digest(mac, _mac(key, raw)):
            raise OperatorChoiceError(f"choices.jsonl line {number}: authentication failed")
        payload = raw["payload"]
        if not isinstance(payload, dict) or raw["digest"] != _digest(payload):
            raise OperatorChoiceError(f"choices.jsonl line {number}: digest does not match payload")
        records.append(raw)
    return records


def _latest_scope_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """Latest ConfigChanged row per operator-choice scope, authenticated or not."""
    latest: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        payload = row.get("payload")
        keys = payload.get("keys_changed") if isinstance(payload, Mapping) else None
        if not isinstance(keys, list) or len(keys) != 1 or not isinstance(keys[0], str):
            continue
        if not keys[0].startswith(SCOPE_PREFIX):
            continue
        latest[keys[0].removeprefix(SCOPE_PREFIX)] = row
    return latest


def _ledger_scope_rows(ledger_path: Path) -> dict[str, Mapping[str, Any]]:
    if not ledger_path.exists():
        return {}

    store = LedgerStore(ledger_path)
    try:
        rows = store.read(types=["ConfigChanged"], limit=None)
    finally:
        store.close()
    return _latest_scope_rows(rows)


def _authority(
    records: list[dict[str, Any]], ledger_rows: Mapping[str, Mapping[str, Any]]
) -> dict[str, Decision]:
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        latest[str(record["scope"])] = record
    decisions: dict[str, Decision] = {}
    for scope, record in latest.items():
        row = ledger_rows.get(scope)
        bound = (
            row is not None
            and row.get("idempotency_key") == record["idempotency_key"]
            and isinstance(row.get("payload"), Mapping)
            and row["payload"].get("new_hash") == record["digest"]
            and row["payload"].get("by") == record["by"]
        )
        payload = record["payload"]
        decisions[scope] = Decision(
            scope=scope,
            decision=str(payload.get("decision", "")),
            by=str(record["by"]),
            digest=str(record["digest"]),
            idempotency_key=str(record["idempotency_key"]),
            payload=payload,
            bound=bool(bound),
        )
    return decisions


def read_authority(operator_dir: Path, ledger_path: Path) -> dict[str, Decision]:
    """Latest decision per scope. Raises OperatorChoiceError when the trust anchor is unsound."""
    _, key = _load_authority(operator_dir)
    records = _read_protected(key, operator_dir / CHOICES_NAME)
    return _authority(records, _ledger_scope_rows(ledger_path))


def init_key(operator_dir: Path) -> None:
    """Create the operator key with O_EXCL and mode 0600. Refuses to replace an existing key."""
    operator_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        fd = os.open(operator_dir / KEY_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise OperatorChoiceError("refused: an operator key already exists") from exc
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(secrets.token_hex(32) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _writer_key(operator_dir: Path) -> tuple[bytes, str]:
    """Key and ``human:`` label for the writer, which must be the operator account itself."""
    owner, key = _load_authority(operator_dir)
    if os.geteuid() != owner:
        raise OperatorChoiceError(
            "refused: only the operator account that owns the operator key may record choices"
        )
    return key, operator_label(owner)


def _append_protected(path: Path, line: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _commit(
    store: LedgerStore,
    *,
    operator_dir: Path,
    scope: str,
    body: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    key, by = _writer_key(operator_dir)
    stored = _read_protected(key, operator_dir / CHOICES_NAME)
    ledger_rows = _latest_scope_rows(store.read(types=["ConfigChanged"], limit=None))
    previous = _authority(stored, ledger_rows).get(scope)
    ts_utc = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"v": 1, **body, "at": ts_utc, "nonce": secrets.token_hex(8)}
    digest = _digest(payload)
    idempotency_key = f"operator-choice|{digest}"
    keys_changed = [f"{SCOPE_PREFIX}{scope}"]
    record: dict[str, Any] = {
        "scope": scope,
        "by": by,
        "ts_utc": ts_utc,
        "idempotency_key": idempotency_key,
        "keys_changed": keys_changed,
        "digest": digest,
        "payload": payload,
    }
    line = canonical_json(record | {"mac": _mac(key, record)})
    _append_protected(operator_dir / CHOICES_NAME, line)
    store.append(
        ts_utc=ts_utc,
        source="manual",
        correlation_id="operator",
        idempotency_key=idempotency_key,
        type="ConfigChanged",
        payload={
            "source": "manual",
            "by": by,
            "keys_changed": keys_changed,
            "old_hash": previous.digest if previous is not None else "",
            "new_hash": digest,
        },
    )
    return record


def record_tool_choice(
    store: LedgerStore,
    *,
    seat: str,
    tool: str,
    decision: str,
    now: datetime,
    contracts_dir: Path | None = None,
    operator_dir: Path | None = None,
) -> dict[str, Any]:
    """Record an authenticated allow, deny or revoke for one roster tool of one seat."""
    if decision not in TOOL_DECISIONS:
        raise ValueError(f"decision must be one of {sorted(TOOL_DECISIONS)}")
    if seat not in EXPECTED_SEAT_IDS:
        raise OperatorChoiceError(f"unknown seat {seat!r}")
    roster = roster_tool_names(contracts_dir or DEFAULT_CONTRACTS_DIR, seat)
    if tool not in roster:
        raise OperatorChoiceError(f"{tool} is not in the roster of {seat}")
    return _commit(
        store,
        operator_dir=operator_dir or OPERATOR_DIR,
        scope=tool_scope(seat, tool),
        body={"kind": "tool", "seat": seat, "tool": tool, "decision": decision},
        now=now,
    )


def record_rpc_choice(
    store: LedgerStore,
    *,
    url: str,
    configured_urls: Iterable[str],
    now: datetime,
    operator_dir: Path | None = None,
) -> dict[str, Any]:
    """Record an explicit choice of one configured RPC endpoint (scheme, host, port only)."""
    chosen = canonical_endpoint(url)
    configured = {canonical_endpoint(item) for item in configured_urls}
    if chosen not in configured:
        raise OperatorChoiceError(
            f"refused: {chosen.label()} is not a configured endpoint; no new provider is added"
        )
    return _commit(
        store,
        operator_dir=operator_dir or OPERATOR_DIR,
        scope=RPC_SCOPE,
        body={"kind": "rpc", "decision": RPC_DECISION, "endpoint": chosen.as_dict()},
        now=now,
    )


def rpc_status(
    operator_dir: Path | None = None, ledger_path: Path | None = None
) -> tuple[str, Endpoint | None]:
    """Return ("default", None), ("unbound", None) or ("explicit", endpoint)."""
    decision = read_authority(
        operator_dir or OPERATOR_DIR, ledger_path or PAPER_LEDGER_PATH
    ).get(RPC_SCOPE)
    if decision is None:
        return ("default", None)
    if not decision.bound or decision.decision != RPC_DECISION:
        return ("unbound", None)
    endpoint = decision.payload["endpoint"]
    return ("explicit", Endpoint(endpoint["scheme"], endpoint["host"], int(endpoint["port"])))


class OperatorGrants:
    """Read-side gate: may ``seat`` use ``tool`` right now? Fails closed on any authority error."""

    def __init__(
        self,
        *,
        operator_dir: Path | None = None,
        ledger_path: Path | None = None,
        contracts_dir: Path | None = None,
    ) -> None:
        self._operator_dir = operator_dir
        self._ledger_path = ledger_path
        self._contracts_dir = contracts_dir

    def decisions(self) -> dict[str, Decision]:
        return read_authority(
            self._operator_dir or OPERATOR_DIR, self._ledger_path or PAPER_LEDGER_PATH
        )

    def allows(self, seat: str, tool: str) -> bool:
        try:
            if seat not in EXPECTED_SEAT_IDS:
                return False
            roster = roster_tool_names(self._contracts_dir or DEFAULT_CONTRACTS_DIR, seat)
            if tool not in roster:
                return False
            decision = self.decisions().get(tool_scope(seat, tool))
        except (OperatorChoiceError, OSError, ValueError, sqlite3.Error):
            return False
        return decision is not None and decision.allowed
