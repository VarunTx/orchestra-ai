# Session handoff

**Read this first, then `AGENTS.md`.** Everything below was true at the end of the session on 2026-10-21.

- Branch `main`, HEAD `ca23a39`, clean and pushed to `https://github.com/VarunTx/orchestra-ai` (public, MIT).
- Local stack running (`docker compose ps`): api, web, workers, conductor, postgres, redis.
- Dashboard: `http://localhost:3000` — sign in with `OWNER_PASSWORD` from the repo's ignored `.env`.

Do not repeat the discovery work. The authoritative records are:

| Question | File |
| --- | --- |
| What has been built and verified, with dates | `docs/PROGRESS.md` (read the last three sections) |
| How the system works | `docs/ARCHITECTURE.md` |
| Lifecycle/runner behaviour and limits | `docs/PROJECT_LIFECYCLE.md` |
| Free-VM deployment | `docs/DEPLOY_FREE.md` |
| Product intent and guardrails | `AGENTS.md`, `README.md` |

## What this product is

A single-owner developer operations console for someone who ships many small AI-built projects: project/service inventory, real HTTP monitoring, incidents with evidence, webhook alerts, Conductor execution operations with engine telemetry, and an **optional, off-by-default** local coding runner. Conductor OSS remains the only orchestration engine.

## Decisions locked in this session (do not relitigate)

1. **Direction: a personal operations console** (chosen by the owner), not a developer-agent workspace. The coding runner stays, but only as an optional extra.
2. **AI runner is off by default.** It requires pairing, `--allow-model-calls`, and `DEEPSEEK_API_KEY` on the runner. No live model call has ever been made. Keep it that way unless the owner explicitly approves spend.
3. **Maintainer-specific companion project removed** from the repo (importer route, UI action, patch, screenshots, docs). The originals are at `/private/tmp/orchestra-sunflower-artifacts`. Do not re-add project-specific data.
4. **Free, open-source stack.** Vercel/Supabase are intentionally not used; the target is one free VM (Oracle Always Free A1) or local Docker. See `docs/DEPLOY_FREE.md`.

## Verified state

- Backend: `61 passed, 1 skipped` — run `make test-db` (or `docker compose run --rm --no-deps -v "$PWD/backend:/app" api python -m pytest tests -q`). The skip is an opt-in real-engine test: `ORCHESTRA_ENGINE_TEST=true`.
- Frontend: `npm --prefix frontend run typecheck` clean; `npm --prefix frontend run build` compiles.
- Browser: `npm --prefix frontend run test:e2e` → 12 passed at 390/650/1024/1440 px.
- Engine: `python scripts/smoke.py` → 6 scenarios pass against the real local Conductor.
- Runner/companion fixtures: `python -m pytest scripts/tests -q` → 15 passed, 1 skipped (no model calls).

Re-run these before claiming anything is still true.

## Gotchas that cost time

- **iCloud conflict copies.** The repo lives in `~/Documents` (iCloud-synced), which creates files like `0002_x 2.sql`. A duplicate once put the API in a restart loop. The loader now only accepts `NNNN_name.sql`, and `* 2.*` is git- and docker-ignored. If the API restart-loops, run `find . -name "* 2.*" -not -path "./.git/*" -delete`.
- **`COOKIE_SECURE=false` locally.** With `true`, login silently fails on `http://localhost`. Hosted deployments must set `true`.
- **Migrations are append-only** in `backend/app/migrations/`. Do not edit an applied file; add the next number.
- **Engine metrics live at `/actuator/prometheus`** (not `/prometheus`, which is an HTML page).
- **`TASK_DOMAIN=production`** is set in the local `.env`; executions start with `"production, NO_DOMAIN"` fallback, so they complete on the default fleet. `WORKER_DOMAIN` is unset.
- **Docker rebuild needed** after backend changes: `docker compose up -d --build api`; after frontend: `... --build web`.
- Do not run `docker compose down -v` (deletes the data volume) or `scripts/recovery.py` against anything shared.

## Next work, in the owner's chosen order

### 1. Automatic diagnostics on incidents
When a check opens an incident, start the existing `diagnostic_pipeline` Conductor workflow with the incident evidence, store the workflow id on the incident, and render its report in the incident detail view. Must not duplicate on redelivery, must not run when Conductor is unavailable (mark `unknown`, do not invent a cause), and must never send incident logs to an LLM (Gemini stays off).
Acceptance: integration test that a failing check produces exactly one diagnostic execution; UI shows the report; a second failure does not start a second run.

### 2. Seven-day reliability per project
Availability %, incident count, and mean time to recovery over a rolling 7 days, computed from `observations` and `incidents` (no fabricated numbers; show `—` when history is thin). Surface on the project page and in the Overview attention list.
Acceptance: test with seeded observations/incidents asserting the arithmetic; empty history renders as unavailable.

### 3. Phone alerts
Add Slack/Discord/Telegram formatting on top of the existing webhook alert engine, keeping cooldowns and delivery records. Explicit configuration only.

Anything else in the original roadmap is lower priority. Do not start the coding runner's live-model path without approval.

## Suggested skills for the next session

Call the Skill tool for: `workflow-safety` (before touching Conductor definitions/retries), `enterprise-security` (any route, credential or log change), `tdd` (for the two features above), `code-review` (before committing), `diagnosing-bugs` (if the stack misbehaves).

## Agent rules that stay in force

`AGENTS.md` is authoritative: Conductor is the only engine, never fabricate metrics, no secrets in tracked files, no deployment or paid calls without explicit approval, and update `docs/PROGRESS.md` only with results you actually observed.
