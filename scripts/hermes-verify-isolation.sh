#!/usr/bin/env bash
# Verify PumpGrok Hermes profile isolation and file-bus layout.
# Exit 0 if healthy. Prints problems otherwise.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DESK="${PUMPGROK_DESK:-${HOME}/trading-desk}"
HERMES_BASE="${HERMES_BASE:-${HOME}/.hermes}"
PROFILES_DIR="${HERMES_BASE}/profiles"
errors=0

err() { echo "FAIL: $*" >&2; errors=$((errors + 1)); }
ok() { echo "ok: $*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --desk) DESK="$2"; shift 2 ;;
    --hermes-base) HERMES_BASE="$2"; PROFILES_DIR="${HERMES_BASE}/profiles"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--desk PATH] [--hermes-base PATH]"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

ROLES=(chief scout risk whale sniper rug exit shill)
CRON_OWNERS=(chief scout risk rug)
FORBIDDEN_ROLES=(sniper exit)
FORBIDDEN_KEYS='PRIVATE_KEY|SECRET_KEY|SEED|MNEMONIC|PHANTOM|WALLET_SECRET'

[[ -f "${ROOT}/hermes/profiles.yaml" ]] || err "missing hermes/profiles.yaml"
[[ -f "${ROOT}/hermes/cron/jobs.yaml" ]] || err "missing hermes/cron/jobs.yaml"
[[ -f "${ROOT}/tools/desk_state.py" ]] || err "missing tools/desk_state.py"
[[ -f "${ROOT}/skills/hermes-cron-desk/SKILL.md" ]] || err "missing hermes-cron-desk skill"

for prompt in scout-discover risk-audit chief-pickup rug-watch chief-journal; do
  [[ -f "${ROOT}/hermes/cron/prompts/${prompt}.md" ]] || err "missing prompt ${prompt}.md"
done

if grep -Eq 'owner:[[:space:]]*(sniper|exit)' "${ROOT}/hermes/cron/jobs.yaml"; then
  err "jobs.yaml assigns cron to sniper or exit"
else
  ok "jobs.yaml has no sniper/exit owners"
fi

[[ -d "${DESK}" ]] || err "desk missing: ${DESK}"
for child in proposals briefs leads research journal incidents positions watch; do
  [[ -d "${DESK}/${child}" ]] || err "desk child missing: ${DESK}/${child}"
done
[[ -f "${DESK}/desk.md" ]] || err "missing ${DESK}/desk.md"
if grep -Ei 'engagement:[[:space:]]*micro-live' "${DESK}/desk.md"; then
  err "desk.md engagement is micro-live; cron state machine is research/paper only"
else
  ok "desk.md present"
fi

for role in "${ROLES[@]}"; do
  home="${PROFILES_DIR}/${role}"
  [[ -d "${home}" ]] || { err "profile missing: ${home}"; continue; }
  [[ -f "${home}/SOUL.md" ]] || err "${role}: missing SOUL.md"
  [[ -f "${home}/MEMORY.md" ]] || err "${role}: missing MEMORY.md"
  [[ -f "${home}/config.yaml" ]] || err "${role}: missing config.yaml"
  [[ -f "${home}/.env" ]] || err "${role}: missing .env"
  [[ -f "${home}/.no-bundled-skills" ]] || err "${role}: missing .no-bundled-skills"
  if [[ "${home}" == "${HERMES_BASE}" ]]; then
    err "${role} home collapsed onto default HERMES_HOME"
  fi
  if grep -Eq "${FORBIDDEN_KEYS}" "${home}/.env"; then
    err "${role}: forbidden wallet/key material in .env"
  fi
  if [[ "${role}" != "chief" ]] && grep -Eq '^[[:space:]]*TELEGRAM_BOT_TOKEN=.' "${home}/.env"; then
    err "${role}: TELEGRAM_BOT_TOKEN set (only chief may hold it)"
  fi
  if ! grep -q "home_mode: profile" "${home}/config.yaml"; then
    err "${role}: config.yaml missing terminal.home_mode: profile"
  fi
  if grep -qi "personal assistant" "${home}/MEMORY.md"; then
    err "${role}: MEMORY.md looks copied from default profile"
  fi
done

for role in "${FORBIDDEN_ROLES[@]}"; do
  cron_dir="${PROFILES_DIR}/${role}/cron"
  if [[ -d "${cron_dir}" ]] && find "${cron_dir}" -name 'jobs.json' -o -name '*.json' 2>/dev/null | grep -q .; then
    if command -v hermes >/dev/null 2>&1; then
      if hermes -p "${role}" cron list 2>/dev/null | grep -Eqi 'discover|pickup|watch|audit|journal'; then
        err "${role}: desk cron jobs present (forbidden owner)"
      fi
    fi
  fi
done

if command -v python3 >/dev/null 2>&1; then
  if ! PUMPGROK_ROOT="${ROOT}" PUMPGROK_DESK="${DESK}" python3 "${ROOT}/tools/desk_state.py" status >/tmp/pumpgrok-desk-status.json; then
    err "desk_state.py status failed"
  else
    ok "desk_state.py status"
  fi
fi

if command -v hermes >/dev/null 2>&1; then
  hermes profile list || true
  for owner in "${CRON_OWNERS[@]}"; do
    hermes -p "${owner}" cron list || true
  done
else
  echo "WARN: hermes CLI not on PATH; skipped profile list / cron list"
fi

echo
if [[ ${errors} -gt 0 ]]; then
  echo "${errors} isolation problem(s)"
  exit 1
fi
echo "PumpGrok Hermes isolation looks healthy."
