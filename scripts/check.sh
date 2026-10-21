#!/usr/bin/env bash
# Lints the PumpGrok repository's instruction files.
# Stdlib Python only; no network. Keep this file ASCII (research Pitfall 10).
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
for path in agents:
    if os.path.basename(path) == "README.md":
        continue
    fm, body = frontmatter(path)
    stem = os.path.basename(path)[:-3]
    agent_names.add(stem)
    for key in ("title", "description"):
        if key not in fm:
            err(f"{path}: missing '{key}'")
    for s in fm.get("skills", []) or []:
        if s not in skill_names and skill_names:
            err(f"{path}: references unknown skill '{s}'")

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
# Vendor pin: the upstream pin lives in docs/VENDOR_PIN.md (STRUCT-001)
# ------------------------------------------------------------------
pin_doc = "docs/VENDOR_PIN.md"
if not os.path.exists(pin_doc):
    err(f"{pin_doc} is missing")
elif "409e74c905faa0e9de42e918efe2c604f206856e" not in open(pin_doc, encoding="utf-8").read():
    err(f"{pin_doc} does not record the vendor pin 409e74c905faa0e9de42e918efe2c604f206856e")

# ------------------------------------------------------------------
# Hermes helper scripts must be executable (./scripts/...)
# ------------------------------------------------------------------
for path in (
    "scripts/hermes-bootstrap.sh",
    "scripts/hermes-install-cron.sh",
    "scripts/hermes-verify-isolation.sh",
):
    if not os.path.exists(path):
        err(f"{path} is missing")
    elif not os.access(path, os.X_OK):
        err(f"{path} is not executable")

# ------------------------------------------------------------------
# Placeholder organisation: `your-org` may remain only in the allowlisted manifests and
# setup docs until STRUCT-007 supplies the real organisation. An allowlisted file that no
# longer contains the placeholder must leave the list, so the list only shrinks.
# ------------------------------------------------------------------
PLACEHOLDER = "your-org"
PLACEHOLDER_ALLOWLIST = {
    ".claude-plugin/marketplace.json",
    ".grok-plugin/marketplace.json",
    "SETUP.md",
}
PLACEHOLDER_SKIP_DIRS = {"docs", "vendor", "var", "node_modules", "__pycache__"}
PLACEHOLDER_SKIP_FILES = {"scripts/check.sh"}  # names the placeholder it checks for

def _walk_text_files():
    for root, dirs, files in os.walk("."):
        dirs[:] = [
            d for d in dirs
            if d not in PLACEHOLDER_SKIP_DIRS
            and (not d.startswith(".") or d in {".github", ".claude-plugin", ".grok-plugin", ".cursor-plugin"})
        ]
        for name in files:
            yield os.path.normpath(os.path.join(root, name))

placeholder_hits = set()
for path in _walk_text_files():
    if path in PLACEHOLDER_SKIP_FILES:
        continue
    try:
        text = open(path, encoding="utf-8").read()
    except (UnicodeDecodeError, OSError):
        continue
    if PLACEHOLDER in text:
        placeholder_hits.add(path)
for path in sorted(placeholder_hits - PLACEHOLDER_ALLOWLIST):
    err(f"{path}: contains placeholder '{PLACEHOLDER}' outside the STRUCT-007 allowlist")
for path in sorted(PLACEHOLDER_ALLOWLIST - placeholder_hits):
    err(f"{path}: on the '{PLACEHOLDER}' allowlist but no longer contains it; remove the entry")

# ------------------------------------------------------------------
# No emoji in instruction files, including the planning docs (research Pitfall 10)
# ------------------------------------------------------------------
emoji_re = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
md_files = [p for p in glob.glob("**/*.md", recursive=True)
            if not p.startswith(("node_modules", ".git", "vendor/"))]
planning_files = glob.glob(".planning/**/*.md", recursive=True)
for path in sorted(set(md_files + planning_files)) + glob.glob("rules/*.mdc"):
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except UnicodeDecodeError as exc:
        err(f"{path}: not valid UTF-8, emoji check cannot run: {exc}")
        continue
    except OSError as exc:
        err(f"{path}: unreadable, emoji check cannot run: {exc}")
        continue
    if emoji_re.search(text):
        err(f"{path}: contains emoji")

# ------------------------------------------------------------------
# Report
# ------------------------------------------------------------------
if errors:
    print("\n".join(errors))
    print(f"\n{len(errors)} problem(s)")
    sys.exit(1)

print(f"ok: {len(skills)} skills, {len([a for a in agents if not a.endswith('README.md')])} agents, "
      f"{len(md_files) + len(planning_files)} markdown files checked")
print("PumpGrok repository structure looks healthy.")
PY
