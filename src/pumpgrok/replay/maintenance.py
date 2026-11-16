"""Replay dataset maintenance: ``replay trim`` and ``replay import`` (16-04).

Every function here is deterministic and network-free: no transport, RPC or LLM client is
imported. ``root`` is the operator's ``var`` directory. Datasets live under
``<root>/datasets/<name>``; an imported ledger lives under ``<root>/replay/<name>``.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Callable
from pathlib import Path

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore
from pumpgrok.replay.fixtures import (
    EVENTS_NAME,
    CorruptFixture,
    FixtureManifest,
    load_dataset,
)
from pumpgrok.replay.live_recorder import GAPS_NAME, seal_directory
from pumpgrok.replay.rng import make_rng

__all__ = ["MaintenanceRefused", "TRIM_KEEP_FRACTION", "import_dataset", "trim"]

# Events of mints without an order are kept with this probability, drawn from the seeded RNG.
TRIM_KEEP_FRACTION = 0.05
IMPORTED_LEDGER_NAME = "imported-ledger.sqlite"
IMPORTED_DIGEST_NAME = IMPORTED_LEDGER_NAME + ".sha256"


class MaintenanceRefused(PumpgrokError):
    """A maintenance request this module refuses, before anything is written.

    ``fields["kind"]`` selects the CLI exit code: ``usage`` (bad name, missing input, existing
    target, nothing to keep) exits 1; ``ledger`` (a ledger that fails verification or holds a row
    this desk did not record) exits 2.
    """

    code = "maintenance_refused"


def _plain_name(name: str) -> str:
    try:
        FixtureManifest._plain_dataset_name(name)
    except ValueError:
        raise MaintenanceRefused("dataset name is not a plain name", kind="usage") from None
    return name


def _verified_bytes(dataset_dir: Path, manifest: FixtureManifest, name: str) -> bytes:
    """Read one listed file again and check it against its manifest digest."""
    data = (dataset_dir / name).read_bytes()
    if hashlib.sha256(data).hexdigest() != manifest.sha256[name]:
        raise CorruptFixture("sha256 does not match manifest", file=name)
    return data


def _write_new(path: Path, data: bytes) -> None:
    """Create a file that must not exist, and make its bytes durable."""
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def trim(
    name: str,
    *,
    root: Path,
    max_events: int,
    seed: int,
    mints_with_orders: Callable[[Path], frozenset[str]],
) -> Path:
    """Write ``<name>-trimmed``: every event of a mint with an order, a seeded 5 percent of the
    rest, then the last ``max_events`` of those kept events in file order.

    ``mints_with_orders`` names the mints that hold an order row when the source dataset is
    replayed. The RNG is drawn only for events of mints without an order, in file order, so one
    seed gives one output. ``gaps.jsonl`` is copied unchanged when the source lists it. No gap is
    inserted and ``feed.jsonl`` is not carried over.
    """
    if type(max_events) is not int or max_events <= 0:
        raise MaintenanceRefused("max-events must be a positive integer", kind="usage")
    _plain_name(name)
    source = root / "datasets" / name
    if not source.is_dir():
        raise MaintenanceRefused(f"dataset not found: {name}", kind="usage")
    dataset = load_dataset(source)
    manifest = dataset.manifest
    events_bytes = _verified_bytes(source, manifest, EVENTS_NAME)
    lines = events_bytes.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    if len(lines) != len(dataset.events):
        raise CorruptFixture("event line count does not match the loaded events", file=EVENTS_NAME)

    orders = mints_with_orders(source)
    rng = make_rng(seed)
    kept: list[tuple[bytes, dict[str, object]]] = []
    for raw, event in zip(lines, dataset.events, strict=True):
        if event.get("mint") in orders or rng.random() < TRIM_KEEP_FRACTION:
            kept.append((raw, event))
    kept = kept[-max_events:]
    if not kept:
        raise MaintenanceRefused("trim keeps no events", kind="usage")

    target = root / "datasets" / f"{name}-trimmed"
    if target.exists():
        raise MaintenanceRefused(f"target exists: {target.name}", kind="usage")
    target.mkdir(parents=True)
    try:
        _write_new(target / EVENTS_NAME, b"".join(raw + b"\n" for raw, _ in kept))
        if GAPS_NAME in manifest.sha256:
            _write_new(target / GAPS_NAME, _verified_bytes(source, manifest, GAPS_NAME))
        sources = {str(event["source"]): str(event["source"]) for _, event in kept}
        seal_directory(
            target,
            recorded_from_utc=str(kept[0][1]["ts_utc"]),
            recorded_to_utc=str(kept[-1][1]["ts_utc"]),
            sources=sources,
            seed_hint=seed,
            notes=(
                f"Trimmed from {name}: keep every event of a mint with an order, "
                f"a seeded {TRIM_KEEP_FRACTION:.0%} of the rest, last {max_events} kept"
            ),
        )
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target


def _verify_paper_ledger(path: Path) -> None:
    """Refuse unless the ledger verifies from genesis and every row was recorded by paper."""
    try:
        store = LedgerStore(str(path))
    except sqlite3.Error:
        raise MaintenanceRefused(
            "ledger is not a readable sqlite database", kind="ledger"
        ) from None
    try:
        store.verify()
        rows = store.read(limit=None)
    except (LedgerInconsistent, sqlite3.Error):
        raise MaintenanceRefused("ledger does not verify from genesis", kind="ledger") from None
    finally:
        store.close()
    if not rows:
        raise MaintenanceRefused("ledger holds no rows", kind="ledger")
    if any(row["source"] != "paper" for row in rows):
        raise MaintenanceRefused("ledger holds a row whose source is not paper", kind="ledger")


def import_dataset(ledger: Path, *, name: str, root: Path) -> Path:
    """Copy a ledger this desk recorded to ``<root>/replay/<name>/imported-ledger.sqlite``.

    Accepted only when the ledger verifies from genesis and every row's source is ``paper``
    (owner decision 1, 2026-11-15). The verified bytes are copied unchanged, the copy is read
    back and matched to their sha256, and the digest is written beside it in ``sha256sum`` form.
    Nothing is converted. An existing target is refused before anything is written.
    """
    _plain_name(name)
    if not ledger.is_file():
        raise MaintenanceRefused("ledger file not found", kind="usage")
    data = ledger.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory() as scratch:
        candidate = Path(scratch) / IMPORTED_LEDGER_NAME
        candidate.write_bytes(data)
        _verify_paper_ledger(candidate)
    target = root / "replay" / name
    if target.exists():
        raise MaintenanceRefused(f"target exists: {name}", kind="usage")
    try:
        target.mkdir(parents=True)
    except FileExistsError:
        raise MaintenanceRefused(f"target exists: {name}", kind="usage") from None
    try:
        _write_new(target / IMPORTED_LEDGER_NAME, data)
        copied = (target / IMPORTED_LEDGER_NAME).read_bytes()
        if hashlib.sha256(copied).hexdigest() != digest:
            raise MaintenanceRefused(
                "copied ledger does not match the verified bytes", kind="ledger"
            )
        _write_new(target / IMPORTED_DIGEST_NAME, f"{digest}  {IMPORTED_LEDGER_NAME}\n".encode())
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target
