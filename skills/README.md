# Skills

Twenty-three portable skills that define how the PumpGrok desk operates.

## Core / Bootstrap
| Skill | Purpose | Primary users |
|-------|---------|---------------|
| pumpgrok-setup | Bootstrap the entire desk from zero | First Bot / CHIEF |
| tool-connections | Browser sessions + wallet hand-off | CHIEF, all |
| desk-operating-model | Constitution, roles, evidence standard | everyone |
| desk-folders-and-journal | Directory layout and journal conventions | everyone |

## Process & Risk
| Skill | Purpose | Primary users |
|-------|---------|---------------|
| desk-trade-lifecycle | End-to-end ticket stages | CHIEF, everyone |
| desk-risk-limits | Capital limits and circuit breakers | RISK, CHIEF |
| desk-execution-protocol | Single-send and pre-send checklist | SNIPER, EXIT |
| risk-audit | Absolute safety gate checklist | RISK |
| desk-monitoring | Desk health and daily P&L | CHIEF |
| desk-post-trade-review | Journal and process grades | CHIEF, EXIT |
| desk-incident-response | Playbooks for failures and rugs | CHIEF, all |
| desk-strategy-lab | Paper rules and strategy experiments | CHIEF |

## Domain
| Skill | Purpose | Primary users |
|-------|---------|---------------|
| discovery-tools | Lead generation and LEAD schema | SCOUT |
| jupiter-routing | Preferred execution path | SNIPER, EXIT |
| position-monitoring | Post-entry safety and exit rules | RUG, EXIT |
| holder-and-flow-analysis | Smart-money and concentration | WHALE |
| social-sentiment | Velocity and quality scoring | SHILL |
| solana-market-data | Price, liquidity, volume | SCOUT, RISK, SNIPER |
| solana-api-reference | Compact endpoint reference | SNIPER, RISK |
| solana-rpc-and-wallet | Safe wallet and RPC patterns | SNIPER, RISK |
| grokbot-pipeline | Dry-run screening engine output as desk evidence | SCOUT, RISK, CHIEF |
| browser-ops | CAPTCHA / session hygiene | all |

## Conventions
- Every skill has YAML frontmatter (`name`, `description`)
- Bodies stay focused on purpose, procedure, output schema, and NEVER lists
- Tools under `/workspace/pumpgrok/tools/` are preferred over pure browser when available
- No strategy content, no return claims, no emoji
