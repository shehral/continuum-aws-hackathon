#!/usr/bin/env bash
# Continuum post-commit hook — Part 6
#
# Installation (run once in your project repo):
#   cp /path/to/continuum/tools/continuum-post-commit.sh .git/hooks/post-commit
#   chmod +x .git/hooks/post-commit
#
# Configuration (set in your shell profile or .env):
#   CONTINUUM_API_URL   — base URL of the Continuum API (default: http://localhost:8000)
#   CONTINUUM_API_TOKEN — Bearer token for the Continuum API
#   CONTINUUM_PROJECT   — Project name to associate with this commit
#
# How it works:
#   After each git commit, this hook POSTs the commit metadata and changed
#   files to POST /api/git/commit.  Continuum then creates a CommitNode in
#   Neo4j and links it to any decisions from the same session window via
#   IMPLEMENTED_BY edges.

set -euo pipefail

CONTINUUM_API_URL="${CONTINUUM_API_URL:-http://localhost:8000}"
CONTINUUM_PROJECT="${CONTINUUM_PROJECT:-}"
CONTINUUM_API_TOKEN="${CONTINUUM_API_TOKEN:-}"

# Silently exit if no API token is configured
if [ -z "$CONTINUUM_API_TOKEN" ]; then
  exit 0
fi

# Gather commit metadata
SHA=$(git rev-parse HEAD)
MESSAGE=$(git log -1 --format="%s" HEAD)
AUTHOR_EMAIL=$(git log -1 --format="%ae" HEAD)
COMMITTED_AT=$(git log -1 --format="%aI" HEAD)

# Get list of changed files
FILES_CHANGED=$(git diff-tree --no-commit-id -r --name-only HEAD | tr '\n' ',' | sed 's/,$//')

# Convert comma-separated files to JSON array
FILES_JSON=$(echo "$FILES_CHANGED" | python3 -c "
import sys, json
raw = sys.stdin.read().strip()
files = [f for f in raw.split(',') if f]
print(json.dumps(files))
" 2>/dev/null || echo "[]")

# Build JSON payload
PAYLOAD=$(python3 -c "
import json, sys
payload = {
    'sha': '${SHA}',
    'message': $(echo "${MESSAGE}" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))"),
    'author_email': '${AUTHOR_EMAIL}',
    'committed_at': '${COMMITTED_AT}',
    'files_changed': ${FILES_JSON},
    'project_name': '${CONTINUUM_PROJECT}' or None,
}
print(json.dumps(payload))
" 2>/dev/null)

if [ -z "$PAYLOAD" ]; then
  echo "[continuum] Warning: failed to build commit payload, skipping."
  exit 0
fi

# POST to Continuum API (fire-and-forget, 5s timeout, fail silently)
RESPONSE=$(curl -s \
  --max-time 5 \
  -X POST \
  "${CONTINUUM_API_URL}/api/git/commit" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${CONTINUUM_API_TOKEN}" \
  -d "${PAYLOAD}" \
  2>/dev/null || echo "")

if [ -n "$RESPONSE" ]; then
  LINKED=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('linked_decisions',0))" 2>/dev/null || echo "?")
  echo "[continuum] Commit ${SHA:0:7} linked to ${LINKED} decision(s)."
fi

exit 0
