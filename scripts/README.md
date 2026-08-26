# Scripts

Validation and helper scripts for the PumpGrok repository.

| Script | Purpose |
|--------|---------|
| `check.sh` | Lints frontmatter, agent definitions, skill structure, security constitution presence, and the one-writer conventions. No network required. |

## Usage

```bash
# From the repository root
./scripts/check.sh
```

Exit code 0 = healthy.  
Non-zero = problems listed on stdout.

## Design notes

- Pure stdlib Python (no external dependencies).
- Adapted from the HyperGrok `scripts/check.sh` pattern.
- Enforces:
  - Proper YAML frontmatter on agents and skills
  - Global Security Constitution phrases present in agent files
  - `rules/pumpgrok-team.mdc` exists
  - No emoji in instruction files
  - Soft checks on write-capable agents (SNIPER / EXIT)
