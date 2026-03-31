#!/usr/bin/env bash
# run-tickets.sh — launch multiple ticket agents in parallel with concurrency cap.
#
# Usage: ./scripts/run-tickets.sh [--dry-run] <ticket-id> [<ticket-id> ...]
#   e.g. ./scripts/run-tickets.sh kua-101 kua-102 kua-103
#
# Env vars:
#   MAX_PARALLEL   — max concurrent agents (default: 5)
#   ANTHROPIC_API_KEY, GH_TOKEN, LINEAR_API_KEY — passed through to run-ticket.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAX_PARALLEL="${MAX_PARALLEL:-5}"
DRY_RUN=false

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

TICKETS=()
for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY_RUN=true ;;
    --*)
      echo "Unknown option: ${arg}" >&2
      echo "Usage: $0 [--dry-run] <ticket-id> [<ticket-id> ...]" >&2
      exit 1
      ;;
    *) TICKETS+=("${arg}") ;;
  esac
done

if [[ ${#TICKETS[@]} -eq 0 ]]; then
  echo "Usage: $0 [--dry-run] <ticket-id> [<ticket-id> ...]" >&2
  echo "Example: $0 kua-101 kua-102 kua-103" >&2
  exit 1
fi

if [[ "${DRY_RUN}" == true ]]; then
  echo "Dry run — would launch ${#TICKETS[@]} ticket(s) with MAX_PARALLEL=${MAX_PARALLEL}:"
  for t in "${TICKETS[@]}"; do
    echo "  ${SCRIPT_DIR}/run-ticket.sh ${t}"
  done
  exit 0
fi

# ---------------------------------------------------------------------------
# Parallel job runner with concurrency cap
# ---------------------------------------------------------------------------

declare -A JOB_PIDS   # ticket-id -> pid
declare -A JOB_STATUS # ticket-id -> exit code

running_jobs() {
  local count=0
  for pid in "${JOB_PIDS[@]}"; do
    if kill -0 "${pid}" 2>/dev/null; then
      (( count++ )) || true
    fi
  done
  echo "${count}"
}

reap_finished() {
  for ticket in "${!JOB_PIDS[@]}"; do
    local pid="${JOB_PIDS[${ticket}]}"
    if ! kill -0 "${pid}" 2>/dev/null; then
      wait "${pid}" && JOB_STATUS["${ticket}"]=0 || JOB_STATUS["${ticket}"]=$?
      unset "JOB_PIDS[${ticket}]"
    fi
  done
}

for ticket in "${TICKETS[@]}"; do
  # Wait while at the concurrency cap
  while [[ "$(running_jobs)" -ge "${MAX_PARALLEL}" ]]; do
    reap_finished
    sleep 2
  done

  echo "Starting: ${ticket}"
  "${SCRIPT_DIR}/run-ticket.sh" "${ticket}" &
  JOB_PIDS["${ticket}"]=$!
done

# Wait for all remaining jobs
while [[ "$(running_jobs)" -gt 0 ]]; do
  reap_finished
  sleep 2
done
reap_finished

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "========================================"
echo " Summary"
echo "========================================"

FAILURES=0
for ticket in "${TICKETS[@]}"; do
  code="${JOB_STATUS[${ticket}]:-1}"
  ticket_upper="$(printf '%s' "${ticket}" | tr '[:lower:]' '[:upper:]')"
  if [[ "${code}" -eq 0 ]]; then
    echo "  ✓ ${ticket_upper}"
  else
    echo "  ✗ ${ticket_upper}  (exit ${code})"
    (( FAILURES++ )) || true
  fi
done

echo ""
[[ "${FAILURES}" -eq 0 ]] && echo "All ${#TICKETS[@]} ticket(s) completed successfully." \
                          || echo "${FAILURES} of ${#TICKETS[@]} ticket(s) failed."

exit "${FAILURES}"
