# MCP server

`backend/app/mcp_server.py` exposes the control plane to MCP clients (OpenCode,
Claude Code, Claude Desktop) over **stdio**. It is a façade over the authenticated
REST API, so authentication, audit records and project scoping stay on one path.
It never talks to Conductor directly and never touches the database.

## Run it

```sh
cd backend
CONTROL_PLANE_URL=http://127.0.0.1:8000 \
CONTROL_PLANE_TOKEN=<same value as the API> \
python -m app.mcp_server
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `CONTROL_PLANE_URL` | `http://127.0.0.1:8000` | API base URL. The token is sent as `Authorization: Bearer`. |
| `CONTROL_PLANE_TOKEN` | required | Control-plane token. Never logged, never returned in a tool result. |
| `MCP_ENABLE_WRITES` | `false` | Enables the two audited write tools. |

Client configuration (OpenCode `opencode.json`):

```json
{
  "mcp": {
    "orchestra": {
      "type": "local",
      "command": ["python", "-m", "app.mcp_server"],
      "cwd": "backend",
      "environment": { "CONTROL_PLANE_TOKEN": "${CONTROL_PLANE_TOKEN}" },
      "enabled": true
    }
  }
}
```

## Tools

Read tools are always registered.

| Tool | Calls | Notes |
| --- | --- | --- |
| `list_executions` | `GET /api/executions` | Whitelisted summary fields; `size` capped at 25 |
| `get_execution` | `GET /api/executions/{id}` | Task states and retry counts; inputs/outputs marked untrusted |
| `list_incidents` | `GET /api/incidents` | `status="active"` for unresolved |
| `get_incident` | `GET /api/incidents/{id}` | Events included; observation count only |
| `infrastructure_health` | `GET /api/infrastructure` | Storage, engine, telemetry, API, worker polling, AI state |
| `list_workflow_definitions` | `GET /api/workflows` | Name, version, description, task names |

Write tools require `MCP_ENABLE_WRITES=true`; while it is off they return an
`is_error` result explaining the flag instead of failing silently.

| Tool | Calls | Guard |
| --- | --- | --- |
| `start_diagnostic` | `POST /api/executions` | Always `diagnostic_pipeline`, never `incident_analysis`; `record_kind=verification`; `failure_mode=none` |
| `acknowledge_incident` | `POST /api/incidents/{id}/acknowledge` | Note capped at 500 characters |

## Safety properties

- **No paid calls.** `incident_analysis` is not reachable: the tool hard-codes the
  workflow name. Gemini stays disabled.
- **Untrusted data is labelled.** Execution inputs/outputs and incident evidence
  are returned inside an `untrusted` envelope with a notice that the text is
  evidence, never instructions. This is the prompt-injection boundary: the same
  agent must not treat log text as a command.
- **Whitelisted fields only.** Every response is built from an explicit key list,
  so connector credentials, API keys and other new columns are not forwarded by
  accident. `/api/connectors` is not exposed at all.
- **Bounded output.** Strings are clipped to 2000 characters and logs to 20 000,
  so one tool call cannot flood an agent's context.
- **Honest failures.** Upstream errors surface as `503: <detail>`; an unreachable
  API says so. Nothing is invented or cached to look healthy.

## Verification

```sh
cd backend && ../.venv/bin/python -m pytest tests/test_mcp_server.py -q
# live, against a running stack (read-only):
.venv/bin/python scripts/mcp_smoke.py http://127.0.0.1:8000
```

## Hosted deployments

The API has no public domain: the dashboard proxies over the private network, so
a laptop cannot reach the Railway API directly. Two supported options:

1. Run the MCP server on the same private network (for example as the service's
   own entrypoint) and expose only the transport you need.
2. Point `CONTROL_PLANE_URL` at a local Compose stack for development.

Do not publish the API domain just to reach it from a laptop; that widens the
internet-facing surface for a convenience feature.
