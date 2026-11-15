# Phase 16 gap and grading thresholds: proposal

Status: PROPOSAL. PENDING OWNER APPROVAL. Nothing in this file is pinned.

Owner decision 5 (2026-11-15): CHIEF drafts the gap and grading thresholds and the cooldown, with a reason for each. The owner approves before implementation.

Blocks: plan 16-03 (Task 1 checkpoint). Transitively blocks 16-05, 16-06 and 16-07, because grading and gap flattening feed them.

Rule until approval: no threshold value appears in `src/pumpgrok/backtest/` or `tests/backtest/`. After approval, the approved values are defined once, as `APPROVED_THRESHOLDS` in `src/pumpgrok/backtest/grading.py`. Tests import that object. No other copy is written.

## Proposed values

| Parameter | Proposed value | Used by | Reason |
|---|---|---|---|
| Long dataset: minimum recorded window | 7 days (604800 s) | `grading.py`, check `duration >= long` | Same 7-day floor as `annualization_valid` in the Metrics v2 set (BT-08 names it). A window under 7 days yields `annualization_valid=false`, so a promotion grade should not rest on one. |
| Gap-light: maximum single gap | 300 s | `gaps.py` (gap detection) and `grading.py` (gap-light check) | Equal to the `momentum_breakout` default `lookback_seconds` (300, `src/pumpgrok/strategies/momentum_breakout.py`). A gap longer than the lookback leaves the breakout window with no observed ticks, so a signal there would be judged on no data. |
| Gap-light: maximum total gap time | 5 percent of window duration | `grading.py` | Keeps evidence from being dominated by flattened positions. Judgement, not measurement: the repo holds no measured gap distribution yet. At the 7-day long threshold the budget is 30240 s (about 8 h 24 min). |
| Cooldown after a gap | 300 s, no new entries, counted from gap end | `gaps.py` (entry gate on the segment) | Same 300 s as the lookback. After a gap the strategy window must refill with observed ticks before a new entry. |
| Flatten haircut (reference only) | 500 bps | `gaps.py` | Fixed by ROADMAP Phase 16 criterion 4. Not part of this approval. Listed so the set is complete. |

Gap-light has two limits. A single gap over 300 s is a gap. Total gap time over 5 percent of the window is not gap-light. A window that fails either limit grades `research_only` with reason `gap`.

## Open questions for the owner

1. The definition of "synthetic". 16-03 asks whether it covers datasets built in `tmp_path`. CHIEF proposes yes: such datasets are synthetic and never grade as promotion evidence.
2. Whether the total gap budget should be a percentage (proposed) or a fixed number of seconds.
3. Whether the cooldown counts from gap end (proposed) or gap start.

## Approval record

Fill one row per parameter. Approved values enter code only after this table is complete.

| Parameter | Owner answer (approve, amend to a value with reason, or reject) | Date |
|---|---|---|
| Long dataset: minimum recorded window | | |
| Gap-light: maximum single gap | | |
| Gap-light: maximum total gap time | | |
| Cooldown after a gap | | |
| Open question 1 (synthetic definition) | | |
| Open question 2 (percentage or seconds) | | |
| Open question 3 (cooldown start) | | |
