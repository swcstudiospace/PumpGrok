# 10-02 SUMMARY: LIV-01 and LIV-02 import-graph proof, overlays disabled

Two committed safety tests prove no guarded path reaches the live
adapter and every overlay ships with live disabled. No product code
changed. Live stays refused.

## Commits

- 1aae2e3 test(10-02-LIV-01): transitive import-graph proof no guarded path reaches live adapter
- 1a730e7 test(10-02-LIV-02): every overlay ships with live disabled

## Changed files

- tests/safety/test_import_graph_no_live.py (new, Task 1, LIV-01)
- tests/safety/test_live_disabled_overlays.py (new, Task 2, LIV-02)

## Task 1: Import-graph proof with no path to a live adapter (LIV-01)

AST reachability over src/pumpgrok, not a direct-import grep. The test
builds the module map, resolves absolute and relative imports to
internal edges, and takes the closure of each guarded root (backtest
package, execution paper_adapter, upgrade package, supervisor package,
cli). It asserts the closure never contains
pumpgrok.execution.live.live_adapter and no closure file names the
LiveAdapterStub symbol. Imports of the gate module live_gate stay
allowed and are covered by a dedicated test proving the CLI reaches
the gate but not the adapter. Files under execution/live/ are scanned
for network client imports and socket opens. Probe tests pin the
import resolver and all three scanners.

## Task 2: Live disabled in every overlay (LIV-02)

Iterates every TOML file in src/pumpgrok/config/overlays/ and asserts
[live] enabled is False with no exception for the live profile, which
declares intent through execution.mode live yet stays disabled at the
gate. Also pins the exact dev/paper/live profile set and the
LiveSettings enabled default of False.

## Acceptance (exit codes)

- uv run python -m pytest tests/safety/test_import_graph_no_live.py -q: exit 0, 15 passed
- uv run python -m pytest tests/safety/test_live_disabled_overlays.py -q: exit 0, 4 passed
- Overlay shell loop (tomllib assert enabled is False per file): exit 0
- uv run ruff check on both files: exit 0, no issues
- uv run ruff format --check on both files: exit 0
- git -C /root/src/repos/pumpgrok status --short: empty (main checkout untouched)

Note: the runner wrapper prints a "No tests collected" summary line for
-q runs, but the raw pytest output shows 15 and 4 dots with exit 0, and
-v runs report 19 passed. Results above are the raw pytest exit codes.

## Deviations

None. Plan executed exactly as written. No live adapter registered,
no signing or key material, no network call on the live path, no
guard test weakened.
