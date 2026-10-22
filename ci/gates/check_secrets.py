#!/usr/bin/env python3
"""Gate G-3 — committed secrets.

A secret that reaches git is disclosed: the object stays in history, in every clone and fork, and
on any CI or mirror that fetched it. Detection at commit time is the only cheap moment.

This is a net, not a guarantee. Custom formats and split credentials pass it, which is why a human
review still looks.

    python3 ci/gates/check_secrets.py --base origin/main
    python3 ci/gates/check_secrets.py --files path/to/file.py
    python3 ci/gates/check_secrets.py --staged          # pre-commit hook mode
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST_MARKER = "pragma: allowlist secret"

# (name, pattern, description)
PATTERNS: list[tuple[str, str, str]] = [
    ("aws_access_key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b", "AWS access key id"),
    (
        "aws_secret",
        r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})",
        "AWS secret access key",
    ),
    ("github_token", r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", "GitHub token"),
    ("github_pat", r"\bgithub_pat_[A-Za-z0-9_]{60,}\b", "GitHub fine-grained PAT"),
    ("gitlab_token", r"\bglpat-[A-Za-z0-9\-_]{20,}\b", "GitLab token"),
    ("slack_token", r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b", "Slack token"),
    ("stripe_live", r"\b[sr]k_live_[A-Za-z0-9]{20,}\b", "Stripe live key"),
    ("google_api", r"\bAIza[0-9A-Za-z\-_]{30,}", "Google API key"),
    ("openai", r"\bsk-(?:proj-)?[A-Za-z0-9\-_]{32,}\b", "OpenAI-style API key"),
    ("anthropic", r"\bsk-ant-[A-Za-z0-9\-_]{32,}\b", "Anthropic API key"),
    (
        "private_key",
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
        "private key block",
    ),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b", "JWT"),
    (
        "conn_string",
        r"(?i)\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis|amqp)://"
        r"[^:\s/]+:[^@\s/]+@",
        "connection string with inline credentials",
    ),
    ("npm_token", r"\bnpm_[A-Za-z0-9]{36}\b", "npm token"),
    ("twilio", r"\bSK[0-9a-fA-F]{32}\b", "Twilio key"),
    ("sendgrid", r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b", "SendGrid key"),
    ("pypi_token", r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{50,}\b", "PyPI token"),
    ("solana_base58_key", r"\b[1-9A-HJ-NP-Za-km-z]{86,88}\b", "Solana 64-byte secret key, base58"),
    (
        "solana_json_keypair",
        r"\[\s*(?:\d{1,3}\s*,\s*){63}\d{1,3}\s*\]",
        "Solana keypair as JSON byte array",
    ),
    (
        "helius_url_key",
        r"(?i)helius(?:-rpc)?\.com/[^\s\"']*api-key=[A-Za-z0-9-]{20,}",
        "Helius RPC URL with key",
    ),
    (
        "quicknode_url",
        r"(?i)[a-z0-9-]+\.solana-mainnet\.quiknode\.pro/[A-Za-z0-9]{20,}",
        "QuickNode endpoint with token",
    ),
    ("telegram_bot_token", r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b", "Telegram bot token"),
    ("xai_key", r"\bxai-[A-Za-z0-9]{32,}\b", "x.ai API key"),
]

# Variable names that make a high-entropy value suspicious.
# NOTE: \b does not fire inside snake_case ('_' is a word character), so 'api_secret'
# would not match a \bsecret\b pattern. Allow an optional leading separator instead.
SECRET_NAME_RE = re.compile(
    r"(?i)(?:^|[^A-Za-z0-9]|_)(?:secret|password|passwd|pwd|token|api[_-]?key|apikey|auth|"
    r"credential|private[_-]?key|access[_-]?key|client[_-]?secret|encryption[_-]?key|"
    r"keypair|mnemonic|seed[_-]?phrase|wallet[_-]?secret)"
    r"(?:[^A-Za-z0-9]|_|$)"
)
ASSIGNMENT_RE = re.compile(r"""['"]([A-Za-z0-9+/=_\-]{20,})['"]""")

# Values that look high-entropy but are placeholders.
PLACEHOLDER_RE = re.compile(
    r"(?i)^(?:x{4,}|\*{4,}|\.{3,}|<[^>]+>|\$\{[^}]+\}|changeme|placeholder|example|"
    r"your[_-]?\w+[_-]?here|dummy|redacted|sample|test[_-]?\w*|fake[_-]?\w*|"
    r"[0]{8,}|[a]{8,}|abcdef\w*|deadbeef\w*)$"
)

SKIP_DIRS = {
    ".git",
    "node_modules",
    "target",
    "build",
    "dist",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    "vendor",
    "Pods",
    ".gradle",
    ".terraform",
}
SKIP_EXT = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".pdf",
    ".zip",
    ".gz",
    ".jar",
    ".apk",
    ".ipa",
    ".so",
    ".dylib",
    ".dll",
    ".woff",
    ".woff2",
    ".ttf",
    ".mp4",
    ".mp3",
    ".webp",
    ".lock",
}

# Terraform state holds resource attributes verbatim, including generated passwords. Solana
# keypair files are JSON byte arrays and carry no other marker, so their names are flagged.
ALWAYS_FLAG_FILES = {
    "terraform.tfstate",
    "terraform.tfstate.backup",
    ".env",
    "id_rsa",
    "id_ed25519",
    "id.json",
    "keypair.json",
    "wallet.json",
}


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {c: s.count(c) / len(s) for c in set(s)}
    return -sum(p * math.log2(p) for p in freq.values())


def is_placeholder(value: str) -> bool:
    if PLACEHOLDER_RE.match(value):
        return True
    # A value with very few distinct characters is not a real credential.
    return len(set(value)) < 6


def scan_line(path: str, lineno: int, line: str) -> list[dict]:
    if ALLOWLIST_MARKER in line:
        return []

    hits: list[tuple[str, str, str]] = []  # (rule, desc, secret value)

    for name, pattern, desc in PATTERNS:
        for m in re.finditer(pattern, line):
            hits.append((name, desc, m.group(0)))

    # High-entropy value assigned to a suspiciously named variable.
    if SECRET_NAME_RE.search(line):
        for m in ASSIGNMENT_RE.finditer(line):
            value = m.group(1)
            if is_placeholder(value):
                continue
            if shannon_entropy(value) > 3.5:
                desc = "high-entropy value assigned to a secret-named variable"
                hits.append(("high_entropy", desc, value))

    # Every flagged value on the line is masked in every excerpt. A line can carry several
    # credentials; masking only the value a finding names would print the others.
    secrets = [value for _, _, value in hits]
    return [
        {
            "file": path,
            "line": lineno,
            "rule": rule,
            "desc": desc,
            "excerpt": _redact(line, secrets),
        }
        for rule, desc, _ in hits
    ]


def _mask(secret: str) -> str:
    keep = 4
    return secret[:keep] + "*" * max(4, len(secret) - keep) if len(secret) > keep else "****"


def _redact(line: str, secrets: list[str]) -> str:
    # Collect every occurrence of every secret, then mask the merged spans. Overlapping secrets
    # then leave no fragment of either behind.
    spans: list[tuple[int, int]] = []
    for secret in set(secrets):
        if not secret:
            continue
        start = line.find(secret)
        while start != -1:
            spans.append((start, start + len(secret)))
            start = line.find(secret, start + 1)
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    parts: list[str] = []
    pos = 0
    for start, end in merged:
        parts.append(line[pos:start])
        parts.append(_mask(line[start:end]))
        pos = end
    parts.append(line[pos:])
    return "".join(parts).strip()[:160]


def _forbidden(rel: str) -> list[dict]:
    return [
        {
            "file": rel,
            "line": 0,
            "rule": "forbidden_file",
            "desc": f"{Path(rel).name} must never be committed "
            "(holds credentials in plain text)",
            "excerpt": "",
        }
    ]


def _scan_text(rel: str, text: str) -> list[dict]:
    findings: list[dict] = []
    for i, line in enumerate(text.splitlines(), start=1):
        if len(line) > 4000:  # minified bundle
            continue
        findings.extend(scan_line(rel, i, line))
    return findings


def scan_file(path: Path, rel: str) -> list[dict]:
    if Path(rel).name in ALWAYS_FLAG_FILES:
        return _forbidden(rel)

    if path.suffix.lower() in SKIP_EXT:
        return []

    try:
        text = path.read_text(errors="replace")
    except (OSError, UnicodeDecodeError):
        return []

    return _scan_text(rel, text)


def scan_blob(rel: str, blob: str) -> list[dict]:
    """Scan the staged content of rel, which is the index object `blob`, not the worktree file."""
    if Path(rel).name in ALWAYS_FLAG_FILES:
        return _forbidden(rel)

    if Path(rel).suffix.lower() in SKIP_EXT:
        return []

    return _scan_text(rel, _git(["cat-file", "blob", blob]))


def _git(args: list[str]) -> str:
    try:
        out = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            cwd=REPO_ROOT,
        )
    except subprocess.CalledProcessError as exc:
        # A failed diff must not read as "no files to scan": that would print PASS on a tree
        # that was never scanned.
        sys.exit(f"check_secrets: git {' '.join(args[:2])} failed: {exc.stderr}")
    return out.stdout


def changed_files(base: str) -> list[str]:
    # -z: plain output quotes non-ASCII names, and a quoted name names no file on disk.
    raw = _git(["diff", "--name-only", "-z", f"{base}...HEAD"])
    return [name for name in raw.split("\0") if name]


def staged_blobs() -> dict[str, str]:
    """Map each staged path to the index blob that a commit would record.

    --no-renames reports a rename as a delete plus an add, so the destination is scanned
    under its new path. Gitlinks (mode 160000) are submodule pointers with no file content.
    """
    raw = _git(["diff", "--cached", "--raw", "-z", "--no-renames", "--diff-filter=ACMT"])
    parts = raw.split("\0")
    blobs: dict[str, str] = {}
    for meta, path in zip(parts[0::2], parts[1::2]):
        _src_mode, dst_mode, _src_sha, dst_sha, _status = meta.lstrip(":").split()
        if dst_mode != "160000":
            blobs[path] = dst_sha
    return blobs


def main() -> int:
    ap = argparse.ArgumentParser(description="Gate G-3: committed secrets")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--staged", action="store_true", help="Scan staged files (pre-commit)")
    ap.add_argument("--all", action="store_true", help="Scan the whole tree")
    ap.add_argument("--root", type=Path, default=REPO_ROOT)
    args = ap.parse_args()

    root = args.root.resolve()

    staged_index: dict[str, str] | None = None
    if args.files is not None:
        targets = args.files
    elif args.staged:
        # The index is what a commit records; the working tree may hold something else.
        staged_index = staged_blobs()
        targets = list(staged_index)
    elif args.all:
        targets = [
            str(p.relative_to(root))
            for p in root.rglob("*")
            if p.is_file() and not any(part in SKIP_DIRS for part in p.parts)
        ]
    else:
        targets = changed_files(args.base)

    if not targets:
        print("G-3 PASS — no files to scan")
        return 0

    findings: list[dict] = []
    for rel in targets:
        if any(part in SKIP_DIRS for part in Path(rel).parts):
            continue
        if staged_index is not None:
            findings.extend(scan_blob(rel, staged_index[rel]))
            continue
        path = root / rel
        if not path.exists() or not path.is_file():
            continue
        findings.extend(scan_file(path, rel))

    if findings:
        print(f"G-3 FAIL — {len(findings)} potential secret(s)", file=sys.stderr)
        for f in findings:
            loc = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
            print(f"  {loc}", file=sys.stderr)
            print(f"    {f['rule']}: {f['desc']}", file=sys.stderr)
            if f["excerpt"]:
                print(f"    {f['excerpt']}", file=sys.stderr)
        print(
            "\n  If a hit is real, the secret is COMPROMISED. "
            "Rotate it first, then clean history.\n"
            "  If it is a false positive, add '# pragma: allowlist secret' with a reason.\n"
            "  See skills/security/secrets-handling/SKILL.md",
            file=sys.stderr,
        )
        return 1

    print(f"G-3 PASS — {len(targets)} file(s) scanned, no secrets detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
