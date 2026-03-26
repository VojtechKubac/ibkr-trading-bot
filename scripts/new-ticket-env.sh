#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <ticket-id> <short-description>"
  echo "Example: $0 kua-68 containerized-workflow"
  exit 1
fi

TICKET_ID_RAW="$1"
SLUG_RAW="$2"

TICKET_ID="$(echo "${TICKET_ID_RAW}" | tr '[:upper:]' '[:lower:]')"
SLUG="$(echo "${SLUG_RAW}" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')"
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

cat > "${TARGET_DIR}/.ticket-env" <<EOF
TICKET_ID=${TICKET_ID}
BRANCH_NAME=${BRANCH_NAME}
TICKET_CONTAINER_NAME=trading-${BRANCH_NAME}
HOST_UID=$(id -u)
HOST_GID=$(id -g)
EOF

echo
echo "Created worktree: ${TARGET_DIR}"
echo "Branch: ${BRANCH_NAME}"
echo
echo "Next steps:"
echo "  cd \"${TARGET_DIR}\""
echo "  set -a; source .ticket-env; set +a"
echo "  docker compose -f docker-compose.ticket.yml up -d --build"
echo "  docker compose -f docker-compose.ticket.yml exec ticket-dev bash"
