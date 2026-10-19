# Deployment preparation

The supported and locally verified target is a private, single-host Docker Compose deployment. The `conductor-control-plane` project name scopes its containers and persistent PostgreSQL volume. Start with `python3 scripts/setup_env.py` and `docker compose up -d --build --wait --wait-timeout 180`.

## Before hosting

1. Provision a Docker host and persistent disk; retain the PostgreSQL volume across releases. Do not use `down -v` unless intentional data deletion is authorized.
2. Generate new host-specific secrets. Keep `.env` readable only by the deployment operator. Inject provider credentials from your secret manager for a managed environment.
3. Keep engine, database and API private. Put a TLS reverse proxy in front of the web service. Set `APP_ORIGINS` on the web service to the exact external HTTPS origin (comma-separated if needed). Never use a wildcard.
4. Configure `COOKIE_SECURE=true` on the web service behind a TLS-terminating reverse proxy. Direct localhost development uses non-secure cookies. Add upstream identity/rate controls and replace the shared-token model before multi-user use.
5. Approve Gemini data handling/model/costs before setting `ENABLE_GEMINI=true`. The provider model can be changed through `GEMINI_MODEL`.
6. Run deterministic smoke and browser tests. Run crash-recovery checks only in a dedicated staging environment. Make a separate authorized live Gemini call to verify your provider account.
7. Back up PostgreSQL and verify restore on a separate database. Set your retention, capacity, TLS, monitoring and incident-response policies before production use.

## Rollout and rollback

- Back up the database before Conductor version changes. The pinned engine digest is the tested artifact; inspect upstream migration notes before changing it.
- Build images from a recorded commit. On a new host, run `docker compose up -d --build --wait --wait-timeout 180` and verify `docker compose ps`.
- Application containers run as non-root users. Engine/database images use their vendor defaults. This MVP does not implement HA or horizontal gateway/worker management.
- Roll back application images to a previous commit, preserving the database volume. Database schema migrations may require restoring a backup; do not assume that a binary downgrade is safe.
- `docker compose down` stops the project while retaining data. No public deployment is implied by the local setup.

## Verification status

All five services build/start locally; deterministic real-engine and browser tests pass. Recovery checks and their exact results are recorded in PROGRESS.md. The remote CI workflow is prepared but has not run on GitHub. A live Gemini request failed with ClientError and needs valid provider access/configuration before the AI portion can be called verified.
