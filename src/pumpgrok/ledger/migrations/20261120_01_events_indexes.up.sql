-- migrate:up
-- M-2026-1120 v2026.11.20-01 (T1482-data, correlation 1482cee0-ef94-43e4-8400-e343d6141fbe)
-- Additive expand: indexes for the bound access patterns only. No column,
-- type or row change. SQLite (blueprint tech-stack: stdlib sqlite3 ledger);
-- busy_timeout 5000 ms matches store.py _SCHEMA.
PRAGMA busy_timeout = 5000;
CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events (type, ts_utc, seq);
CREATE INDEX IF NOT EXISTS idx_events_correlation ON events (correlation_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_ts_seq ON events (ts_utc, seq);
