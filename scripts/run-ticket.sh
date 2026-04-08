#!/usr/bin/env bash
# run-ticket.sh — end-to-end orchestrator: fetch ticket, start container, run agent.
#
# Usage: ./scripts/run-ticket.sh <ticket-id>
#   e.g. ./scripts/run-ticket.sh kua-123
#
# Required env vars (set in host shell before calling this script):
#   GH_TOKEN           — GitHub PAT with repo scope (for git push + gh pr create)
#   LINEAR_API_KEY     — Linear personal API key (for fetching ticket details)
#   AGENT_CLI          — optional override: claude|cursor
#   ANTHROPIC_API_KEY  — required when AGENT_CLI=claude (or auto-detected Claude)
#   CURSOR_API_KEY     — required when AGENT_CLI=cursor (or auto-detected Cursor)

set -euo pipefail

# ---------------------------------------------------------------------------
# Args and env validation
# ---------------------------------------------------------------------------

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <ticket-id>" >&2
  echo "Example: $0 kua-123" >&2
  exit 1
fi

detect_agent_cli() {
  local override="${AGENT_CLI:-}"
  if [[ -n "${override}" ]]; then
    override="$(printf '%s' "${override}" | tr '[:upper:]' '[:lower:]')"
    if [[ "${override}" != "claude" && "${override}" != "cursor" ]]; then
      echo "Error: AGENT_CLI must be either 'claude' or 'cursor'." >&2
      exit 1
    fi
    printf '%s' "${override}"
    return
  fi

  if [[ "${CURSOR_AGENT:-}" == "1" || "${CURSOR_INVOKED_AS:-}" == "agent" ]]; then
    printf '%s' "cursor"
    return
  fi

  printf '%s' "claude"
}

AGENT_CLI="$(detect_agent_cli)"

for var in GH_TOKEN LINEAR_API_KEY; do
  if [[ -z "${!var:-}" ]]; then
    echo "Error: ${var} is not set in the host shell." >&2
    exit 1
  fi
done

if [[ "${AGENT_CLI}" == "cursor" ]]; then
  AGENT_LABEL="Cursor"
  AGENT_FOOTER_LINE="🤖 Generated with [Cursor](https://cursor.com)"
  REQUIRED_AGENT_API_KEY="CURSOR_API_KEY"
else
  AGENT_LABEL="Claude"
  AGENT_FOOTER_LINE="🤖 Generated with [Claude Code](https://claude.com/claude-code)"
  REQUIRED_AGENT_API_KEY="ANTHROPIC_API_KEY"
fi

if [[ -z "${!REQUIRED_AGENT_API_KEY:-}" ]]; then
  echo "Error: ${REQUIRED_AGENT_API_KEY} is required when AGENT_CLI=${AGENT_CLI}." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

normalize_slug() {
  printf '%s' "$1" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

TICKET_ID="$(normalize_slug "$1")"
TICKET_ID_UPPER="$(printf '%s' "${TICKET_ID}" | tr '[:lower:]' '[:upper:]')"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMMON_GIT_DIR="$(git -C "${REPO_ROOT}" rev-parse --git-common-dir)"
COMMON_GIT_DIR_ABS="$(cd "${COMMON_GIT_DIR}" && pwd)"
MAIN_CHECKOUT_DIR="$(dirname "${COMMON_GIT_DIR_ABS}")"
PARENT_DIR="$(dirname "${MAIN_CHECKOUT_DIR}")"
WORKTREES_DIR="${PARENT_DIR}/worktrees"

# ---------------------------------------------------------------------------
# Step 1: Fetch ticket from Linear
# ---------------------------------------------------------------------------

TEAM_KEY="$(printf '%s' "${TICKET_ID}" | sed 's/-[0-9]*$//' | tr '[:lower:]' '[:upper:]')"
TICKET_NUM="$(printf '%s' "${TICKET_ID}" | grep -oE '[0-9]+$')"

echo "Fetching ${TICKET_ID_UPPER} from Linear..."

LINEAR_RESPONSE=$(curl -s --connect-timeout 10 --max-time 30 -X POST https://api.linear.app/graphql \
  -H "Authorization: ${LINEAR_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"{ issues(filter: { team: { key: { eq: \\\"${TEAM_KEY}\\\" } }, number: { eq: ${TICKET_NUM} } }, first: 1) { nodes { identifier title description url } } }\"}" \
  || { echo "Error: Linear API request failed" >&2; exit 1; })

eval "$(printf '%s' "${LINEAR_RESPONSE}" | python3 - <<'PYEOF'
import sys, json, shlex
try:
    d = json.loads(sys.stdin.read())
    nodes = d.get("data", {}).get("issues", {}).get("nodes", [])
    n = nodes[0] if nodes else {}
    print(f"TICKET_TITLE={shlex.quote(n.get('title') or '')}")
    print(f"TICKET_DESC={shlex.quote(n.get('description') or '')}")
    print(f"TICKET_URL={shlex.quote(n.get('url') or '')}")
except Exception as e:
    print(f"echo 'JSON parse error: {e}' >&2; exit 1")
PYEOF
)"

if [[ -z "${TICKET_TITLE}" ]]; then
  echo "Error: could not fetch ${TICKET_ID_UPPER} from Linear. Check LINEAR_API_KEY and ticket ID." >&2
  exit 1
fi

echo "  Title: ${TICKET_TITLE}"
echo "  URL:   ${TICKET_URL}"

# ---------------------------------------------------------------------------
# Step 2: Resolve or create worktree
# ---------------------------------------------------------------------------

# Reuse an existing worktree for this ticket ID if one exists (any slug).
EXISTING_WORKTREE=$(find "${WORKTREES_DIR}" -maxdepth 1 -type d -name "${TICKET_ID}-*" 2>/dev/null | sort | head -1 || true)

if [[ -n "${EXISTING_WORKTREE}" ]]; then
  WORKTREE_DIR="${EXISTING_WORKTREE}"
  BRANCH_NAME="$(basename "${WORKTREE_DIR}")"
  echo "Reusing existing worktree: ${WORKTREE_DIR}"
else
  SLUG="$(normalize_slug "${TICKET_TITLE}" | cut -c1-40 | sed 's/-$//')"
  BRANCH_NAME="${TICKET_ID}-${SLUG}"
  WORKTREE_DIR="${WORKTREES_DIR}/${BRANCH_NAME}"
  echo "Creating worktree: ${WORKTREE_DIR}"
  "${SCRIPT_DIR}/start-ticket-workflow.sh" "${TICKET_ID}" "${SLUG}"
fi

# ---------------------------------------------------------------------------
# Step 3: Ensure container is running
# ---------------------------------------------------------------------------

cd "${WORKTREE_DIR}"
set -a; source .ticket-env; set +a

docker compose -f docker-compose.ticket.yml up -d 2>&1

# ---------------------------------------------------------------------------
# Step 4: Write agent prompt to a file in the worktree (avoids shell quoting)
# ---------------------------------------------------------------------------

PROMPT_FILE="${WORKTREE_DIR}/.agent-prompt.txt"
LOG_FILE="${WORKTREE_DIR}/.agent.log"

cat > "${PROMPT_FILE}" <<PROMPT
You are a coding agent implementing Linear ticket ${TICKET_ID_UPPER}.

## Ticket

**Title:** ${TICKET_TITLE}
**URL:** ${TICKET_URL}

**Description:**

${TICKET_DESC}

## Instructions

1. Read AGENTS.md for all project conventions and rules before making any changes.
2. Implement the ticket as described above.
3. Before committing, run all quality checks and fix any failures:
   \`\`\`
   pytest tests/
   ruff check .
   mypy trading_bot/ main.py
   \`\`\`
4. Commit with a message in the format: "${TICKET_ID_UPPER}: <short description>"
5. Push the branch:
   \`\`\`
   git push -u origin ${BRANCH_NAME}
   \`\`\`
6. Create a PR:
   \`\`\`
   gh pr create --title "${TICKET_ID_UPPER}: ${TICKET_TITLE}" --body "..."
   \`\`\`
   PR body must contain: Summary (bullet points), Test plan (checklist), and the footer line:
   ${AGENT_FOOTER_LINE}
7. After creating the PR, wait for CodeRabbit review. Address all comments (including
   nitpicks) before considering the ticket done. CodeRabbit is done when all discussions
   are resolved and no CodeRabbit CI run is in progress.

Work autonomously to completion. Do not pause for confirmation.
PROMPT

# ---------------------------------------------------------------------------
# Step 5: Run the agent
# ---------------------------------------------------------------------------

echo ""
echo "Launching ${AGENT_LABEL} agent for ${TICKET_ID_UPPER} (log: ${LOG_FILE})..."
echo ""

if [[ "${AGENT_CLI}" == "cursor" ]]; then
  docker compose -f docker-compose.ticket.yml exec -T ticket-dev \
    bash -c 'cursor-agent -p --force --sandbox disabled "$(cat /workspace/.agent-prompt.txt)"' \
    2>&1 | tee "${LOG_FILE}"
else
  docker compose -f docker-compose.ticket.yml exec -T ticket-dev \
    bash -c 'claude --dangerously-skip-permissions -p "$(cat /workspace/.agent-prompt.txt)"' \
    2>&1 | tee "${LOG_FILE}"
fi

AGENT_EXIT=${PIPESTATUS[0]}

# Clean up prompt file
rm -f "${PROMPT_FILE}"

echo ""
if [[ ${AGENT_EXIT} -eq 0 ]]; then
  echo "✓ ${TICKET_ID_UPPER} completed — see ${LOG_FILE}"
else
  echo "✗ ${TICKET_ID_UPPER} failed (exit ${AGENT_EXIT}) — see ${LOG_FILE}" >&2
  exit "${AGENT_EXIT}"
fi
