# Architecture

Reference for the code as it exists today. Where behavior is uncertain or unprobed, this document says so instead of guessing. See `docs/PROGRESS.md` for verified milestones and `docs/RAILWAY.md` for the deployed trial stack.

## Topology (Docker Compose)

| Service | Image / runtime | Listener | Role |
| --- | --- | --- | --- |
| `web` | Next.js 16.4.2 on Node 22.18 (standalone build) | `127.0.0.1:3000` | Dashboard UI and the only public entry point |
| `api` | FastAPI on Python 3.11 | `127.0.0.1:8000` | Authenticated gateway, no orchestration logic |
| `workers` | Same image, `python -m app.workers` | none | Official `conductor-python` TaskHandler polling |
| `conductor` | `conductoross/conductor` pinned by digest | `:8080`, private network | Sole orchestration engine |
| `postgres` | `postgres:16.6-alpine` | private network | Conductor persistence |

Conductor and PostgreSQL are never published to the host in Compose. `docker compose down` keeps the named volume `orchestra-ai_postgres_data`.

## Request flow

1. Browser (`frontend/components/control-plane.tsx`) calls only its own origin: `/api/session` and `/api/<segment>/...`.
2. `frontend/app/api/session/route.ts` validates the entered token against the API and, on success, stores it in the `cp_session` cookie (`httpOnly`, `sameSite: strict`, `secure` on HTTPS, 8 h).
3. `frontend/app/api/[...path]/route.ts` proxies `workflows`, `executions` and `infrastructure` only. It rejects unknown segments (404), rejects non-GET requests whose `Origin` is not in the pinned allowlist (403), reads the token from the cookie, and forwards it as a bearer token with a 45 s timeout.
4. `backend/app/main.py` authenticates every route with `hmac.compare_digest` against `CONTROL_PLANE_TOKEN` (constant-time, 401 + `WWW-Authenticate` otherwise). Responses set `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.
5. `backend/app/engine.py` is the only Conductor client: base URL `CONDUCTOR_URL`, 12 s timeout, up to 3 attempts for `GET`, exactly 1 attempt for mutations, HTTP 5xx mapped to 502/503.
6. Conductor schedules tasks; workers long-poll, execute, and return task output. All state, retries and history live in Conductor + PostgreSQL.

The frontend holds no server-side session store; each request re-reads the cookie. The overview polls every 5 s, the open execution detail every 3 s.

## Workflows and tasks

Both workflows are `version: 1`, `schemaVersion: 2`, `restartable: true`, workflow timeout 600 s, and share the shape `normalize → analyze → report`:

| Workflow | Middle task | Provider |
| --- | --- | --- |
| `incident_analysis` | `cp_analyze_incident` | Gemini (`gemini-2.5-flash` by default) |
| `diagnostic_pipeline` | `cp_diagnose_incident` | Deterministic keyword analysis |

Task definitions (`backend/app/definitions.py`): `timeoutSeconds` 90, `responseTimeoutSeconds` 75, `timeoutPolicy: RETRY`, `retryCount` 2 with fixed 3 s delay — except `cp_analyze_incident`, which has `retryCount: 0` so an ambiguous failure never becomes a second billable call.

`backend/app/workers.py`:

| Task | Work | Idempotency |
| --- | --- | --- |
| `cp_normalize_incident` | Validates and trims evidence, counts lines, hashes evidence (`sha256`) | Pure |
| `cp_diagnose_incident` | Keyword scan over evidence, honours diagnostic failure/delay injection | Pure; no external writes |
| `cp_analyze_incident` | One Gemini request with a JSON response schema; failures surface only type + HTTP status | Pure, but billable |
| `cp_publish_report` | Assembles the report with `generated_at` and `requires_human_review: true` | Pure |

Definitions are installed by the API lifespan hook on startup (idempotent `POST metadata/taskdefs`, `PUT metadata/workflow`, retried for 180 s on 502/503). Startup fails if registration cannot complete.

## API surface

| Route | Behavior |
| --- | --- |
| `GET /healthz` | Unauthenticated liveness |
| `GET /api/session` | Token check used by the login form |
| `GET /api/workflows` | Conductor definitions filtered to the two managed workflows |
| `POST /api/executions` | Validated start (`extra='forbid'`, bounded fields); Gemini workflows return 409 when disabled; failure injection restricted to diagnostics |
| `GET /api/executions` | Conductor search restricted to the two managed types, `size` 1–100 |
| `GET /api/executions/{id}` | Execution plus tasks; 404 for unmanaged workflow types |
| `POST /api/executions/{id}/retry` | Only `FAILED`/`TIMED_OUT` |
| `POST /api/executions/{id}/terminate` | Only `RUNNING`/`PAUSED` |
| `GET /api/infrastructure` | Engine reachability and latency, worker poll ages, Gemini and storage status |

## Trust boundaries and limits

- **Single tenant, single credential.** One shared token grants access to every execution of the two managed workflows. There is no per-user identity, no role model and no tenant field; `owned_execution` filters by workflow type, not by owner.
- **Untrusted data.** Incident logs, task inputs/outputs and workflow history are untrusted content and may contain instructions. They are prompt data only and must never drive control flow.
- **Honest telemetry.** `/api/infrastructure` reports `storage` as `not independently probed`; worker state is derived from Conductor poll timestamps and is `unavailable`/`unknown` when absent. No synthetic metrics are produced.
- **AI is off by default.** `ENABLE_GEMINI=false` unless explicitly enabled with a key; the API and the analysis worker both refuse to run otherwise.

## Configuration

| Variable | Consumer | Notes |
| --- | --- | --- |
| `CONTROL_PLANE_TOKEN` | api | ≥32 characters; generated by `scripts/setup_env.py` |
| `POSTGRES_PASSWORD` | postgres, conductor | Required by Compose |
| `CONDUCTOR_URL` / `CONDUCTOR_HOST` | api, workers | Compose sets `http://conductor:8080/api` |
| `API_URL` / `API_HOST` | web | Server-only; never bundled |
| `APP_ORIGINS` | web | Exact origin allowlist for mutations and cookies |
| `COOKIE_SECURE` | web | `true` for HTTPS deployments |
| `ENABLE_GEMINI`, `GEMINI_API_KEY`, `GEMINI_MODEL` | api, workers | Billable; disabled by default |

`.env` is git-ignored; `.env.example` documents the shape without secrets.

## Operating and verifying

- `make up` builds and waits for the stack; `make test` runs pytest and the type check; `make smoke` exercises the real engine; `make browser` runs Playwright; `make recovery` is destructive and local-only.
- CI (`.github/workflows/ci.yml`) runs pytest, `npm ci`, type check, Compose up, `scripts/smoke.py`, Playwright and `scripts/recovery.py`, then tears the stack down.
- The Railway trial deployment runs the same five services with only the dashboard public; see `docs/RAILWAY.md`. Never run recovery tests there.
