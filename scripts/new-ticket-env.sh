#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <ticket-id> <short-description>"
  echo "Example: $0 kua-68 containerized-workflow"
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

if [[ -z "${TICKET_ID}" || -z "${SLUG}" ]]; then
  echo "Error: ticket-id and short-description must contain at least one alphanumeric character."
  exit 1
fi

BRANCH_NAME="${TICKET_ID}-${SLUG}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PARENT_DIR="$(dirname "${REPO_ROOT}")"
WORKTREES_DIR="${PARENT_DIR}/worktrees"
TARGET_DIR="${WORKTREES_DIR}/${BRANCH_NAME}"

mkdir -p "${WORKTREES_DIR}"

if [[ -d "${TARGET_DIR}" ]]; then
  echo "Worktree already exists: ${TARGET_DIR}"
  exit 1
fi

cd "${REPO_ROOT}"
git fetch origin main
git worktree add -b "${BRANCH_NAME}" "${TARGET_DIR}" origin/main

{
  printf 'TICKET_ID=%q\n' "${TICKET_ID}"
  printf 'BRANCH_NAME=%q\n' "${BRANCH_NAME}"
  printf 'TICKET_CONTAINER_NAME=%q\n' "trading-${BRANCH_NAME}"
  printf 'HOST_UID=%q\n' "$(id -u)"
  printf 'HOST_GID=%q\n' "$(id -g)"
} > "${TARGET_DIR}/.ticket-env"

echo
echo "Created worktree: ${TARGET_DIR}"
echo "Branch: ${BRANCH_NAME}"
echo
echo "Next steps:"
echo "  cd \"${TARGET_DIR}\""
echo "  set -a; source .ticket-env; set +a"
echo "  docker compose -f docker-compose.ticket.yml up -d --build"
echo "  docker compose -f docker-compose.ticket.yml exec ticket-dev bash"
