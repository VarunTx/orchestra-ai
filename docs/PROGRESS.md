# Progress and verification

## Delivered

- FastAPI gateway with constant-time token authentication, bounded input validation, safe upstream failures and read-only request retries.
- Two real versioned Conductor workflows, four official SDK Python workers, bounded task retries/timeouts, and PostgreSQL persistence/search.
- Next.js/TypeScript/Tailwind dashboard with shadcn-style Radix button, definitions/DAG/JSON, execution history, live task inspection and truthful infrastructure observations.
- Private Compose deployment, non-root application images, locked dependencies, HTTP-only sessions, explicit origin checks and configurable secure cookies.
- Smoke, unit, browser and crash-recovery tests; GitHub Actions; architecture/setup/deployment documentation and real screenshots.

## Verified locally — October 19, 2026

- All five Compose services built and started successfully.
- 13 backend tests passed (one dependency deprecation warning from Starlette's httpx TestClient integration).
- Frontend strict TypeScript check passed.
- Docker and native macOS Next.js production builds passed. An initial native build cache retained a sandbox error; moving that cache aside resolved it.
- Real engine smoke tests passed: success (one analysis attempt), fail-once recovery (two), failure exhaustion (three), manual retry, termination, and status-filtered search.
- Playwright Chromium tests passed: protected API/origin checks and full browser sign-in → real fail-once execution → task output → definition explorer → infrastructure → mobile layout. No browser page errors.
- Worker recovery tests passed: queued work survived stopped workers; an in-flight diagnostic recovered after SIGKILL through engine timeout/retry; completed history persisted across a Conductor restart.
- Four SDK task workers have actual recent Conductor poll observations.
- Desktop/mobile screenshots reviewed and saved under docs/screenshots.
- Dependency installation reported zero npm audit vulnerabilities at installation time.

## Live AI blocker

Exactly one authorized Gemini test was made with synthetic incident text. Workflow `393023a2-2064-4b37-a3e3-6f616de5cebe` normalized its input and failed in the Gemini task with a provider `ClientError`. No automatic provider/task retries were made. The original error was sanitized; the precise credential/model/quota cause was not retained. Gemini was disabled again afterward. A valid provider configuration and authorization for another request are required to verify a successful AI result. Mocked structured-result validation is covered, but does not substitute for live verification.

## Deployment boundaries

At the initial delivery checkpoint, no remote was configured. The Orchestra AI repository is now pushed to GitHub and Actions verification has started; no public deployment has been performed. The locally built Compose deployment is the verified deployment target. Production security/backup/HA requirements and feature scope are documented in README.md and DEPLOYMENT.md.

## Checkpoints

- `c676a0f`: initial full implementation and deterministic execution verification.
- Final verification/docs/fixes checkpoint follows this report; consult `git log` for its hash.

## Orchestra AI rename and Render preparation

- Renamed product UI, page metadata, API title, npm package and Compose project to Orchestra AI.
- Preserved the original local PostgreSQL volume during the Compose rename; real history remains available.
- Replaced the Gemini credential in ignored `.env`; no new provider request has been made.
- Added runtime hosted/local labels, Render private DNS configuration, secure cookies and Render-origin validation.
- Added `render.yaml`: dashboard, private API/engine, worker group and private managed PostgreSQL. Paid resources have not been provisioned.
- Render's official JSON schema and cross-resource references validate; hosted Conductor image builds successfully.
- Private GitHub repository created: https://github.com/VarunTx/orchestra-ai. Source pushed successfully at commit `e366693`; GitHub Actions verification started.
- Render account connection and its concrete hosting cost approval are still needed before provisioning.

## Zero-cost public demo — October 19, 2026

- User required no hosting charges and authorized switching away from Render. Render account connection and My Workspace selection succeeded earlier, but Dashboard browser access remains blocked by saved permissions. No bypass was attempted and no Render resources were provisioned.
- Confirmed Render's prepared multi-service Blueprint uses paid resources. Do not apply it under the current zero-cost requirement.
- Started accountless Cloudflare Quick Tunnel to the existing Docker Desktop web service. No new cloud account/payment method or paid resource was created.
- Public demo: https://tagged-uni-sphere-psychological.trycloudflare.com . This is temporary public access to the Mac, NOT independent cloud hosting. Mac, Docker and tunnel must stay running; hostname changes on tunnel recreation.
- Set exact public allowed origin and Secure/HttpOnly session cookies; kept Gemini disabled. No Gemini request was made.
- Verified public HTTPS returns 200, unauthenticated API access returns 401, authenticated definitions load, and session cookie is Secure and HttpOnly.
- Both existing Playwright tests passed through the public URL (9.2 seconds), including real diagnostic execution with fail-once retry, deterministic task output, definitions, actual worker polling, and mobile layout. Screenshots refreshed by those tests.
- Added docs/FREE_DEMO.md with login, lifetime limitations and stop/restart instructions. Permanent free cloud hosting remains blocked on a suitable provider account/capacity; this demo does not satisfy that part of the original hosting request.

## Temporary tunnel repair — October 19, 2026

- The initial demo hostname stopped resolving. Cloudflared logged `Unauthorized: Tunnel not found` while the local application remained healthy (HTTP 200).
- Restarted the tunnel and replaced the stale public origin in ignored `.env`; restarted only the web service.
- Replacement: https://harvest-transmit-jelsoft-trades.trycloudflare.com . Verified public HTTP 200, unauthenticated API rejection, secure-cookie token login and authenticated workflow definitions. No paid resources or AI calls.
- Updated FREE_DEMO.md. Quick Tunnel availability is not guaranteed even when the local container is running; permanent hosting remains unresolved.

## Independent free hosting investigation — October 19, 2026

- User requested hosting independent of the Mac, with no domain purchase and no charges.
- Current official Hugging Face docs require a paid plan for new Docker compute Spaces, so that is not a zero-cost alternative.
- Railway documents a no-card new-user trial with $5 credit, up to 30 days, five services per project and 1 GB RAM limits. This is a candidate for the requested short demo, not a permanent free-hosting guarantee. Trial eligibility, actual available limits and reduced-memory Conductor operation still need verification.
- Made the Railway connector installation option available. No Railway resources created and no paid subscription authorized. Deployment is blocked on account connection/eligibility; retain Gemini disabled and do not upgrade to a paid plan.
- References: https://docs.railway.com/pricing/free-trial ; https://docs.railway.com/pricing/faqs ; https://huggingface.co/docs/hub/en/spaces-overview

## Railway staged deployment — October 19, 2026

- Railway connected as VarunTx. Dashboard verified a fresh trial: 30 days or $5 remaining.
- Created private project Orchestra AI (`68e2641a-a387-4bcf-9307-e25eadebe42f`), production environment (`b0275afe-d627-48e4-b265-3a12b3d1e8f7`), five empty services, and dashboard domain `web-production-95d5e.up.railway.app`.
- Staged 83 changes: GitHub sources pinned at `1c0ce19`, Docker roots, bounded memory/CPU, private service references, 500 MB PostgreSQL volume, generated database password, existing workspace token, secure cookie/exact origin, hosted labels, and Gemini disabled (no Gemini key uploaded).
- Conductor staged with 512 MB JVM heap and 1 GB memory cap; runtime suitability remains unverified. Trial credit duration is usage-dependent and no uptime duration is promised.
- Final accept-deploy call was declined: tool returned "Cancelled — the user did not approve this action. No changes were made." No workaround attempted. Staged changes have not been committed or tested remotely. User approval/application is required to continue deployment.

## Railway live verification — October 19, 2026

- User applied the staged deployment in Railway and requested final verification.
- All five services report SUCCESS: PostgreSQL, Conductor, FastAPI, official SDK workers and Next.js dashboard. No source fixes or plan upgrades were needed.
- Working public URL: https://web-production-95d5e.up.railway.app . This runs independently of the Mac and the Cloudflare Quick Tunnel.
- Verified public HTTPS 200, unauthenticated API 401, existing-token login, Secure/HttpOnly cookie and authenticated workflow definitions.
- Both Playwright tests passed against Railway (12.6 seconds), covering login, real fail-once diagnostic execution/retry, deterministic task output, definitions/DAG, four actual worker poll observations and mobile layout. Verified workflow `e0cd86c0-7121-4223-9db4-70767cafc0a1` COMPLETED on Railway.
- Screenshots refreshed from the Railway browser run. Gemini remains disabled; no AI provider request or paid plan upgrade occurred. Hosting consumes the account's trial credit and is not permanently free.
- Added docs/RAILWAY.md for operation, security, source pinning and credit/retention limits. Earlier tunnel-only and staged-deployment blockers above are historical and superseded by this successful deployment.

## Agent engineering harness — October 20, 2026

- Added project-scoped OpenCode definitions; no application code, dependencies or runtime configuration changed.
- `.opencode/skills/workflow-safety/SKILL.md` and `.opencode/skills/enterprise-security/SKILL.md` encode the Conductor/retry/billing rules and the authentication/tenant/secrets rules already implemented in `backend/app/` and `frontend/app/api/`.
- `.opencode/commands/verify.md` and `.opencode/commands/review.md` add `/verify` (pytest, typecheck, production build, gated local Playwright) and `/review` (diff review over regressions, contracts, security, tests, scope).
- `docs/ARCHITECTURE.md` documents the Compose topology, request path, workflow/task contracts, trust boundaries and configuration as implemented. It records that the system is single-tenant with one shared token and that `storage` health is not independently probed.
- Discoverability verified through the local OpenCode 2.1.1 API: `/api/skill` lists 42 skills including `workflow-safety` and `enterprise-security`; `/api/command` lists `verify` and the project `review` command replacing the built-in one.
- Not executed in this change: no deployment, no Railway mutation, no Gemini/provider call, no destructive recovery test.

## Personal developer control plane — October 20, 2026

- Added an application-owned PostgreSQL database (`orchestra`) with SQL migrations in `backend/app/migrations/`, created on API startup and kept out of Conductor's schema. New tables: clusters, projects, environments, services, deployments, connectors, observations, incidents, incident_events, alerts, notifications, audit_log, sessions, app_settings.
- Implemented project/environment/service/cluster/deployment CRUD, dashboard aggregates, observation history and audit logging through authenticated APIs. Every list and mutation is exercised by tests.
- Implemented a real monitoring collector inside the API process: advisory-lock single-runner, per-service intervals and timeouts, SSRF-guarded HTTPS checks with no redirects, failure/recovery thresholds, bounded history and retention pruning. Verified against the running stack: a service with a 15 s interval produced two observations with no manual check and no browser session.
- `unknown` outcomes (blocked target, DNS failure) never change service status and never open incidents; a test covers this distinction.
- Implemented incidents with a partial unique index preventing duplicates, append-only event trail, acknowledgment, notes, manual resolution and automatic resolution on recovery.
- Implemented webhook alerts with severity filters, cooldowns, per-delivery records and SSRF validation of targets.
- Implemented connectors: Railway GraphQL inventory, GitHub REST (repository, commits, workflow runs → deployments) and an agent ingest endpoint for local Docker. Credentials are AES-GCM sealed at rest and never returned by the API; rotation and redaction are tested.
- Replaced the browser-held shared token with an opaque server-side session (`cp_session`, HTTP-only, SameSite=strict) exchanged from the owner password or the master API token. Sessions are revocable, expire, and are pruned. Login attempts are rate-limited.
- Extended the Conductor surface with an engine-wide definition catalog and a read-only schedule view. `PROGRESS` records engine 3.33.0-rc13; schedules returned an empty list, so no schedule was created or claimed.
- Rebuilt the frontend around a shared shell: Overview, Projects (list/new/detail), Clusters, Services, Deployments, Executions, Workflows, Incidents (list/detail), Integrations and Settings. Existing execution/workflow/infrastructure panels are reused inside the shell rather than rewritten.

### Verified in this milestone (local Compose only)

- `docker compose run --rm --no-deps -v backend:/app api python -m pytest tests -q` → **29 passed** (1 pre-existing Starlette deprecation warning). Includes the deterministic end-to-end cycle: register project → register service → healthy → failing check → incident with evidence → recovery → automatic resolution, plus SSRF, secret sealing, credential redaction, alert dedupe/cooldown, connector rotation and validation failure, migration idempotency, login rate limiting and agent authentication.
- `npm --prefix frontend run typecheck` → clean; `npm --prefix frontend run build` → compiled, 17 routes.
- `npm --prefix frontend run test:e2e` → **3 passed in 10.0 s** against the live stack: unauthenticated API/origin rejection; project registration, real check, incident and recovery through the UI; real Conductor fail-once execution, task inspection, definitions and worker polls; mobile layout without horizontal overflow.
- `scripts/smoke.py` → PASS for success, fail-once retry, retry exhaustion, manual retry, termination and search filtering against the real engine.
- `/api/infrastructure` → storage `connected` (1 ms probe), engine `connected` (3 ms), four workers `polling`.
- Screenshots `overview.png`, `project.png`, `incident.png`, `execution.png`, `infrastructure.png`, `mobile.png` were regenerated by those browser runs, not from fixtures.

### Not verified — do not treat as complete

- Railway connector: inventory query implemented, but no Railway token was available, so validation, pagination and inventory mapping are unverified. Railway exposes no per-service health through that query, so provider health is not mapped to service status.
- GitHub connector sync was not executed against api.github.com with a token; only the adapter code and its error/rate-limit paths exist.
- `scripts/docker_agent.py` was not run end-to-end; the ingest endpoint it calls is covered by a test using a simulated agent token.
- Gemini remains disabled and unverified; no paid request was made.
- No deployment, Railway resource change, remote push or destructive recovery test was performed.

## Orkes-parity engine profile, telemetry and free hosting — October 20, 2026

- Reworked `infra/conductor.properties` to the Orkes *Production Deployment* "PostgreSQL stack (simplest)": Postgres for db/queue/external payload/indexing, **Valkey 8.1 for the execution lock**, sweeper (8 threads, 2 s poll, batch 2), system task workers (20 threads / 20 polls), and explicit payload thresholds (5 MB spill / 10 MB hard limit per workflow, 3 MB / 10 MB per task, 256 KB variables).
- Added a `valkey` service; Conductor now waits for its health before starting. Verified: engine healthy in 10 s and the full real-engine smoke suite passed with the Redis lock active.
- Disabled the Elasticsearch health indicator (`management.health.elasticsearch.enabled=false`). Before this, `/actuator/health` reported **DOWN** while the engine was healthy, because indexing is PostgreSQL-native. After a restart it reports **UP** with db/disk/ping/ssl components.
- Added `telemetry.py`: parses Conductor's Micrometer output at `/actuator/prometheus`, sums workflow failure counters by status, successful starts, in-flight tasks, mean task execution, mean queue wait, JVM heap and uptime; adds per-task queue depth from `GET /api/tasks/queue/size`. Exposed as `/api/infrastructure` → `engine.telemetry`, rendered in a new "Engine telemetry" panel on the Workflows page. Missing series render as `—`, never zero.
- Verified live telemetry after a smoke run: `workflow_failures {FAILED: 2, TERMINATED: 1}`, 4 successful starts, mean task execution 29.0 ms, mean queue wait 1078.7 ms, heap 205/1024 MB, per-queue depths 0, poll counters per managed task.
- Added Conductor **task domains**: `TASK_DOMAIN` starts executions with `taskToDomain: {"*": "<domain>, NO_DOMAIN"}` (documented fallback) and `WORKER_DOMAIN` binds a fleet to a domain via the SDK's `domain=` parameter. Verified by running the smoke suite with `TASK_DOMAIN=production` and no domain-specific fleet: every workflow completed through the `NO_DOMAIN` fallback.
- Added the free-VM deployment kit: `compose.prod.yaml` (memory limits, log rotation, Caddy behind a `public` profile), `Caddyfile`, `scripts/deploy_wizard.sh` (7 guided stages), `scripts/backup.sh` and `scripts/restore.sh`, plus `docs/DEPLOY_FREE.md` with the licence/cost table and Oracle caveats.
- Verified backup and restore locally: both databases dumped (56 KB conductor, 16 KB orchestra), `gzip -t` passed, restore into `orchestra_restore` produced 1 project, 2 services and 1 migration row, then the drill database was dropped. No live data was touched.
- Fixed a real responsive defect the new panels exposed: a wide table widened the page to 412 px at a 390 px viewport. `.content` now clips horizontal overflow so wide tables scroll inside `.table-scroll` instead of moving the page. The mobile Playwright assertion passes again, and `docs/screenshots/workflows.png` now captures the catalog plus engine telemetry.

- Added controlled workflow-definition registration (`POST /api/workflows/definitions` + a validated editor on the Workflows page). Validation accepts only worker-backed `SIMPLE` tasks, rejects `HTTP`/`EVENT`/`SUB_WORKFLOW`, enforces unique reference names, bounds versions and inputs, and refuses to overwrite an existing name+version. Verified against the real engine: `manual_recheck` v1 registered, appeared in the catalog, a duplicate returned 409, and an `HTTP` task was rejected with 422.

### Decisions recorded

- Railway is retained only as an existing demonstration; the documented target is one free VM (Oracle Always Free A1: 2 OCPU / 12 GB / 200 GB, verified against Oracle's current Always Free page). Tailscale (free) or Caddy + DuckDNS provide access without buying a domain. Render/Fly no longer offer a usable free always-on tier.
- All new runtime components are open source: Valkey (BSD-3), Caddy (Apache 2.0), PostgreSQL, Conductor OSS. Tailscale and DuckDNS are free services, not open source; Headscale is documented as the self-hosted alternative.

### Still unverified

- No VM has been provisioned, so `compose.prod.yaml`, Caddy TLS and the wizard's remote steps are **untested against a real host**. They are configuration and instructions, not verified deployments.
- Railway still runs the old pinned commit and was not touched.
- Gemini remains disabled and unverified. No paid API call was made.

## Sunflower project lifecycle — October 20, 2026

### Implemented

- Added additive project-lifecycle persistence, scoped hashed runner credentials, owner work requests and exact-commit review/publication approval. `project_change` v1 runs on Conductor with a strict runner task domain and zero automatic coding retries; incident workflow versions are preserved.
- Added an outbound macOS OpenCode runner using the official Conductor Python SDK through a narrow authenticated gateway. It uses separate worktrees, isolated agent/test environments, a process lock and SQLite journal. Ambiguous starts and orphaned sessions require reconciliation rather than launching another paid session. Credential/configuration files cannot be automatically committed. Bounded redacted progress, diff, session and test evidence are separate from local raw transcripts.
- Added Work, Changes, Releases and Health views, explicit runner pairing/revocation and approval/rejection, plus expected-release verification against every service's version and readiness evidence. Missing versions, mismatches and failing checks remain unverified. The runner does not deploy or migrate production data.
- GitHub Actions records are retained and classified as CI evidence; deployment history/project deployment timestamps exclude them. CI status refreshes update the same evidence record.
- Imported Sunflower into the **local** application database with three real HTTP-monitored services. Your fork is recorded separately from the teammate's deployed source. D1/Gemini/n8n remain unknown without dependency evidence. The existing unauthenticated Sunflower administrative API is recorded as a blocker for real family data.
- Prepared the companion Sunflower changes in `/private/tmp/orchestra-sunflower` and saved the reproducible patch under `integrations/sunflower/readiness-release-ci.patch`: bounded read-only D1 readiness, version evidence for all three apps, CI, pinned Wrangler 4.86.0 and a local-only D1 migration/query check. No pre-existing engine dependency version was changed. Dirty frontend builds report a null SHA unless explicitly configured.

### Executed verification

- Backend suite with the opt-in local Conductor contract test: **48 passed**, with the existing Starlette/httpx deprecation warning. Includes real correlation-ID start reconciliation, strict-domain task polling, task completion and cancellation, plus authorization, token revocation, approval invalidation/rejection, CI separation and release mismatch/readiness scenarios.
- Official Conductor SDK over the real local HTTP gateway: polling and task completion passed with a deterministic synthetic result; no model was invoked.
- Native runner suite: **7 passed** (portable container run: **6 passed, 1 intentionally skipped**), including a real isolated worktree/process/commit and offline-check fixture using a deterministic fake agent, duplicate-delivery prevention, lost-completion acknowledgment, cancellation-before-launch, credential redaction and the SDK URL regression guard.
- Orchestra frontend typecheck passed. Native production build and local Docker production build passed. A failed sandbox build cache had to be moved aside before the native build succeeded; no source workaround was needed.
- Full local Playwright suite: **4 passed**. Includes project creation, runner pairing, unapproved-model rejection, release uncertainty, existing real incident/recovery and real Conductor fail-once/task inspection, plus mobile layout.
- Existing local deterministic engine smoke passed: success, fail-once retry, exhaustion, manual retry, termination and status-filtered search.
- Sunflower engine typecheck and **436 tests passed**; isolated local D1 migrations and readiness SQL passed. Both frontend typechecks and production builds passed, including generated version artifacts. No live eval/smoke script calling Gemini was run.
- OpenCode 2.1.1 standalone startup/configuration reached the expected nonexistent-provider error using isolated storage, no credentials and an intentionally invalid provider. This validates startup/config parsing, not a real model session.
- Actual local Sunflower desktop/mobile screenshots saved separately; mobile page had no horizontal overflow. Existing historical screenshots were preserved.

### Remaining acceptance steps and limits

- No successful live DeepSeek coding session was attempted. A real session still requires explicit provider-use approval and credentials, and is not implied by the deterministic runner fixture.
- No push, PR creation, merge, Cloudflare/Railway change, remote migration, paid provider request or destructive recovery drill was performed. GitHub publication and teammate deployment remain unverified.
- The Sunflower patch is local and unpublished. Its readiness/version endpoints are not claimed to exist on the teammate's current deployment. The running URLs are only monitored with read-only HTTP GETs.
- The runner currently supports macOS only and requires trusted local check configuration. Its containment is not a general-purpose hostile-code sandbox.
- Application authentication for Sunflower is still outstanding. Orchestra does not ingest family conversations or assume its own login protects the managed application.


## Stabilization and general project management — October 20, 2026

### Implemented

- Unified Runs, Automations and Infrastructure under shared navigation. Run/project tabs, filters and selected execution use URL state. Run history and totals share ownership checks; durable execution associations survive project deletion. Verification records are labelled while preserving engine history.
- Added generic repository/environment/service onboarding, editable services and observation history, separate readiness diagnostics, monitoring without a coding runner, and editable work drafts. Disabled, stale, unknown and last-known health are distinct across lists and totals.
- Added project-scoped GitHub connections with public reads, CI/PR evidence and visible failures; read-only Railway account inventory/local linking with explicit unsupported project-token scope; Docker mapping/stopped-container detection; webhook delivery inspection. Deployment records remain distinct from verified releases.
- Added in-app laptop instructions and fresh preflight checks, project-profile companion supervision, bounded coding sessions, readable changes/check evidence and explicit follow-up attempts. Publication is a separate zero-retry Conductor task on the paired runner, requested from the website after exact-evidence approval. Ambiguous starts/publication require reconciliation; duplicate delivery cannot silently repeat a model session or write.
- Completed inspection and validated execution for permitted registered workflow definitions; coding/publication retain dedicated approval flows. Original workflow versions and task restrictions remain intact.
- Fixed proxy PUT/notification routing and empty 204 responses, client filtering that hid server search results, mobile run-name overflow, nested-shell padding and action-message handling. Wide tables scroll within their containers; global overflow clipping was removed.

### Executed verification

- Full backend suite against local PostgreSQL and Conductor: **61 passed**, with one existing Starlette/httpx deprecation warning. Includes access/history, freshness, drafts, approval redelivery, preflight reservation, publication correlation recovery/association, a local webhook receiver, local outage/recovery and matched/mismatched/unavailable release evidence.
- Native runner/companion suite: **16 passed**, including an actual isolated Git worktree and fake-agent process, sandbox checks, duplicate delivery, lost acknowledgment, cancellation/disconnection, preparation failure, publication reconciliation and separate project credentials. These fixtures do not call a model or publish to GitHub.
- Frontend TypeScript check and Docker production build passed. Local Conductor smoke passed for success, fail-once retries, exhausted retries, manual retry, termination and filtered search.
- Full local Playwright suite: **12 passed**. Covers generic onboarding of two projects, editable services/drafts, URL navigation, session expiry, safe automation execution on Conductor, scoped connection setup/error messages, publication task failure without remote writes, truthful run search and actual control bounds at **390, 650, 1024 and 1440 pixels**. These are focused regression flows, not proof of every possible provider/error combination.
- Installed OpenCode help succeeded inside the real macOS sandbox with isolated configuration and no provider credentials; required standalone/JSON/model flags were present. This verifies CLI compatibility, not successful model use.

### Remaining acceptance gates and operational limits

- A documentation-only Sunflower acceptance draft is saved but unapproved. The real DeepSeek → checks → review → draft-PR acceptance cycle still requires laptop provider/GitHub setup, explicit model-use approval with a usage limit, then separate exact-commit publication approval. No paid call, push, PR publication, deployment, provider-resource mutation or remote database operation was performed.
- Live Railway credential discovery, provider permission/rate limits, real GitHub publication and teammate deployment are not established by mocked/local regression tests. The runner remains macOS-only; configured local check commands must be trusted. A runtime limit is not a monetary billing cap.
- Engine history scans paginated engine results to apply consistent ownership/filtering before counts; scale evaluation and indexing remain future work. No new scheduler or execution database replaced Conductor.
- Sunflower's application authentication gap remains a release blocker before real family data. Its companion patch and historical test results above were not redeployed or rerun as part of stabilization.
