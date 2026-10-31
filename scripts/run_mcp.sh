#!/usr/bin/env sh
# Launch the read-only MCP server over stdio for OpenCode or any MCP client.
#
# Loads backend/.env (control-plane token and API URL) and starts the server
# against a running control plane. Set CONTROL_PLANE_URL to point elsewhere.
set -eu
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

: "${CONTROL_PLANE_TOKEN:?CONTROL_PLANE_TOKEN is required (set it in .env or the environment)}"
: "${CONTROL_PLANE_URL:=http://127.0.0.1:8000}"
export CONTROL_PLANE_TOKEN CONTROL_PLANE_URL

cd backend
exec ../.venv/bin/python -m app.mcp_server
