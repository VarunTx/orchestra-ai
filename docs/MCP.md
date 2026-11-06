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
| HTTP | `docker compose --profile mcp up -d --build --wait mcp` | local agents over `127.0.0.1:8765` |

The default deployment is the local Docker Compose stack. The HTTP transport is
the `mcp` service in `compose.yaml`, built from `Dockerfile.mcp`, and is bound to
loopback only: **http://127.0.0.1:8765/mcp**.

### Why the `mcp` profile

`.env.mcp-local` is gitignored, so it is absent in a fresh clone and in CI.
Enabling the service by default would make `make up` / `docker compose up`
fail before the rest of the stack starts. The service therefore lives behind a
Compose profile named `mcp`; start it explicitly with the command above. The
`mcp` profile is not part of `make up` unless you enable the profile.

Run it locally without Docker if you prefer:

```sh
cd backend
CONTROL_PLANE_URL=http://127.0.0.1:8000 \
CONTROL_PLANE_TOKEN=<operate-scoped token> \
MCP_CLIENT_TOKEN=<client secret> \
PORT=8765 python -m app.mcp_server --http
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `CONTROL_PLANE_URL` | `http://127.0.0.1:8000` | API base URL; the Compose service uses `http://api:8000` |
| `CONTROL_PLANE_TOKEN` | required | Token the **server** uses to call the API. Its scope bounds everything an agent can do. |
| `MCP_CLIENT_TOKEN` | required for `--http` | Bearer secret **clients** present to the MCP endpoint |
| `PORT` / `HOST` | `8765` / `0.0.0.0` | HTTP listen address; the Compose service sets `PORT=8765` |
| `MCP_ALLOWED_HOSTS` | `localhost`, `127.0.0.1` (with and without `:8765`) | Comma-separated `Host` values accepted by the SDK's DNS-rebinding protection |

The SDK compares the `Host` header exactly, **including a non-default port**.
`MCP_ALLOWED_HOSTS` must therefore contain the `host:port` forms clients send:
`localhost:8765` and `127.0.0.1:8765`, as well as the bare hostnames.

The Compose service reads `.env.mcp-local` (gitignored). That file must define:

```sh
MCP_CLIENT_TOKEN=<client secret>
MCP_CONTROL_PLANE_TOKEN=<operate-scoped token, never the master token>
```

The service maps `MCP_CONTROL_PLANE_TOKEN` to `CONTROL_PLANE_TOKEN` and refuses
to start if the key is absent. It never falls back to the master token in
`.env`.

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

Claude Code — `.mcp.json` is committed, defaults to the local HTTP endpoint and
reads two environment variables:

```sh
export ORCHESTRA_MCP_URL=http://127.0.0.1:8765/mcp
export ORCHESTRA_MCP_TOKEN=$(grep '^MCP_CLIENT_TOKEN=' .env.mcp-local | cut -d= -f2-)
claude mcp list        # orchestra  connected
```

Codex — `.codex/config.toml` is project-scoped and points at the same local
endpoint:

```toml
[mcp_servers.orchestra]
url = "http://127.0.0.1:8765/mcp"
bearer_token_env_var = "ORCHESTRA_MCP_TOKEN"
default_tools_approval_mode = "writes"
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
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/healthz
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8765/mcp
```

The first `curl` should return `200`; the unauthenticated POST should return
`401`. `GET /healthz` is the Compose healthcheck and exposes no control-plane
data.

`scripts/mcp_smoke.py` targets a stdio server and still asserts the removed
`MCP_ENABLE_WRITES` gate, so it does not match the current scoped-token server.
Do not treat it as a live check of this HTTP endpoint without updating it.

## Local operation

| Piece | Value |
| --- | --- |
| Compose service | `mcp`, profile `mcp`, built from `Dockerfile.mcp` at the repo root |
| URL | `http://127.0.0.1:8765/mcp` |
| Publish | `127.0.0.1:8765:8765` only |
| API target | `CONTROL_PLANE_URL=http://api:8000` (private Compose network) |
| Credential | `MCP_CONTROL_PLANE_TOKEN` from `.env.mcp-local`, `operate`-scoped |
| Client secret | `MCP_CLIENT_TOKEN` from `.env.mcp-local` |
| Allowed host | `localhost`, `127.0.0.1`, `localhost:8765`, `127.0.0.1:8765` |

Only the tool surface is published, and only on loopback. The API itself stays
on the private Compose network. The service cannot delete anything because its
token is `operate`-scoped and the API enforces that, not the MCP layer.

To revoke access, delete the scoped token with `DELETE /api/tokens/{id}`; the
service then receives 401 on every call.

## OpenAI clients

### Codex CLI

`.codex/config.toml` is committed and project-scoped:

```sh
export ORCHESTRA_MCP_TOKEN=$(grep '^MCP_CLIENT_TOKEN=' .env.mcp-local | cut -d= -f2-)
codex mcp list        # orchestra ... enabled  Bearer token
codex                 # then: "create a cluster called Payments and list clusters"
```

`default_tools_approval_mode = "writes"` means read tools run unattended while
anything that mutates waits for confirmation. In an interactive session that is
the intended behaviour.

For **non-interactive** runs (`codex exec`), Codex's approval policy is `never`,
so every MCP call is refused with `MCP tool call requires approval, but approval
policy is never`. Scripted runs therefore need
`codex exec --dangerously-bypass-approvals-and-sandbox "..."`. Use that only in
a sandbox you control; the interactive client does not need it.

### ChatGPT desktop app

The desktop app, Codex CLI and the IDE extension share MCP configuration for the
same Codex host. Add the server under **Settings → MCP servers → Add server**:
type Streamable HTTP, URL `http://127.0.0.1:8765/mcp`, bearer token from
`.env.mcp-local`. The desktop app must run on the same machine as the Compose
stack.

### OpenAI Responses API

If you would rather call the model from a script, the Responses API accepts a
remote MCP server directly, so the same local endpoint works without a CLI:

```python
tools=[{"type": "mcp", "server_label": "orchestra",
        "server_url": "http://127.0.0.1:8765/mcp",
        "headers": {"Authorization": f"Bearer {token}"}}]
```

Not verified here: no `OPENAI_API_KEY` was used, so this path is documented from
the API shape rather than executed.
