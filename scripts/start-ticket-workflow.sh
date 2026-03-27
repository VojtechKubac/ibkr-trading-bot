#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <ticket-id> <short-description>"
  echo "Example: $0 kua-69 workflow-enforcement"
  exit 1
fi

TICKET_ID_RAW="$1"
SLUG_RAW="$2"

normalize_slug() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-{2,}/-/g'
}

TICKET_ID="$(normalize_slug "${TICKET_ID_RAW}")"
SLUG="$(normalize_slug "${SLUG_RAW}")"
BRANCH_NAME="${TICKET_ID}-${SLUG}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMMON_GIT_DIR="$(git -C "${REPO_ROOT}" rev-parse --git-common-dir)"
COMMON_GIT_DIR_ABS="$(cd "${COMMON_GIT_DIR}" && pwd)"
MAIN_CHECKOUT_DIR="$(dirname "${COMMON_GIT_DIR_ABS}")"
PARENT_DIR="$(dirname "${MAIN_CHECKOUT_DIR}")"
WORKTREE_DIR="${PARENT_DIR}/worktrees/${BRANCH_NAME}"

if [[ ! -d "${WORKTREE_DIR}" ]]; then
  "${SCRIPT_DIR}/new-ticket-env.sh" "${TICKET_ID}" "${SLUG}"
fi

cd "${WORKTREE_DIR}"
set -a
source .ticket-env
set +a

docker compose -f docker-compose.ticket.yml up -d --build

echo
echo "Ticket workflow ready:"
echo "  worktree: ${WORKTREE_DIR}"
echo "  branch:   ${BRANCH_NAME}"
echo
echo "Next step (inside container):"
echo "  docker compose -f docker-compose.ticket.yml exec ticket-dev bash"
echo
echo "Then run one of:"
echo "  claude --dangerously-skip-permissions"
echo "  cursor-agent -p --force --sandbox disabled \"implement the ticket\""
