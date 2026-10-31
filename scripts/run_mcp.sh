#!/usr/bin/env sh
# Launch the MCP server over stdio for OpenCode or any MCP client.
#
# Loads .env (API URL and control-plane token) and starts the server against a
# running control plane. Set MCP_CONTROL_PLANE_TOKEN to give the agent a scoped
# token instead of the master token; set CONTROL_PLANE_URL to point elsewhere.
set -eu
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# A scoped token bounds what the agent can do, even if it is talked into trying.
if [ -n "${MCP_CONTROL_PLANE_TOKEN:-}" ]; then
  CONTROL_PLANE_TOKEN="$MCP_CONTROL_PLANE_TOKEN"
fi

: "${CONTROL_PLANE_TOKEN:?CONTROL_PLANE_TOKEN is required (set it in .env or the environment)}"
: "${CONTROL_PLANE_URL:=http://127.0.0.1:8000}"
export CONTROL_PLANE_TOKEN CONTROL_PLANE_URL

cd backend
exec ../.venv/bin/python -m app.mcp_server
