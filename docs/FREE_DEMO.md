# Free public demo

**Superseded:** The verified independent cloud deployment is now https://web-production-95d5e.up.railway.app . See [RAILWAY.md](RAILWAY.md). The instructions below describe the older Mac-hosted demo only.

Orchestra AI can be shared through an accountless Cloudflare Quick Tunnel. The application, Conductor, Python workers and PostgreSQL run in Docker on this Mac; Cloudflare provides the temporary public HTTPS URL. This is a demo, not independent cloud hosting. There is no cloud hosting subscription or billable AI call in this configuration. The Mac's electricity and Internet connection are still used.

Keep the Mac awake and Docker running. The URL is temporary, has no uptime guarantee and changes when a new tunnel is created. Local PostgreSQL data remains in the existing Docker volume. Only the dashboard is exposed through the tunnel; management calls require the workspace token.

## Current session

URL: https://harvest-transmit-jelsoft-trades.trycloudflare.com

Sign in using `CONTROL_PLANE_TOKEN` from the local ignored `.env` file. Never commit or share that file. `COOKIE_SECURE=true`; `APP_ORIGINS` includes exactly this HTTPS origin and the local development origins. `ENABLE_GEMINI=false`, so use the diagnostic workflow for non-AI executions. AI incident analysis remains unavailable until separately authorized and verified.

Stop public access with:

```sh
docker stop orchestra-ai-tunnel
```

## Start a new tunnel

Remove the stopped tunnel container (this contains no application/database data), then run:

```sh
docker rm orchestra-ai-tunnel
docker compose up -d
docker run -d --name orchestra-ai-tunnel cloudflare/cloudflared@sha256:a15a3b50b8dabd57ac2090e9484c0247dba9dfa1f0df4d298d4317f9d69eb2d5 tunnel --no-autoupdate --url http://host.docker.internal:3000
docker logs orchestra-ai-tunnel
```

In `.env`, replace the old public URL in `APP_ORIGINS` with the new exact HTTPS URL from the logs, keep `COOKIE_SECURE=true` and `ENABLE_GEMINI=false`, then run `docker compose up -d web`. Do not use a wildcard origin. The host address above is for Docker Desktop on macOS.

## Hosting status and cost boundary

Do not apply `render.yaml` under the zero-cost requirement: it explicitly provisions paid resources. Render's private services and workers have no free plan; free PostgreSQL expires after 30 days, and free web services can incur bandwidth/build overages on accounts with payment methods. No Render resources were created by this task.

Independent cloud hosting remains unfinished. A suitable free provider account and sufficient compute/storage capacity would be needed to move the complete real-engine stack off this Mac. No new provider account or paid plan was created.

References: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/ and https://render.com/docs/free
