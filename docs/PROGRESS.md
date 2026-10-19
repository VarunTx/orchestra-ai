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

No hosting account/remote is configured, no public deployment was performed, and GitHub Actions has not run remotely. The locally built Compose deployment is the verified deployment target. Production security/backup/HA requirements and feature scope are documented in README.md and DEPLOYMENT.md.

## Checkpoints

- `c676a0f`: initial full implementation and deterministic execution verification.
- Final verification/docs/fixes checkpoint follows this report; consult `git log` for its hash.
