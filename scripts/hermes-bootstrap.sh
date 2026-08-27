#!/usr/bin/env bash
# Create isolated Hermes profiles for the eight PumpGrok roles.
# Does not copy default-profile memory, sessions, or Telegram tokens.
# Does not install SNIPER/EXIT cron.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DESK="${PUMPGROK_DESK:-${HOME}/trading-desk}"
HERMES_BASE="${HERMES_BASE:-${HOME}/.hermes}"
PROFILES_DIR="${HERMES_BASE}/profiles"
DRY_RUN=0
COPY_PROVIDER_ENV=0

ROLES=(chief scout risk whale sniper rug exit shill)

# Model-provider keys only. Never Telegram, Discord, Slack, or wallet material.
PROVIDER_ALLOWLIST_RE='^(OPENROUTER_API_KEY|OPENAI_API_KEY|ANTHROPIC_API_KEY|NOUS_API_KEY|XAI_API_KEY|GROQ_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|TOGETHER_API_KEY|FIREWORKS_API_KEY|MISTRAL_API_KEY|DEEPSEEK_API_KEY|HERMES_MODEL|MODEL|LLM_MODEL|OPENAI_BASE_URL|OPENROUTER_BASE_URL)='

FORBIDDEN_ENV_RE='(PRIVATE_KEY|SECRET_KEY|SEED|MNEMONIC|PHANTOM|WALLET_SECRET|TELEGRAM_BOT_TOKEN|DISCORD_TOKEN|SLACK_BOT_TOKEN)'

skills_for() {
  case "$1" in
    chief) echo "desk-operating-model desk-trade-lifecycle desk-folders-and-journal pumpgrok-setup hermes-cron-desk" ;;
    scout) echo "discovery-tools solana-market-data social-sentiment desk-trade-lifecycle hermes-cron-desk" ;;
    risk) echo "risk-audit desk-risk-limits holder-and-flow-analysis desk-incident-response hermes-cron-desk" ;;
    whale) echo "holder-and-flow-analysis solana-market-data solana-api-reference" ;;
    sniper) echo "desk-execution-protocol jupiter-routing tool-connections" ;;
    rug) echo "desk-monitoring risk-audit holder-and-flow-analysis position-monitoring hermes-cron-desk" ;;
    exit) echo "position-monitoring desk-post-trade-review jupiter-routing" ;;
    shill) echo "social-sentiment browser-ops discovery-tools" ;;
    *) echo "" ;;
  esac
}

title_for() {
  case "$1" in
    chief) echo "Desk Orchestrator" ;;
    scout) echo "Alpha Hunter" ;;
    risk) echo "Absolute Safety Gate" ;;
    whale) echo "Smart-Money Analyst" ;;
    sniper) echo "Single-Write Execution (buys)" ;;
    rug) echo "Post-Entry Safety Monitor" ;;
    exit) echo "Position Manager (sells only)" ;;
    shill) echo "Sentiment and Velocity" ;;
    *) echo "$1" ;;
  esac
}

usage() {
  cat <<EOF
Usage: $0 [--desk PATH] [--hermes-base PATH] [--copy-provider-env] [--dry-run]

Creates ~/.hermes/profiles/<role> with:
  - SOUL.md from agents/<role>.md
  - MEMORY.md seed that contains no default-profile memory
  - only that role's skills (copied, not the default memory store)
  - isolated config.yaml (terminal.home_mode: profile)
  - .env containing PUMPGROK_ROOT / PUMPGROK_DESK only
  - .no-bundled-skills marker so hermes update does not re-seed bundled skills
  - shared file-bus at --desk (default ~/trading-desk)

Does NOT clone the default profile. Does NOT copy TELEGRAM_BOT_TOKEN
except a commented placeholder on chief.

--copy-provider-env copies allowlisted model API keys from
\$HERMES_BASE/.env into each profile .env. Telegram and wallet keys
are never copied.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --desk) DESK="$2"; shift 2 ;;
    --hermes-base) HERMES_BASE="$2"; PROFILES_DIR="${HERMES_BASE}/profiles"; shift 2 ;;
    --copy-provider-env) COPY_PROVIDER_ENV=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ ${DRY_RUN} -eq 1 ]]; then
  echo "DRY-RUN PUMPGROK_ROOT=${ROOT}"
  echo "DRY-RUN PUMPGROK_DESK=${DESK}"
  echo "DRY-RUN HERMES_BASE=${HERMES_BASE}"
  echo "DRY-RUN roles: ${ROLES[*]}"
  echo "DRY-RUN clone_all=false copy_provider_env=${COPY_PROVIDER_ENV}"
fi

mkdir -p "${DESK}"/{proposals,briefs,leads,research,journal,incidents,positions,watch}
if [[ ! -f "${DESK}/desk.md" ]]; then
  cat > "${DESK}/desk.md" <<EOF
# PumpGrok Desk Record
Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Engagement: research
Halt: false
Throwaway wallet: not yet connected
Daily loss limit: 5 %
Notes: Hermes isolated profiles + cron state machine. Research only.
EOF
fi
if [[ ! -f "${DESK}/risk-limits.md" ]]; then
  cat > "${DESK}/risk-limits.md" <<EOF
# Risk limits
Status: interview pending
Default paper size: TBD
EOF
fi

if ! command -v hermes >/dev/null 2>&1; then
  echo "WARN: hermes CLI not on PATH. Will write profile trees only." >&2
fi

provider_env_lines() {
  local src="${HERMES_BASE}/.env"
  if [[ ${COPY_PROVIDER_ENV} -ne 1 || ! -f "${src}" ]]; then
    return 0
  fi
  grep -E "${PROVIDER_ALLOWLIST_RE}" "${src}" | grep -Ev "${FORBIDDEN_ENV_RE}" || true
}

write_env() {
  local role="$1"
  local dest="$2"
  local tmp
  tmp="$(mktemp)"
  cat > "${tmp}" <<EOF
# Profile-local env. Do not put seeds or private keys here.
PUMPGROK_ROOT=${ROOT}
PUMPGROK_DESK=${DESK}
PUMPGROK_ROLE=${role}
EOF
  provider_env_lines >> "${tmp}"
  if [[ "${role}" == "chief" ]]; then
    cat >> "${tmp}" <<EOF
# Uncomment and set a NEW BotFather token. Do not reuse the personal-assistant token.
# TELEGRAM_BOT_TOKEN=
# TELEGRAM_ALLOWED_USERS=
EOF
  fi
  if [[ -f "${dest}" ]] && grep -q '^TELEGRAM_BOT_TOKEN=' "${dest}"; then
    grep '^TELEGRAM_BOT_TOKEN=' "${dest}" >> "${tmp}" || true
    grep '^TELEGRAM_ALLOWED_USERS=' "${dest}" >> "${tmp}" || true
  fi
  if grep -Eq "${FORBIDDEN_ENV_RE}" "${tmp}"; then
    if [[ "${role}" != "chief" ]] || grep -Eq '(PRIVATE_KEY|SECRET_KEY|SEED|MNEMONIC|PHANTOM|WALLET_SECRET)=' "${tmp}"; then
      echo "REFUSED: forbidden secret would land in ${dest}" >&2
      rm -f "${tmp}"
      return 1
    fi
  fi
  mv "${tmp}" "${dest}"
}

create_profile_tree() {
  local role="$1"
  local home="${PROFILES_DIR}/${role}"
  mkdir -p "${home}"/{memories,sessions,skills,logs,plans,workspace,cron,home,scripts}
  local soul_src="${ROOT}/agents/${role}.md"
  if [[ ! -f "${soul_src}" ]]; then
    echo "missing ${soul_src}" >&2
    return 1
  fi
  cp "${soul_src}" "${home}/SOUL.md"

  cat > "${home}/MEMORY.md" <<EOF
# ${role} memory
This is the PumpGrok ${role} profile. Isolated HERMES_HOME.
Files beat memory. Shared writable state is only ${DESK}.
Do not import memory from the default ~/.hermes profile.
Do not store keys. Engagement lives in ${DESK}/desk.md.
EOF

  cat > "${home}/profile.yaml" <<EOF
name: ${role}
title: $(title_for "${role}")
role: ${role}
source: PumpGrok agents/${role}.md
isolation: hermes-home
EOF

  rm -rf "${home}/skills"
  mkdir -p "${home}/skills"
  local skill
  for skill in $(skills_for "${role}"); do
    if [[ -d "${ROOT}/skills/${skill}" ]]; then
      mkdir -p "${home}/skills/${skill}"
      cp -R "${ROOT}/skills/${skill}/." "${home}/skills/${skill}/"
    fi
  done
  touch "${home}/.no-bundled-skills"
  touch "${home}/skills/.no-bundled-skills"

  cat > "${home}/config.yaml" <<EOF
# Generated by scripts/hermes-bootstrap.sh — PumpGrok isolation
terminal:
  cwd: "${DESK}"
  home_mode: profile
memory:
  enabled: true
EOF

  write_env "${role}" "${home}/.env"
  echo "${home}"
}

echo "PUMPGROK_ROOT=${ROOT}"
echo "PUMPGROK_DESK=${DESK}"
echo "HERMES_BASE=${HERMES_BASE}"

if [[ ${DRY_RUN} -eq 1 ]]; then
  for role in "${ROLES[@]}"; do
    echo "DRY-RUN would isolate ${role} skills=$(skills_for "${role}")"
  done
else
  mkdir -p "${PROFILES_DIR}"
  for role in "${ROLES[@]}"; do
    home="${PROFILES_DIR}/${role}"
    if command -v hermes >/dev/null 2>&1; then
      if [[ ! -d "${home}" ]]; then
        hermes profile create "${role}" --no-skills 2>/dev/null \
          || hermes profile create "${role}" 2>/dev/null \
          || mkdir -p "${home}"
      fi
      hermes -p "${role}" skills opt-out 2>/dev/null || true
    fi
    create_profile_tree "${role}"
    echo "isolated ${role} -> ${PROFILES_DIR}/${role}"
  done
fi

if command -v python3 >/dev/null 2>&1; then
  PUMPGROK_ROOT="${ROOT}" PUMPGROK_DESK="${DESK}" python3 "${ROOT}/tools/desk_state.py" ensure
fi

echo
echo "Isolation check (paths must differ from ${HERMES_BASE} itself):"
echo "  ${PROFILES_DIR}/risk/config.yaml"
echo "  ${PROFILES_DIR}/chief/.env"
echo "  ${PROFILES_DIR}/scout/MEMORY.md"

cat <<EOF

NEXT
1. Put a NEW Telegram token only in ${PROFILES_DIR}/chief/.env
2. Optionally copy model keys: re-run with --copy-provider-env
3. ./scripts/hermes-install-cron.sh --desk "${DESK}"
4. Enable multiplex on the existing default gateway so role cron fires
   (see hermes/README.md). Do not start sniper/exit gateways.
5. ./scripts/hermes-verify-isolation.sh --desk "${DESK}"

VERIFY
  hermes profile list
  test -f ${DESK}/desk.md
  ! grep -E '${FORBIDDEN_ENV_RE}' ${PROFILES_DIR}/scout/.env ${PROFILES_DIR}/risk/.env ${PROFILES_DIR}/sniper/.env
EOF
