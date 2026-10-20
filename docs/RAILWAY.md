# Railway trial deployment

The maintainer's original Railway trial deployment is described here as a reference. It is not a supported hosted instance: Railway trials expire, and this configuration is superseded by the free-VM profile in `docs/DEPLOY_FREE.md`.

Substitute your own project ID and domain when following along; the identifiers from the maintainer's account are not reproduced here.

The dashboard, API, official SDK workers, real Conductor engine and PostgreSQL run on Railway, independently of the local Mac. Check docs/PROGRESS.md for the latest verification status.

Sign in with the existing `CONTROL_PLANE_TOKEN` from the local ignored `.env`. The token is configured as a server-side secret; do not publish it. Gemini is disabled and no Gemini key was uploaded. The diagnostic workflow works without AI API charges; AI incident analysis is not enabled.

Only the dashboard has a public domain. API, Conductor and PostgreSQL communicate over Railway's private network. PostgreSQL has a 500 MB persistent volume. Conductor uses a 512 MB JVM heap within a 1 GB memory cap. Services are pinned to source commit `1c0ce19`; future GitHub pushes do not automatically update this deployment.

## No-charge boundary

The account displayed a new-user trial with $5 credit and up to 30 days on October 19, 2026. This uses trial credits; it is not unlimited free hosting. Duration depends on actual compute, storage and network usage, and cannot be guaranteed. No paid subscription was selected. Keep the account on its free/trial plan, do not add a payment method or upgrade, and check Railway's Usage page for remaining credit. Service availability ends when the account's free resources no longer cover it. Trial volumes are subject to Railway's retention policy; export needed data before expiry.

The Mac and Docker Desktop are not required for this Railway deployment. The older Cloudflare URLs are separate local demos and may expire. Stopping the local stack does not stop Railway services.

Official trial policy: https://docs.railway.com/pricing/free-trial

## Prepared upgrade to the control-plane release — NOT APPLIED

The running deployment is still pinned to commit `1c0ce19`. Nothing below has been executed, and no Railway resource was modified. This is the change set to review before applying.

### Why the upgrade is not a plain redeploy

The current release only needs Conductor plus a shared token. The new release adds an application-owned database, an owner login and connector encryption, so the API service needs new secrets, and the monitoring collector now runs inside the API process (no new service, no extra compute).

### Required API service variables

| Variable | Value | Notes |
| --- | --- | --- |
| `OWNER_PASSWORD` | generated strong password | Stored only as a scrypt hash after first boot |
| `SECRET_KEY` | generated random string | Encrypts connector credentials; rotating it invalidates stored connector tokens |
| `DATABASE_HOST` | Railway PostgreSQL private host | Or set one `DATABASE_URL` instead |
| `DATABASE_PORT` | `5432` | |
| `DATABASE_USER` / `DATABASE_PASSWORD` | Railway PostgreSQL credentials | Same instance as Conductor |
| `DATABASE_NAME` | `orchestra` | Must be created before the API starts, see below |
| `COOKIE_SECURE` | `true` | Already correct for the public HTTPS domain |
| `ENABLE_GEMINI` | `false` | Unchanged |
| `HTTP_CHECK_ALLOW_PRIVATE` | `false` | Railway-hosted checks must not reach private networks |

### Creating the application database

The API calls `CREATE DATABASE orchestra` on first start and exits if it cannot. Railway's PostgreSQL role may not have `CREATEDB`, so the safer sequence is to create it once from the Railway PostgreSQL console/`psql`:

```sql
CREATE DATABASE orchestra;
```

If `CREATEDB` is refused, the alternative is to point `DATABASE_NAME` at a database you create through Railway's database UI. Do **not** place the platform tables in Conductor's `conductor` database: the migration would mix platform and engine schemas, and the isolation guarantee documented in `docs/ARCHITECTURE.md` would be lost.

### Apply order (when approved)

1. Confirm trial credit and that no paid plan or payment method is attached.
2. Add the API variables above as service (not shared) variables; keep `CONTROL_PLANE_TOKEN` unchanged.
3. Create the `orchestra` database.
4. Repoint the API and workers services to the new release commit, keeping `GEMINI*` unset.
5. Redeploy the API first and watch its logs for `monitoring collector started` and no migration error.
6. Redeploy the web service, then workers.
7. Verify: public HTTPS 200, unauthenticated `/api/projects` 401, owner-password login, `/api/infrastructure` reporting storage `connected`, four workers `polling`, and one real `diagnostic_pipeline` execution completing.
8. Run the Playwright suite against the Railway URL, not against local Compose.

### Rollback

Repoint all services to `1c0ce19`. The new `orchestra` database is additive and ignored by the old release, so no data migration has to be undone. The old release does not read `OWNER_PASSWORD` or `SECRET_KEY`.

### Unverified on Railway

Provider connectivity (Railway/GitHub tokens), the 1 GB Conductor memory cap under the new API process, and the behaviour of the collector when the API restarts. These need to be observed after the first deploy; they are not claimed as working.
