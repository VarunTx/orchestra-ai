# Railway trial deployment

Project: https://railway.com/project/68e2641a-a387-4bcf-9307-e25eadebe42f

Dashboard URL: https://web-production-95d5e.up.railway.app

The dashboard, API, official SDK workers, real Conductor engine and PostgreSQL run on Railway, independently of the local Mac. Check docs/PROGRESS.md for the latest verification status.

Sign in with the existing `CONTROL_PLANE_TOKEN` from the local ignored `.env`. The token is configured as a server-side secret; do not publish it. Gemini is disabled and no Gemini key was uploaded. The diagnostic workflow works without AI API charges; AI incident analysis is not enabled.

Only the dashboard has a public domain. API, Conductor and PostgreSQL communicate over Railway's private network. PostgreSQL has a 500 MB persistent volume. Conductor uses a 512 MB JVM heap within a 1 GB memory cap. Services are pinned to source commit `1c0ce19`; future GitHub pushes do not automatically update this deployment.

## No-charge boundary

The account displayed a new-user trial with $5 credit and up to 30 days on October 19, 2026. This uses trial credits; it is not unlimited free hosting. Duration depends on actual compute, storage and network usage, and cannot be guaranteed. No paid subscription was selected. Keep the account on its free/trial plan, do not add a payment method or upgrade, and check Railway's Usage page for remaining credit. Service availability ends when the account's free resources no longer cover it. Trial volumes are subject to Railway's retention policy; export needed data before expiry.

The Mac and Docker Desktop are not required for this Railway deployment. The older Cloudflare URLs are separate local demos and may expire. Stopping the local stack does not stop Railway services.

Official trial policy: https://docs.railway.com/pricing/free-trial
