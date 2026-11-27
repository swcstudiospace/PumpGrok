# Data model - PumpGrok ledger (T1482-data)

Version 1.0. Owner: A07. Engine: SQLite (stdlib sqlite3, A03 blueprint
tech-stack). Paper-only: no live-writable rows exist.

## Entities (as landed in src/pumpgrok/ledger/store.py _SCHEMA)

events(seq PK, ts_utc TEXT NOT NULL ISO9601 UTC, source TEXT NOT NULL
IN {paper,replay,manual}, correlation_id TEXT NOT NULL, idempotency_key
TEXT NOT NULL UNIQUE, type TEXT NOT NULL (18 EventType values),
payload_json TEXT NOT NULL, prev_hash TEXT NOT NULL, hash TEXT NOT NULL
UNIQUE); append-only triggers forbid UPDATE/DELETE.
snapshots(seq PK, ts_utc TEXT NOT NULL, state_json TEXT NOT NULL);
append-only triggers. meta(key PK, value TEXT NOT NULL).

Relationships: none (no FKs): events and snapshots join by seq only,
by convention. Correlation links events of one cycle. Indexes added by
M-2026-1120: idx_events_type_ts(type,ts_utc,seq) for per-type replay
windows, idx_events_correlation(correlation_id,seq) for cycle reads,
idx_events_ts_seq(ts_utc,seq) for time-boxed scans. Index naming
convention: idx_<table>_<columns>. Money/int columns only (ADR-0002);
timestamps from injected Clock only (ADR-0002). Rollback: indexes only,
rows untouched, see migration.rollback plan in handover.
