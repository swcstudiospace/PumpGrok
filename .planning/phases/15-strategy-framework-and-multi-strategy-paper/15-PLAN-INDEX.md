# Phase 15 plan index: Strategy framework and multi-strategy paper

Source: 15-CONTEXT.md plan list, authoritative. Goal: a frozen Strategy protocol, a static registry, a runtime with read-only contexts and per-strategy capital slices; legacy_screening parity; three baselines with bounded version-controlled params and fixtures; fee v2 default with the one deliberate trading-smoke move; live-paper root and Intent router that provably cannot send.

| Plan | Title | Seat | Wave | Depends on | PR / Branch | Tasks |
|---|---|---|---|---|---|---|
| 15-01 | Ledger readers and allocation, ParamSet generalization, fee v2 default flip with trading-smoke re-pin | bot-02-risk | 1 | 11-01, 12-01, 13-03 | PR-23 bot-02-risk/v4-p15-strategy-framework | 5 |
| 15-02 | Strategy core: protocol, registry, runtime, tape, attribution, paper-event overlay | bot-02-risk | 2 | 11-04, 12-01, 12-02, 13-01, 15-01 | PR-23 same branch | 5 |
| 15-03 | memefilters, legacy_screening wrapper with parity, restart-recovery library half | bot-02-risk | 3 | 12-02, 15-01, 15-02 | PR-23 same branch | 4 |
| 15-04 | momentum_breakout and new_launch_sniper with bounds and fixtures | bot-02-risk | 4 | 15-01, 15-02, 15-03 | PR-23 same branch | 5 |
| 15-05 | mean_reversion with bounds and fixture, serialized after 15-04 | bot-02-risk | 5 | 15-01, 15-02, 15-03, 15-04 | PR-23 same branch | 4 |
| 15-06 | ExitRules ticket filter and live-data paper root; Intent router with ticket and approval allocation | bot-00-chief | 3 | 11-01, 13-01, 13-02, 13-03, 14-03, 15-01, 15-02 | PR-24 bot-00-chief/v4-p15-paper-root-router | 4 |
| 15-07 | CHANGELOG entry: equal smoke-10m pair, moved trading-smoke pair | bot-09-journal | 6 | 15-01 to 15-06 | PR-25 bot-09-journal/v4-p15-changelog | 2 |
| 15-08 | Phase 15 close: STATE, verification record, progress table via staged drafts | bot-00-chief | 7 | 15-01 to 15-07 | PR-26 bot-00-chief/v4-p15-close | 3 |

Task total: 32. Waves: 1, 2, 3 (15-03 risk plus 15-06 chief, disjoint files), 4, 5, 6, 7.

Seat purity: every files_modified path resolves to its plan seat under ownership.yaml via resolve_owner. risk owns src/pumpgrok/strategies via the src/pumpgrok catch-all, ledger, upgrade, backtest, config, tests/strategies via tests catch-all, tests/upgrade, tests/backtest via tests catch-all, tests/config via tests catch-all, tests/fixtures/replay via explicit risk pattern, src/pumpgrok/cli/backtest.py via the src/pumpgrok catch-all since only src/pumpgrok/cli.py the file is chief-owned. chief owns supervisor and tests/desk. journal owns CHANGELOG.md and .jsonl fixture outputs are risk-owned inputs here, not journal edits. chief owns .planning.

Shared-file order: registry.py and upgrade_bounds.toml serialize 15-03 legacy entry, then 15-04 two baselines, then 15-05 reversion, alphabetical sections per G-02. Strategies __init__.py is created minimal in 15-01 and extended in 15-02, serialized across waves 1 and 2.

Boundary notes honored: no RiskEngine row added or changed anywhere in this phase (slice enforcement is 17-01 on existing rows); .planning writes in 15-08 are staged drafts applied by chief at the ship checkpoint; executors write SUMMARIES and receipt fragments under /tmp/v4/summaries only and return 150 words; no full pytest -q anywhere; live stays refused exit 3; receipts never carry approved_by.

Resolved CONTEXT inconsistencies: the truncated pins line in 15-CONTEXT resolves to trading_smoke.json plus trading_smoke_rows.json per plans.json; cli/backtest glob resolves to src/pumpgrok/cli/backtest.py which is risk-owned; the 15-08 .planning file list resolves to staged drafts plus chief checkpoint application.

Plan check feedback applied (15-PLAN-CHECK.md PASS with warnings): W1 in 15-01, the parity test constructs bare FeeModel exactly as the paper adapter does and the sniper-owned fees.py default is flagged as a foreign file for a companion plan; W2 in 15-07, OLD versus NEW difference assertion with the pinned git log skip-1 recovery command; W3 in 15-06, canonical import-graph and no-signing suites in acceptance; W4 in 15-08, make test fast path in close acceptance. Advisory 1, strategies init created in 15-01 and extended in 15-02. Advisory 2, exit reasons pointer corrected to core adapter EXIT_RULE_REASONS. Waves, dependencies and seat purity unchanged.
