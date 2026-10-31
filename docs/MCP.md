# MCP server

`backend/app/mcp_server.py` lets an agent operate the control plane instead of
clicking the dashboard: create a cluster, add a project and service, run a
diagnostic, inspect the result, acknowledge an incident.

It is a façade over the authenticated REST API, so authorization, audit records
and project scoping stay on one path. It never talks to Conductor directly and
never touches the database.

## Transports

| Mode | Command | Use |
| --- | --- | --- |
| stdio | `./scripts/run_mcp.sh` | one local operator, zero network exposure |
| HTTP | `python -m app.mcp_server --http` | hosted, any MCP client on any machine |

Hosted endpoint: **https://mcp-production-89f3.up.railway.app/mcp** (Railway
service `mcp`, built from `Dockerfile.mcp`). It holds an `operate`-scoped token,
so it cannot delete anything.

```sh
# HTTP, locally
cd backend
CONTROL_PLANE_URL=http://127.0.0.1:8000 \
CONTROL_PLANE_TOKEN=<scoped token> \
MCP_CLIENT_TOKEN=<client secret> \
PORT=8765 python -m app.mcp_server --http
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `CONTROL_PLANE_URL` | `http://127.0.0.1:8000` | API base URL |
| `CONTROL_PLANE_TOKEN` | required | Token the **server** uses to call the API. Its scope bounds everything an agent can do. |
| `MCP_CLIENT_TOKEN` | required for `--http` | Bearer secret **clients** present to the MCP endpoint |
| `PORT` / `HOST` | `8765` / `0.0.0.0` | HTTP listen address |
| `MCP_ALLOWED_HOSTS` | localhost | Comma-separated `Host` values accepted by the SDK's DNS-rebinding protection. Must include the public hostname when hosted. |

The two tokens are deliberately separate: `MCP_CLIENT_TOKEN` only proves the
caller may talk to the MCP endpoint, while `CONTROL_PLANE_TOKEN` decides what
that endpoint is allowed to do. A `read` token makes every write tool fail with
a 403 from the API; it cannot be escalated by the agent.

## Scopes

Mint tokens with `POST /api/tokens` (`label`, `scope`); the secret is returned
once. List with `GET /api/tokens`, revoke with `DELETE /api/tokens/{id}`.

| Scope | Allows | Typical use |
| --- | --- | --- |
| `read` | every `GET` | dashboards, research agents |
| `operate` | `POST`/`PATCH`/`PUT`, except publishing and credential paths | an agent that creates projects and runs workflows |
| `admin` | everything, including `DELETE` | the dashboard session and the master token |

The required scope is inferred from the verb and path (`required_scope` in
`backend/app/auth.py`), so a new route cannot quietly become world-writable.
Deletes, `/publish`, `/verify`, `/publication*`, `/api/connectors`,
`/api/settings` and `/api/tokens` are admin-only. Actions taken with a scoped
token are audited as `token:<label>`.

## Tools

Read: `list_clusters`, `list_projects`, `get_project`, `list_services`,
`list_workflow_definitions`, `list_executions`, `get_execution`,
`list_incidents`, `get_incident`, `infrastructure_health`, `list_audit`

Operate: `create_cluster`, `create_project`, `create_service`, `check_service`,
`start_diagnostic`, `retry_execution`, `terminate_execution`,
`acknowledge_incident`

Deliberately absent: deletes (admin-only, not exposed as tools), workflow
definition registration (needs a reviewed Conductor definition), connector
credentials, and anything that reaches `incident_analysis` — the paid model call
is not reachable from MCP. `start_diagnostic` hard-codes `diagnostic_pipeline`.

Two-tier safety: prefer the read tools before mutating, and treat
`terminate_execution` as destructive — it stops real engine work.

## Client configuration

OpenCode — `opencode.json` is committed and uses the stdio launcher:

```sh
opencode mcp list      # orchestra  connected
```

Claude Code — `.mcp.json` is committed and reads two environment variables:

```sh
export ORCHESTRA_MCP_URL=http://127.0.0.1:8765/mcp
export ORCHESTRA_MCP_TOKEN=$(grep '^MCP_CLIENT_TOKEN=' .env.mcp-local | cut -d= -f2-)
claude mcp list        # orchestra  connected
```

Codex — not installed or verified here. The equivalent entry is:

```toml
# ~/.codex/config.toml
[mcp_servers.orchestra]
url = "http://127.0.0.1:8765/mcp"
bearer_token_env_var = "ORCHESTRA_MCP_TOKEN"
```

## Safety properties

- **No paid calls.** `incident_analysis` is unreachable; the tool hard-codes the
  deterministic workflow, and the API itself rejects any definition containing
  `cp_analyze_incident`.
- **Untrusted data is labelled.** Execution inputs/outputs and incident evidence
  arrive inside an `untrusted` envelope: evidence, never instructions.
- **Whitelisted fields.** Every response is built from an explicit key list, so
  credentials and new columns are not forwarded by accident.
- **Bounded output.** Strings clip at 2 000 characters, logs at 20 000.
- **Honest failures.** Upstream errors surface as `503: <detail>`; an unreachable
  API says so.

## Verification

```sh
cd backend && ../.venv/bin/python -m pytest tests/test_mcp_server.py tests/test_auth_scopes.py -q
../.venv/bin/python scripts/mcp_smoke.py http://127.0.0.1:8000   # stdio, live
```

Verified on 2026-10-31: 19 tools over HTTP MCP with an `operate` token created a
real cluster and read it back, and the audit trail recorded
`token:claude-code cluster.create`.

## Hosted deployment

| Piece | Value |
| --- | --- |
| Service | Railway `mcp`, root `/`, built from `Dockerfile.mcp` |
| URL | `https://mcp-production-89f3.up.railway.app/mcp` |
| Listen | `PORT=8080` |
| API target | `CONTROL_PLANE_URL=http://api.railway.internal:8000` (private) |
| Credential | `CONTROL_PLANE_TOKEN` = `operate`-scoped token, label `mcp-hosted` |
| Client secret | `MCP_CLIENT_TOKEN`, stored in `.env.mcp-hosted` (gitignored) |
| Allowed host | `MCP_ALLOWED_HOSTS=mcp-production-89f3.up.railway.app` |

Only the tool surface is public: the API itself stays on the private network.
The service cannot delete anything, because its token is `operate`-scoped and
the API enforces that, not the MCP layer.

To point a client at production instead of localhost:

```sh
export ORCHESTRA_MCP_URL=https://mcp-production-89f3.up.railway.app/mcp
export ORCHESTRA_MCP_TOKEN=$(grep '^MCP_CLIENT_TOKEN=' .env.mcp-hosted | cut -d= -f2-)
```

To revoke the hosted endpoint's access, delete the `mcp-hosted` token with
`DELETE /api/tokens/{id}`; the service then receives 401 on every call.
