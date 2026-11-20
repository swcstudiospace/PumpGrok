-- migrate:down
-- M-2026-1120 rollback: drop only the indexes added by the forward file.
-- Data rows are untouched (append-only ledger); rollback plan: run this
-- file, then verify row count equals the pre-migration count.
PRAGMA busy_timeout = 5000;
DROP INDEX IF EXISTS idx_events_ts_seq;
DROP INDEX IF EXISTS idx_events_correlation;
DROP INDEX IF EXISTS idx_events_type_ts;
