#!/usr/bin/env bash
# Install PumpGrok cron jobs into isolated Hermes profiles.
# Refuses to attach jobs to sniper or exit.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DESK="${PUMPGROK_DESK:-${HOME}/trading-desk}"
DRY_RUN=0
DELIVER_CHIEF="${DELIVER_CHIEF:-telegram}"
REMOVE=0

usage() {
  cat <<EOF
Usage: $0 [--desk PATH] [--dry-run] [--deliver-chief TARGET] [--remove]

Installs scout/risk/chief/rug jobs using prompts in hermes/cron/prompts/.
Jobs are created inside the owning profile so multiplex/profile gateways
tick them with that profile's HERMES_HOME.

Default chief notify target: telegram (the chief profile home channel).
Scout and risk deliver to bot-chat:chief (files remain the source of truth).

--remove lists matching jobs per owner and does not create new ones.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --desk) DESK="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --deliver-chief) DELIVER_CHIEF="$2"; shift 2 ;;
    --remove) REMOVE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if ! command -v hermes >/dev/null 2>&1; then
  echo "hermes CLI not found. --dry-run dump only." >&2
  DRY_RUN=1
fi

export PUMPGROK_ROOT="${ROOT}"
export PUMPGROK_DESK="${DESK}"

prompt_body() {
  local file="$1"
  cat <<EOF
PUMPGROK_ROOT=${ROOT}
PUMPGROK_DESK=${DESK}
Read and follow these instructions exactly. Files beat memory.

$(cat "${ROOT}/hermes/cron/prompts/${file}")
EOF
}

install_job() {
  local owner="$1"
  local schedule="$2"
  local name="$3"
  local deliver="$4"
  local prompt_file="$5"
  shift 5
  local skills=("$@")

  case "${owner}" in
    sniper|exit)
      echo "REFUSED: will not install cron on ${owner}" >&2
      return 1
      ;;
  esac

  local prompt
  prompt="$(prompt_body "${prompt_file}")"
  echo "JOB owner=${owner} name=${name} schedule=${schedule} deliver=${deliver}"
  if [[ ${DRY_RUN} -eq 1 ]]; then
    echo "--- prompt ${prompt_file} ---"
    echo "${prompt}" | sed -n '1,14p'
    echo "..."
    return 0
  fi

  local skill_flags=()
  local s
  for s in "${skills[@]}"; do
    skill_flags+=(--skill "${s}")
  done

  # hermes -p OWNER switches HERMES_HOME for create. Combined with
  # --profile OWNER so a multiplexed default gateway still pins the run.
  hermes -p "${owner}" cron create "${schedule}" "${prompt}" \
    --name "${name}" \
    --deliver "${deliver}" \
    --profile "${owner}" \
    --workdir "${DESK}" \
    "${skill_flags[@]}"
}

if [[ ${REMOVE} -eq 1 ]]; then
  echo "Listing jobs on cron owners (remove individually with hermes -p ROLE cron remove ID):"
  for owner in scout risk chief rug; do
    echo "== ${owner} =="
    if command -v hermes >/dev/null 2>&1 && [[ ${DRY_RUN} -eq 0 ]]; then
      hermes -p "${owner}" cron list || true
    fi
  done
  exit 0
fi

install_job scout "every 60m" "[bot:scout] discover" "bot-chat:chief" \
  "scout-discover.md" discovery-tools solana-market-data grokbot-pipeline hermes-cron-desk

install_job scout "every 60m" "[bot:scout] pipeline" "bot-chat:chief" \
  "scout-pipeline.md" grokbot-pipeline discovery-tools hermes-cron-desk

install_job risk "every 15m" "[bot:risk] audit-open-leads" "bot-chat:chief" \
  "risk-audit.md" risk-audit desk-risk-limits hermes-cron-desk

install_job chief "every 15m" "[bot:chief] pickup" "${DELIVER_CHIEF}" \
  "chief-pickup.md" desk-operating-model desk-trade-lifecycle hermes-cron-desk

install_job rug "every 30m" "[bot:rug] watch-paper" "${DELIVER_CHIEF}" \
  "rug-watch.md" desk-monitoring position-monitoring hermes-cron-desk

install_job chief "0 12 * * *" "[bot:chief] journal-rollup" "${DELIVER_CHIEF}" \
  "chief-journal.md" desk-folders-and-journal hermes-cron-desk

if [[ ${DRY_RUN} -eq 0 ]]; then
  echo
  echo "Installed jobs:"
  for owner in scout risk chief rug; do
    echo "== ${owner} =="
    hermes -p "${owner}" cron list || true
  done
  echo
  echo "Gateway: cron only fires while a gateway process is running."
  echo "Enable multiplex for chief,scout,risk,rug on the existing default"
  echo "gateway (see hermes/README.md). Do not start sniper/exit gateways."
fi
