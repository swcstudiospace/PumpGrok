# Scripts

Validation and helper scripts for the PumpGrok repository.

| Script | Purpose |
|--------|---------|
| `check.sh` | Lints frontmatter, agent definitions, skill structure, security constitution presence, and the one-writer conventions. No network required. |
| `hermes-bootstrap.sh` | Create eight isolated Hermes profiles (`HERMES_HOME` per role) and the shared `trading-desk` file bus. Does not clone default-profile memory or tokens. |
| `hermes-install-cron.sh` | Install scout/risk/chief/rug cron jobs. Refuses SNIPER/EXIT owners. |

## Usage

```bash
# From the repository root
./scripts/check.sh
./scripts/hermes-bootstrap.sh --desk "$HOME/trading-desk"
./scripts/hermes-install-cron.sh --desk "$HOME/trading-desk"
```

Exit code 0 = healthy.
Non-zero = problems listed on stdout.

## Design notes

- Pure stdlib Python (no external dependencies) for check/state helpers.
- Adapted from the HyperGrok `scripts/check.sh` pattern.
- Enforces:
  - Proper YAML frontmatter on agents and skills
  - Global Security Constitution phrases present in agent files
  - `rules/pumpgrok-team.mdc` exists
  - No emoji in instruction files
  - Soft checks on write-capable agents (SNIPER / EXIT)
- Hermes bootstrap never uses `--clone-all`.
- Cron state machine is research/paper only.
