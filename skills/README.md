# Skills

Thirty-five portable skills that define how the PumpGrok desk operates.

## Core / Bootstrap
| Skill | Purpose | Primary users |
|-------|---------|---------------|
| pumpgrok-setup | Bootstrap the entire desk from zero | CHIEF |
| tool-connections | Browser sessions + wallet hand-off | CHIEF |
| desk-operating-model | Constitution, roles, evidence standard | everyone |
| desk-folders-and-journal | Directory layout and journal conventions | CHIEF, JOURNAL |

## Process & Risk
| Skill | Purpose | Primary users |
|-------|---------|---------------|
| desk-trade-lifecycle | End-to-end ticket stages | CHIEF, SCOUT |
| desk-risk-limits | Capital limits and circuit breakers | RISK, CHIEF |
| desk-execution-protocol | Single-send and pre-send checklist | SNIPER, EXIT |
| risk-audit | Absolute safety gate checklist | RUG |
| desk-monitoring | Desk health and daily P&L | CHIEF |
| desk-post-trade-review | Journal and process grades | JOURNAL |
| desk-incident-response | Playbooks for failures and rugs | CHIEF, RISK |
| desk-strategy-lab | Paper rules and strategy experiments | EXIT, SIGNAL |

## Domain
| Skill | Purpose | Primary users |
|-------|---------|---------------|
| discovery-tools | Lead generation and LEAD schema | SCOUT, WHALE, SHILL |
| jupiter-routing | Preferred execution path | SNIPER, EXIT |
| position-monitoring | Post-entry safety and exit rules | RUG |
| holder-and-flow-analysis | Smart-money and concentration | WHALE |
| social-sentiment | Velocity and quality scoring | SHILL, SCOUT |
| solana-market-data | Price, liquidity, volume | SCOUT, WHALE, SNIPER, RUG, SIGNAL |
| solana-api-reference | Compact endpoint reference | SNIPER |
| solana-rpc-and-wallet | Safe wallet and RPC patterns | SNIPER, EXIT |
| grokbot-pipeline | Dry-run screening engine output as desk evidence via the `tools/pipeline_evidence.py` bridge | everyone |
| browser-ops | CAPTCHA / session hygiene | SHILL |
| hermes-cron-desk | File-bus cron state machine and profile isolation | CHIEF, SCOUT, RISK, RUG, JOURNAL |

## Paper Trading and Safety
| Skill | Purpose | Primary users |
|-------|---------|---------------|
| verification-receipts | Receipt before every completion claim | everyone |
| paper-broker | One paper order per approved ticket | SNIPER, EXIT |
| replay-and-backtest | Deterministic replay before rule promotion | SIGNAL, EXIT |
| live-gate-procedure | Nine live preconditions, read-only | RISK, CHIEF |
| kill-switch | Halt, flatten, and human-only clear | RISK, CHIEF |
| rpc-hygiene | Ordered RPC failover and rate limits | SCOUT, WHALE, SNIPER, RUG, EXIT |
| key-custody | No key material in paper mode | RISK, SNIPER, EXIT |
| safety-scoring | Scored safety report with thresholds | RUG |
| momentum-signals | Evidence-only momentum signals | SIGNAL |
| portfolio-ledger | Ledger reads and reconciliation | JOURNAL, RISK |
| daily-report | Scheduled report rendering | JOURNAL |
| desk-doctor | Desk health proof before trading | everyone |

## Conventions
- Every skill has YAML frontmatter (`name`, `description`)
- Bodies stay focused on purpose, procedure, output schema, and NEVER lists
- Tools under `/workspace/pumpgrok/tools/` are preferred over pure browser when available
- No strategy content, no return claims, no emoji
