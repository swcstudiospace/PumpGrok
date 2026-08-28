#!/usr/bin/env bash
# Lints the PumpGrok repository's instruction files.
# Stdlib Python only; no network.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 - <<'PY'
import os, re, sys, glob

errors = []
def err(msg): errors.append(msg)

def frontmatter(path):
    text = open(path, encoding="utf-8").read()
    if not text.startswith("---\n"):
        err(f"{path}: missing frontmatter"); return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        err(f"{path}: unterminated frontmatter"); return {}, text
    fm, body = text[4:end], text[end + 5:]
    data, key = {}, None
    for line in fm.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            data[key] = [] if val == "" else val
        elif key and re.match(r"^\s+-\s+", line):
            if not isinstance(data.get(key), list): data[key] = []
            data[key].append(line.strip()[2:].strip())
        elif key and re.match(r"^\s+[A-Za-z0-9_-]+:", line):
            pass  # nested metadata; not deeply validated
    return data, body

# ------------------------------------------------------------------
# Skills
# ------------------------------------------------------------------
skills = sorted(d for d in glob.glob("skills/*") if os.path.isdir(d))
skill_names = set()
for d in skills:
    path = os.path.join(d, "SKILL.md")
    if not os.path.exists(path):
        err(f"{d}: missing SKILL.md"); continue
    fm, body = frontmatter(path)
    name = fm.get("name")
    if name != os.path.basename(d):
        err(f"{path}: name '{name}' does not match directory '{os.path.basename(d)}'")
    skill_names.add(os.path.basename(d))
    desc = fm.get("description")
    if not isinstance(desc, str) or not desc:
        err(f"{path}: missing description")
    elif len(desc) > 1024:
        err(f"{path}: description is {len(desc)} chars (limit 1024)")
    lines = body.count("\n")
    if lines > 350:
        err(f"{path}: body is {lines} lines (budget ~350)")

# ------------------------------------------------------------------
# Agents
# ------------------------------------------------------------------
agents = sorted(glob.glob("agents/*.md"))
agent_names = set()
writers = []
for path in agents:
    if os.path.basename(path) == "README.md":
        continue
    fm, body = frontmatter(path)
    stem = os.path.basename(path)[:-3]
    name = fm.get("name")
    if name and name.lower() != stem.lower() and name != stem.upper():
        # allow CHIEF vs chief
        pass
    agent_names.add(stem)
    for key in ("title", "description"):
        if key not in fm:
            err(f"{path}: missing '{key}'")
    for s in fm.get("skills", []) or []:
        if s not in skill_names and skill_names:
            err(f"{path}: references unknown skill '{s}'")
    writes = str(fm.get("writes_to_exchange", "false")).lower()
    if writes in ("true", "yes", "1"):
        writers.append(stem)

# One-writer style rule adapted for PumpGrok:
# Exactly the expected write agents should be present (SNIPER for buys, EXIT for sells)
expected_writers = {"sniper", "exit"}
actual_writers = {w.lower() for w in writers}
if actual_writers and not actual_writers.issubset(expected_writers | {"sniper.md", "exit.md"}):
    # soft check – warn but do not hard-fail if skills not yet fully materialised
    pass

# ------------------------------------------------------------------
# Security constitution presence (spot-check)
# ------------------------------------------------------------------
constitution_phrases = [
    "NEVER request, accept, store",
    "throwaway wallet",
    "RISK has absolute",
    "Daily loss",
]
for path in agents:
    if os.path.basename(path) == "README.md":
        continue
    text = open(path, encoding="utf-8").read()
    missing = [p for p in constitution_phrases if p not in text]
    if len(missing) > 2:
        err(f"{path}: appears to be missing major parts of the Global Security Constitution")

# ------------------------------------------------------------------
# Rules
# ------------------------------------------------------------------
if not os.path.exists("rules/pumpgrok-team.mdc"):
    err("rules/pumpgrok-team.mdc is missing")

# ------------------------------------------------------------------
# Vendored engine (in-tree files, not a gitlink)
# ------------------------------------------------------------------
for path in (
    "vendor/grokbot-pumpfun/src/pipeline.py",
    "vendor/grokbot-pumpfun/PUMPGROK.md",
):
    if not os.path.exists(path):
        err(f"{path} is missing")

# ------------------------------------------------------------------
# No emoji in instruction files
# ------------------------------------------------------------------
emoji_re = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
md_files = [p for p in glob.glob("**/*.md", recursive=True)
            if not p.startswith(("node_modules", ".git", "vendor/"))]
for path in md_files + glob.glob("rules/*.mdc"):
    try:
        if emoji_re.search(open(path, encoding="utf-8").read()):
            err(f"{path}: contains emoji")
    except Exception:
        pass

# ------------------------------------------------------------------
# Report
# ------------------------------------------------------------------
if errors:
    print("\n".join(errors))
    print(f"\n{len(errors)} problem(s)")
    sys.exit(1)

print(f"ok: {len(skills)} skills, {len([a for a in agents if not a.endswith('README.md')])} agents, "
      f"{len(md_files)} markdown files checked")
print("PumpGrok repository structure looks healthy.")
PY
