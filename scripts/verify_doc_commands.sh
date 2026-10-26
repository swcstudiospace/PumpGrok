#!/usr/bin/env bash
#
# scripts/verify_doc_commands.sh — DOC-02 acceptance (Phase 7 criterion 5).
#
# Extracts fenced ```bash blocks AND inline `command` spans from the Commands
# sections of CLAUDE.md ("## Commands") and AGENTS.md ("## Run the checks")
# only, then dispositions each documented command:
#
#   RUN   offline-safe, finite commands (pumpgrok --help, doctor, one-shot
#         replay). The exit code must equal the documented expectation:
#         a trailing comment "# exits N", else 0. Any other nonzero fails.
#   SKIP  make targets (LISTED but never executed — the suite is the
#         orchestrator's job; target names are verified to exist in the
#         Makefile instead), installs (uv sync needs network), the whole-repo
#         check.sh (Phase 7 hard constraint 1), docker (needs a daemon).
#   SKIP  run --serve and any other long-lived process: NEVER executed.
#         Instead the required flags are verified in the output of
#         `uv run pumpgrok run --help`.
#
# Fail-closed: curl/wget/ssh or any command outside the offline allowlist
# fails the script. No network is used by this script beyond loopback probes
# the doctor itself reports as warnings (never fatal, exit stays 0).
#
# Usage: ./scripts/verify_doc_commands.sh   (exits 0 when all pass/skip)

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_MD="$ROOT/CLAUDE.md"
AGENTS_MD="$ROOT/AGENTS.md"
MAKEFILE="$ROOT/Makefile"

# Shell metacharacters never reach bash -c: no operators, substitution,
# redirection, quoting, globbing, or grouping. Documented forms are exact.
PLAIN_ARGS_RE='^[A-Za-z0-9_./:=,+@ -]+$'
HELP_FORM_RE='^(uv run )?pumpgrok( [A-Za-z0-9_.-]+)* --help$'
REPLAY_FORM_RE='^uv run pumpgrok run --mode paper --once --replay [A-Za-z0-9_./-]+$'

pass=0
skip=0
fail=0
FAILED=""
SEEN=""

pass_line() { printf 'PASS  %s (exit %s)\n' "$1" "$2"; pass=$((pass + 1)); }
skip_line() { printf 'SKIP  %s\n      note: %s\n' "$1" "$2"; skip=$((skip + 1)); }
fail_line() { printf 'FAIL  %s\n      reason: %s\n' "$1" "$2"; FAILED="${FAILED}$1
"; fail=$((fail + 1)); }

# Print the lines of the Commands sections only (## Commands in CLAUDE.md,
# ## Run the checks in AGENTS.md); stop at the next ## heading.
section_lines() { # $1 = file
    awk '/^## (Commands|Run the checks)$/ {flag=1; next} /^## / {flag=0} flag' "$1"
}

# Emit candidate commands: raw fenced-bash lines plus SPAN:<inline code>.
# Inline spans are filtered to command-looking text; backticked file paths,
# flags, and prose fragments are dropped here.
collect_candidates() { # $1 = file
    local in_fence=0 line rest span
    while IFS= read -r line; do
        if [[ "$line" == '```'* ]]; then
            if [[ "$line" == '```bash'* ]]; then in_fence=1; else in_fence=0; fi
            continue
        fi
        if ((in_fence)); then
            printf 'FENCE:%s\n' "$line"
            continue
        fi
        rest="$line"
        while [[ "$rest" == *'`'* ]]; do
            rest="${rest#*\`}"
            [[ "$rest" == *'`'* ]] || break
            span="${rest%%\`*}"
            rest="${rest#*\`}"
            if [[ "$span" =~ ^(make([[:space:]]|$)|uv[[:space:]]+run[[:space:]]+[^[:space:]]|./|docker[[:space:]]|pumpgrok[[:space:]]|python3?[[:space:]]) ]]; then
                printf 'SPAN:%s\n' "$span"
            fi
        done
    done < <(section_lines "$1")
}

trim() { # $1 = text -> stripped
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf '%s' "$s"
}

run_cmd() { # $1 = command, $2 = expected exit
    local cmd="$1" expected="$2" code out
    out="$(mktemp)"
    (cd "$ROOT" && bash -c "$cmd" >"$out" 2>&1)
    code=$?
    if [[ "$code" == "$expected" ]]; then
        pass_line "$cmd" "$code"
    else
        fail_line "$cmd" "exit $code, documented expectation $expected"$'\n'"$(tail -n 20 "$out")"
    fi
    rm -f "$out"
}

disposition() { # $1 = raw candidate line
    local raw expected cmd t missing help_out dirpath
    raw="$(trim "$1")"
    [[ -z "$raw" ]] && return 0
    [[ "$raw" == \#* ]] && return 0

    # Documented expectation: trailing comment "# exits N" (default 0).
    expected=0
    if [[ "$raw" =~ \#[[:space:]]*exits[[:space:]]+([0-9]+)[[:space:]]*$ ]]; then
        expected="${BASH_REMATCH[1]}"
        raw="$(trim "${raw%%#*}")"
    elif [[ "$raw" == *' #'* ]]; then
        raw="$(trim "${raw%% #*}")"
    fi
    cmd="$raw"
    [[ -z "$cmd" ]] && return 0
    if [[ ! "$cmd" =~ $PLAIN_ARGS_RE ]]; then
        fail_line "$cmd" "shell operator or metacharacter; documented commands are plain argument lists and are never passed to a shell"
        return 0
    fi

    # Deduplicate across both files (./scripts/check.sh is in both).
    if [[ "$SEEN" == *"
$cmd
"* ]]; then
        return 0
    fi
    SEEN="${SEEN}
$cmd
"

    case "$cmd" in
        make\ *)
            missing=""
            for t in ${cmd#make }; do
                grep -qE "^${t}:" "$MAKEFILE" || missing="${missing}${t} "
            done
            if [[ -n "$missing" ]]; then
                fail_line "$cmd" "make target(s) missing from Makefile: $missing"
            else
                skip_line "$cmd" "make target(s) listed, not executed (suite is the orchestrator's job; names verified in Makefile)"
            fi
            ;;
        uv\ sync*)
            skip_line "$cmd" "dependency install needs network; not executed"
            ;;
        docker\ *)
            skip_line "$cmd" "needs a container daemon; not executed"
            ;;
        ./scripts/check.sh)
            if [[ -x "$ROOT/scripts/check.sh" ]]; then
                skip_line "$cmd" "whole-repo instruction lint is the orchestrator's job (Phase 7 constraint 1); script present and executable"
            else
                fail_line "$cmd" "documented script missing or not executable"
            fi
            ;;
        *--serve*)
            # NEVER execute a long-lived process. Verify the documented
            # flags exist in `run --help` output instead.
            help_out="$(cd "$ROOT" && uv run pumpgrok run --help 2>&1)" || {
                fail_line "$cmd" "cannot verify serve flags: 'uv run pumpgrok run --help' failed"
                return 0
            }
            if printf '%s' "$help_out" | grep -q -- '--serve' && printf '%s' "$help_out" | grep -q -- '--replay'; then
                skip_line "$cmd" "long-lived serve loop; never executed (flags --serve/--replay verified in 'uv run pumpgrok run --help')"
            else
                fail_line "$cmd" "docs promise --serve/--replay but 'uv run pumpgrok run --help' lacks the flag(s)"
            fi
            ;;
        uv\ run\ pumpgrok\ doctor)
            run_cmd "$cmd" "$expected"
            ;;
        uv\ run\ pumpgrok\ run\ --mode\ paper\ --once\ --replay\ *)
            dirpath="${cmd##*--replay }"
            dirpath="${dirpath%% *}"
            if [[ ! "$cmd" =~ $REPLAY_FORM_RE ]]; then
                fail_line "$cmd" "not the documented one-shot replay form"
            elif [[ -d "$ROOT/$dirpath" ]]; then
                run_cmd "$cmd" "$expected"
            else
                fail_line "$cmd" "fixture directory missing: $dirpath"
            fi
            ;;
        *--help*)
            if [[ "$cmd" =~ $HELP_FORM_RE ]]; then
                run_cmd "$cmd" "$expected"
            else
                fail_line "$cmd" "--help line is not a documented offline argument list"
            fi
            ;;
        *curl*|*wget*|*ssh*)
            fail_line "$cmd" "network access is forbidden in doc verification"
            ;;
        *)
            fail_line "$cmd" "not in the offline allowlist (pumpgrok verbs, --help, make (listed), check.sh (listed))"
            ;;
    esac
}

main() {
    local item f
    for f in "$CLAUDE_MD" "$AGENTS_MD"; do
        [[ -f "$f" ]] || {
            fail_line "$f" "documented source file missing"
            continue
        }
        while IFS= read -r item; do
            item="${item#FENCE:}"
            item="${item#SPAN:}"
            disposition "$item"
        done < <(collect_candidates "$f")
    done

    printf -- '---\npass=%d skip=%d fail=%d\n' "$pass" "$skip" "$fail"
    if ((fail > 0)); then
        printf 'failures:\n%s' "$FAILED"
        return 1
    fi
    return 0
}

main "$@"
