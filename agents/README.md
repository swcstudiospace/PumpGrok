# Agents

Eight specialist Bots that form the **PumpGrok** Solana memecoin trading desk.

| File       | Name   | Job                          | Writes to Exchange |
|------------|--------|------------------------------|--------------------|
| chief.md   | CHIEF  | Desk Orchestrator            | No                 |
| scout.md   | SCOUT  | Alpha Hunter / Discovery     | No                 |
| risk.md    | RISK   | Absolute Safety Gate         | No                 |
| whale.md   | WHALE  | Smart-Money Analyst          | No                 |
| sniper.md  | SNIPER | Single-Write Execution       | Yes                |
| rug.md     | RUG    | Post-Entry Safety Monitor    | No                 |
| exit.md    | EXIT   | Position Manager             | Yes                |
| shill.md   | SHILL  | Sentiment & Velocity         | No                 |

Each file contains:
- YAML frontmatter (name, title, description, seat, skills, writes_to_exchange)
- Bot profile
- Full Standing Instructions including the Global Security Constitution

The `SETUP.md` Bot uses these files to create the specialists.

**How to use when creating a Bot manually**
1. Copy the short **description** into the Bot’s description field.
2. Send the full **Standing Instructions** block as the first message.
3. Tell the Bot: “These are your standing instructions. Confirm you have read them and state your job in one sentence. Keep them in memory and re-read them whenever you are unsure.”
