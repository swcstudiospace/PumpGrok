# Set up the PumpGrok Solana Memecoin Trading Desk

You are a Grok Bot building the user’s Solana memecoin trading desk from this repository.  
Follow this file **top to bottom**. When you finish, the user has eight specialist Bots, a full skill library, a tools layer, a Trading Floor group chat, and a written desk record.

Setup is **read-only**. No keys, no real trades, no private-key handling.

Estimated time: 15–25 minutes.

---

## 1. Get the repository onto the desk computer

```bash
mkdir -p /workspace && cd /workspace
git clone --depth 1 https://github.com/your-org/pumpgrok.git pumpgrok \
  || (curl -L https://github.com/your-org/pumpgrok/archive/refs/heads/main.tar.gz | tar xz && mv pumpgrok-main pumpgrok)
ls /workspace/pumpgrok/agents /workspace/pumpgrok/skills /workspace/pumpgrok/tools /workspace/pumpgrok/rules
```

If GitHub is unavailable, ask the user to upload the archive and unpack it into `/workspace/pumpgrok`.

Confirm the following exist:
- `SETUP.md` (this file)
- `agents/` (8 role files + README)
- `skills/` (skill library)
- `tools/` (Python helpers)
- `rules/pumpgrok-team.mdc`
- `scripts/check.sh`

---

## 2. Read the constitution first

Read these files completely before creating anything:

1. `rules/pumpgrok-team.mdc` – the always-applied desk rule
2. `skills/desk-operating-model/SKILL.md` – roles, evidence standard, security constitution
3. `skills/desk-trade-lifecycle/SKILL.md` – the ticket sequence every trade must follow

These override any conflicting instructions.

---

## 3. Prepare the working directories

```bash
mkdir -p /workspace/trading-desk/{proposals,briefs,leads,research,journal,incidents,positions,watch}
```

Optional but recommended:
```bash
touch /workspace/trading-desk/desk.md
touch /workspace/trading-desk/risk-limits.md
```

---

## 4. Install the skills

For every subdirectory under `/workspace/pumpgrok/skills/`:

1. Read the `SKILL.md`
2. Save it as a named skill using the `name` from its frontmatter
3. If the platform rejects a long skill, create a short pointer skill that says:  
   “When this skill is used, read `/workspace/pumpgrok/skills/<name>/SKILL.md` and follow it exactly.”

Priority skills that must be installed:
- `desk-operating-model`
- `desk-trade-lifecycle`
- `desk-risk-limits`
- `desk-execution-protocol`
- `risk-audit`
- `jupiter-routing`
- `discovery-tools`
- `position-monitoring`
- `tool-connections`
- `pumpgrok-setup`

(The remaining skills can be installed immediately after.)

---

## 5. Create the eight specialist Bots

For each file in `agents/`, create one Bot.

| File            | Name   | Job                              |
|-----------------|--------|----------------------------------|
| agents/chief.md | CHIEF  | Desk Orchestrator                |
| agents/scout.md | SCOUT  | Alpha Hunter / Discovery         |
| agents/risk.md  | RISK   | Absolute Safety Gate             |
| agents/whale.md | WHALE  | Smart-Money Analyst              |
| agents/sniper.md| SNIPER | Single-Write Execution (buys)    |
| agents/rug.md   | RUG    | Post-Entry Safety Monitor        |
| agents/exit.md  | EXIT   | Position Manager (sells only)    |
| agents/shill.md | SHILL  | Sentiment & Velocity             |

For every Bot:
1. Use the **Name** and short **Description** from the file.
2. Paste the full **Standing Instructions** (including the Global Security Constitution) as the first message.
3. Tell the Bot:  
   “These are your standing instructions. Confirm you have read them and state your job in one sentence. Keep them in memory and re-read them whenever you are unsure.”

---

## 6. Create the Trading Floor

Create a group chat named **Trading Floor** containing:

CHIEF, SCOUT, RISK, WHALE, SNIPER, RUG

(EXIT and SHILL can be added later or kept in DMs if the platform limit is six Bots.)

Post this as the first message in the group:

> Welcome to the PumpGrok Trading Floor.  
> CHIEF routes. SCOUT surfaces leads. RISK is the absolute safety gate. WHALE and SHILL provide context only. Only SNIPER may send buys and only EXIT may send sells — both only after RISK clearance + exact human approval by ticket ID.  
> Rules live in `/workspace/pumpgrok/rules/pumpgrok-team.mdc` and `skills/desk-operating-model`.  
> Today is setup: engagement = research. Nothing goes on-chain.

---

## 7. Tools layer (optional but recommended)

The `tools/` directory contains Python helpers that skills prefer over pure browser automation:

```bash
cd /workspace/pumpgrok
pip install requests   # only dependency for most tools
python tools/ticket_helper.py --help
python tools/authority_check.py --help
```

No API key is required. The tools work on public endpoints.  
A private Solana RPC (Helius, QuickNode, etc.) dramatically improves reliability and can be passed with `--rpc`.

---

## 8. Approvals & security

Ask the user to open **Settings → General → Auto-review** (or equivalent) and add a **Require Approval** rule for any financial / transaction-related actions.

Remind the user of the Global Security Constitution:

1. Never request, accept, or store seed phrases or private keys.
2. Capital is a dedicated throwaway wallet ≤ $200 USDC + SOL for fees.
3. Human must explicitly approve every spend by exact ticket ID + mint + size + max slippage.
4. RISK has absolute, non-appealable veto.
5. Daily loss ≥ 5 % → CHIEF freezes all new entries.

---

## 9. Write the desk record

Create or update `/workspace/trading-desk/desk.md` with:

```markdown
# PumpGrok Desk Record
Date: <UTC>
Engagement: research          # research | paper | micro-live
Throwaway wallet: not yet connected
Daily loss limit: 5 %
Bots created: CHIEF, SCOUT, RISK, WHALE, SNIPER, RUG, EXIT, SHILL
Trading Floor: created
Skills installed: <list or “core set”>
Tools available: yes
RPC: public (or private URL if provided)
Notes: Setup complete. No live trading until risk-limits interview and explicit user confirmation.
```

Also create a starter `/workspace/trading-desk/risk-limits.md` that the RISK Bot will fill during the interview.

---

## 10. Verification (smoke tests)

In the Trading Floor run:

1. `@SCOUT brief us on the current top new Solana launches`  
   (or simply confirm SCOUT responds with the LEAD schema)

2. `@RISK explain your mandatory checklist and confirm a KILL is final`

3. `@SNIPER confirm you will never send a transaction without the exact human approval phrase containing ticket ID + mint + size`

4. `@CHIEF what is the current engagement level and process compliance status?`

Optional tool checks:
```bash
python /workspace/pumpgrok/tools/ticket_helper.py
python /workspace/pumpgrok/tools/priority_fee.py
```

---

## 11. Receipt

When everything above is complete, reply to the user with this exact structure:

```
PUMPGROK SETUP COMPLETE
Bots: CHIEF, SCOUT, RISK, WHALE, SNIPER, RUG, EXIT, SHILL
Trading Floor: created
Skills: core set installed
Tools: available
Engagement: research
Wallet: not yet connected
Status: ready for risk-limits interview and tool connections

Next recommended steps for the human:
1. Run the risk-limits interview with RISK / CHIEF
2. Connect the throwaway wallet via screen hand-off (tool-connections skill)
3. Optionally supply a private RPC URL
4. Only after explicit confirmation move engagement to paper or micro-live
```

---

## Important reminders

- The desk starts in **research** mode. No money moves until the user explicitly raises the engagement level after the risk interview.
- Private keys and seed phrases never enter chat, files, or tools.
- Analysis is never approval. Only the exact human approval phrase unlocks SNIPER or EXIT.
- RISK KILL ends that token path permanently in the current session.

You have now built PumpGrok. Hand control back to the user.
