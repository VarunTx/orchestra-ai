# Architecture

Reference for the code as it exists today. Where behaviour is uncertain or unverified, this document says so. See `docs/PROGRESS.md` for verified milestones and `docs/RAILWAY.md` for the deployed trial stack.

## Topology (Docker Compose)

| Service | Image / runtime | Listener | Role |
| --- | --- | --- | --- |
| `web` | Next.js 16.4.2 on Node 22.18 (standalone) | `127.0.0.1:3000` | Dashboard and the only public entry point |
| `api` | FastAPI on Python 3.11 | `127.0.0.1:8000` | Authenticated gateway, resource API **and the monitoring collector** |
| `workers` | Same image, `python -m app.workers` | none | Official `conductor-python` TaskHandler polling |
| `conductor` | `conductoross/conductor` pinned by digest | `:8080`, private network | Sole orchestration engine |
| `redis` | `valkey/valkey:8.1-alpine` | private network | Conductor execution lock only (BSD-licensed) |
| `postgres` | `postgres:16.6-alpine` | private network | Two databases: `conductor` (engine) and `orchestra` (platform) |
| `caddy` | `caddy:2.10-alpine`, profile `public` | `:80`, `:443` | TLS front door for the free-VM deployment |

The platform database is created on first API startup and migrated from `backend/app/migrations/`. It never lives inside Conductor's schema, so engine upgrades and platform migrations are independent.

## Layers

```
Browser → Next.js route handlers → FastAPI → Conductor REST → workers
                                  ↘ orchestra database (projects, services, observations…)
Collector (inside FastAPI) → HTTP health checks → orchestra database → incidents → webhooks
```

### Request path

1. Browser code (`components/pages/*`, `components/app-shell.tsx`) calls only its own origin.
2. `app/api/session/route.ts` exchanges the owner password or master API token for an opaque session token and stores it in `cp_session` (`httpOnly`, `sameSite: strict`, `secure` when configured, 8 h).
3. `app/api/[...path]/route.ts` proxies an explicit allowlist of resource segments (`projects`, `services`, `clusters`, `environments`, `deployments`, `incidents`, `alerts`, `connectors`, `dashboard`, `audit`, `settings`, `schedules`, plus the legacy `workflows`/`executions`/`infrastructure`). Unknown segments return 404. Non-GET requests require an exact `Origin` from `APP_ORIGINS`.
4. `api_resources.py` validates input with Pydantic (`extra='forbid'`, bounds, enums) and delegates to `store.py`.
5. `engine.py` is Conductor's only client: 12 s timeout, up to 3 attempts for `GET`, exactly 1 for mutations, HTTP 5xx mapped to 502/503.

### Authentication

- `auth.py` accepts either the master token (constant-time compare) or a session token whose SHA-256 is stored in `sessions`.
- Sessions are revoked on sign-out and expire after `SESSION_TTL_HOURS`; expired rows are pruned.
- The owner password is stored only as a scrypt hash (`app_settings.owner_password_hash`), re-derived when `OWNER_PASSWORD` changes.
- Login attempts are rate-limited per client address inside the process.
- No credential is ever placed in the browser bundle, HTML or `localStorage`.

### Monitoring collector

`monitor.py` runs as an asyncio task inside the API process (`MONITOR_ENABLED=true`):

- Every `MONITOR_TICK_SECONDS` it takes a PostgreSQL advisory lock, selects services whose `last_checked_at + interval <= now()`, and probes them with bounded concurrency.
- A probe is a `GET` with `follow_redirects=False`, a hard timeout and a 2 KB body cap. Targeted URLs pass `security.resolve_public`, which rejects non-HTTP(S), embedded credentials, and hosts resolving to loopback/private/link-local/reserved addresses unless `HTTP_CHECK_ALLOW_PRIVATE=true`.
- Outcomes: expected status → `healthy`; unexpected 2xx → `degraded`; other status or transport failure → `down`; unusable target or DNS failure → `unknown`.
- `unknown` never changes a service's status and never opens an incident — a monitoring gap is not an outage.
- Status transitions apply `failure_threshold`/`recovery_threshold`, open one incident per service, resolve it on recovery, and recompute the project's aggregate status.
- Pruning removes old observations, excess per-service history and expired sessions.

Conductor is not used as the polling scheduler: checks are per-service and dynamic, and the scheduler would require a registered workflow per configuration change. Conductor remains responsible for durable diagnostic workflows; the collector performs collection only.

### Incidents and alerts

- `incidents` has a partial unique index on `(service_id) WHERE resolved_at IS NULL`, so a continuing failure cannot create duplicates.
- `incident_events` is an append-only trail (opened, acknowledged, note, resolved) with actor attribution.
- `alerts` store sealed webhook targets; delivery is attempted only when severity and cooldown allow, and every attempt is recorded in `notifications`.
- Webhook targets are SSRF-checked at send time; a rejected target is recorded as a failed delivery.

### Engine profile

`infra/conductor.properties` implements the docs' "PostgreSQL stack (simplest)":

- `conductor.db.type`, `conductor.queue.type`, `conductor.external-payload-storage.type` and `conductor.indexing.type` are all `postgres`.
- `conductor.workflow-execution-lock.type=redis` against Valkey; the lock is released between decisions, so an idle keyspace is expected.
- Sweeper (`sweeperThreadCount=8`, 2 s poll, batch 2) keeps long-running workflows progressing.
- System task workers run 20 threads / 20 polls for HTTP, Wait, Inline and Switch tasks.
- Payload thresholds: 5 MB workflow input/output spill to external storage, 10 MB hard limit; tasks 3 MB / 10 MB; workflow variables 256 KB.
- Micrometer metrics are exposed at `/actuator/prometheus`; the Elasticsearch health indicator is disabled because indexing is PostgreSQL-native (without this, `/actuator/health` reports DOWN while the engine is healthy).

### Telemetry

`telemetry.py` parses the Prometheus exposition format and sums the series that matter: workflow failure counters by status, successful starts, in-flight tasks, mean task execution and queue-wait time, JVM heap and uptime. Queue depth comes from `GET /api/tasks/queue/size?taskType=…` per managed task. The result is attached to `GET /api/infrastructure` as `engine.telemetry`. A missing series yields `null` and the UI renders `—`; nothing is estimated.

### Task domains

`TASK_DOMAIN` adds `taskToDomain: {"*": "<domain>, NO_DOMAIN"}` to every start request, which is the documented fallback order. `WORKER_DOMAIN` makes a worker fleet poll that domain (`@worker_task(domain=…)`, supported by `conductor-python`). With neither set, all tasks use the default queue. Domains are the isolation primitive here; `isolationGroupId` only applies to HTTP/Kafka system tasks and is not used.

### Connectors

`connectors.py` defines typed adapters:

| Adapter | API | Notes |
| --- | --- | --- |
| `RailwayConnector` | GraphQL `backboard.railway.app/graphql/v2` | `me.projects.services` inventory; no per-service health. Unverified without a real token. |
| `GitHubConnector` | REST `api.github.com` | Repo metadata, commits, workflow runs → deployment events. Rate-limit aware. |
| Docker agent | Inbound `POST /api/agent/observations` | Token-authenticated per connector; services linked by `external_ref.agentKey`. |

Credentials are AES-GCM sealed with a key derived from `SECRET_KEY` (HKDF-SHA256), and are never serialized into responses. Rotation re-seals the value and keeps the old one unreadable.

### Data model (platform database)

`clusters`, `projects`, `environments`, `services`, `deployments`, `connectors`, `observations`, `incidents`, `incident_events`, `alerts`, `notifications`, `audit_log`, `sessions`, `app_settings` and `schema_migrations`.

`services.current_status`, `consecutive_failures` and `last_checked_at` are denormalised so dashboards stay cheap; every status is traceable to observation rows that carry `source` and `observed_at`.

## Conductor workflows and tasks

Both managed workflows are `version: 1`, `schemaVersion: 2`, `restartable: true`, workflow timeout 600 s, and share the shape `normalize → analyze → report`:

| Workflow | Middle task | Provider |
| --- | --- | --- |
| `incident_analysis` | `cp_analyze_incident` | Gemini (`gemini-2.5-flash` by default) |
| `diagnostic_pipeline` | `cp_diagnose_incident` | Deterministic keyword analysis |

Task definitions: `timeoutSeconds` 90, `responseTimeoutSeconds` 75, `timeoutPolicy: RETRY`, `retryCount` 2 with a fixed 3 s delay — except `cp_analyze_incident`, which has `retryCount: 0` so an ambiguous failure never becomes a second billable call.

`workers.py`:

| Task | Work | Idempotency |
| --- | --- | --- |
| `cp_normalize_incident` | Validates and trims evidence, counts lines, hashes evidence | Pure |
| `cp_diagnose_incident` | Keyword scan, honours diagnostic failure/delay injection | Pure; no external writes |
| `cp_analyze_incident` | One Gemini request with a JSON schema; failures surface only type + HTTP status | Pure, but billable |
| `cp_publish_report` | Assembles the report with `generated_at` and `requires_human_review: true` | Pure |

Definitions are installed by the API lifespan hook (idempotent `POST metadata/taskdefs`, `PUT metadata/workflow`), retried for 180 s on 502/503. Startup fails if registration cannot complete.

Additional definitions may be registered through `POST /api/workflows/definitions`. Validation is intentionally narrow: name/schema/version bounds, 1–25 tasks, `type` restricted to `SIMPLE`, task names restricted to the four worker-backed definitions, unique `taskReferenceName`, bounded `inputParameters`, and a 409 when the name+version already exists. `HTTP`, `EVENT`, `SUB_WORKFLOW` and dynamic operators are rejected, so the endpoint cannot be used to call internal services or execute arbitrary code. Registration is audited.

## API surface

| Route | Behaviour |
| --- | --- |
| `POST /api/session` | Password/token → opaque session token (rate-limited) |
| `GET/DELETE /api/session` | Session check; revoke |
| `GET /api/dashboard` | Aggregates, attention list, incidents, deployments, stale checks, failed executions |
| `GET/POST /api/projects`, `GET/PATCH/DELETE /api/projects/{id}` | Project CRUD with nested environments/services on create |
| `POST /api/projects/{id}/environments`, `DELETE /api/environments/{id}` | Environments |
| `GET/POST /api/services`, `GET/PATCH/DELETE /api/services/{id}` | Service CRUD |
| `GET /api/services/{id}/observations`, `POST /api/services/{id}/check` | History; immediate real check |
| `GET/POST /api/clusters`, `PATCH/DELETE /api/clusters/{id}` | Clusters |
| `GET /api/deployments`, `POST /api/deployments` | Deployment history and recording |
| `GET /api/incidents`, `GET /api/incidents/{id}`, `…/acknowledge`, `…/resolve`, `…/notes` | Incident workflow |
| `GET/POST /api/alerts`, `DELETE /api/alerts/{id}` | Webhook alerts |
| `GET/POST /api/connectors`, `PATCH/DELETE /api/connectors/{id}`, `…/validate`, `…/sync` | Connector lifecycle |
| `POST /api/agent/observations` | Agent ingest (connector token, not an owner session) |
| `GET /api/audit`, `GET /api/settings` | Audit trail, read-only runtime configuration |
| `GET /api/workflows`, `GET /api/workflows/catalog`, `GET /api/schedules` | Managed definitions, engine-wide catalog, read-only schedules |
| `POST /api/workflows/definitions` | Validated registration of worker-backed SIMPLE definitions |
| `POST /api/executions`, `GET /api/executions`, `GET /api/executions/{id}`, `…/retry`, `…/terminate` | Execution operations |
| `GET /api/infrastructure` | Engine latency, worker poll ages, Gemini state, real database probe |
| `GET /healthz` | Unauthenticated liveness |

## Trust boundaries and limits

- **Single tenant, single owner.** One credential grants access to everything. `owned_execution` filters by managed workflow type, not by owner.
- **Untrusted data.** Incident logs, task input/output, provider payloads and observation messages are untrusted content. They are displayed and passed as prompt data only; never executed.
- **Honest telemetry.** No synthetic CPU, memory, uptime or cost metrics exist. Provider silence renders as unknown.
- **Conductor is the source of truth** for execution state; the platform never caches or rewrites it.
- **SSRF residual risk.** Targets are resolved and checked immediately before each request, but the connection is made by hostname, so a DNS-rebinding attack between resolution and connection is theoretically possible. Redirects are not followed and targets are owner-configured, which bounds the exposure; pinning the resolved address would close it.

## Configuration

| Variable | Consumer | Notes |
| --- | --- | --- |
| `CONTROL_PLANE_TOKEN` | api | ≥32 chars; master token for scripts |
| `OWNER_PASSWORD` | api | Dashboard password; hashed at rest |
| `SECRET_KEY` | api | Connector credential encryption key |
| `POSTGRES_PASSWORD` | postgres, conductor | Required by Compose |
| `DATABASE_NAME`/`DATABASE_URL` | api | Platform database (default `orchestra`) |
| `CONDUCTOR_URL` | api, workers | `http://conductor:8080/api` in Compose |
| `API_URL` | web | Server-only; never bundled |
| `APP_ORIGINS`, `COOKIE_SECURE` | web | Origin allowlist and cookie security |
| `MONITOR_ENABLED`, `MONITOR_TICK_SECONDS`, `MONITOR_CONCURRENCY`, `MONITOR_RETENTION_DAYS` | api | Collector |
| `HTTP_CHECK_ALLOW_PRIVATE` | api | Development-only private targets |
| `ENABLE_GEMINI`, `GEMINI_API_KEY`, `GEMINI_MODEL` | api, workers | Billable; disabled by default |

## Operating and verifying

- `make up` builds and waits for the stack; `make test-db` runs the complete backend suite in the Compose network; `make typecheck`, `make build`, `make browser`, `make smoke`.
- `scripts/deploy_wizard.sh` provisions a free VM deployment (`compose.prod.yaml` + Caddy profile); `scripts/backup.sh` and `scripts/restore.sh` cover both databases. See `docs/DEPLOY_FREE.md`.
- `scripts/docker_agent.py` pushes local container health from a machine that owns Docker.
- `scripts/smoke.py` exercises the real engine; `scripts/recovery.py` is destructive and local-only.
- CI runs typecheck, build, Compose up, backend tests, smoke, Playwright and recovery, then tears the stack down.
