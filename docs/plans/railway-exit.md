# Leaving Railway

Status: proposed on 2026-11-04. Nothing here has been executed.

## Decision

Run Orchestra AI on the Mac with Docker Compose, and delete the Railway project.

The local stack is already running. Measured idle memory is about 1.4 GB across six containers, and the local database holds more real history than a demo needs (5 projects, 14,447 observations, 290 incidents, 132 workflows).

You lose three things:

| Lost | Effect | If you want it back |
| --- | --- | --- |
| Always-on health checks | The collector runs inside the API, so checks pause while the Mac sleeps. Stale services already render as stale. | Oracle VM |
| Public dashboard URL | Nobody else can open it | Tailscale for your own devices, or the Oracle VM with Caddy |
| Hosted MCP endpoint | Remote clients cannot reach it. Local clients still work. | Same as above |

## Alternatives

| Option | Cost | Use it when | Limits |
| --- | --- | --- | --- |
| **Mac + Compose** | $0 | Now. This is a personal project. | Stops when the Mac sleeps |
| Tailscale added to the Mac | $0 on the free plan | You want it from your phone | Proprietary service. Headscale is the self-hosted option. |
| Oracle Always Free A1 | $0 | You later want it always on | 2 OCPU / 12 GB per Oracle's page. Capacity is not guaranteed, and idle instances may be reclaimed. `compose.prod.yaml` has never run on a real VM. |
| Old laptop or Raspberry Pi with 4 GB+ | Hardware you own | You have one spare | You maintain it |
| Hetzner CAX11 | About €6/month per secondary sources | You accept a small fixed bill | Not free |

Do not go back to Cloudflare Quick Tunnels. The `orchestra-ai-tunnel` container is still running and its log shows `Unauthorized: Tunnel not found`. It exposes nothing, but it should be removed.

The current images run as `linux/arm64`, so an Oracle A1 move needs no architecture change.

## What stays

Keep `RailwayConnector` and the `railway` provider value. They are a feature that lets Orchestra inventory someone's Railway account, not a dependency on hosting. Removing them would mean a migration on a `CHECK` constraint and changes to the API and frontend contracts, for no saving.

## Order of work

1. Run the DeepSeek prompt below, then review the diff.
2. Confirm the local MCP service works from your clients.
3. Do the manual cutover. It is irreversible, so it stays in your hands.

## DeepSeek prompt

Paste this into OpenCode.

```text
Task: make the local Docker Compose stack the default Orchestra AI deployment and remove hosted Railway URLs from client configuration and current docs. Do not touch Railway itself.

Read first: AGENTS.md, docs/PROGRESS.md, docs/MCP.md, docs/DEPLOY_FREE.md, docs/RAILWAY.md, docs/ARCHITECTURE.md, compose.yaml, compose.prod.yaml, Dockerfile.mcp, scripts/run_mcp.sh, .mcp.json, .codex/config.toml, opencode.json. Run `git status` before changing anything.

Hard limits:
- Do not run any `railway` command. Do not deploy, push or commit.
- Do not read aloud, print, log or copy the value of any secret. You may list the KEY NAMES in .env.mcp-local with: cut -d= -f1 .env.mcp-local
- Do not edit .env, .env.mcp-local, .env.mcp-hosted or .env.railway-prod. If a new variable is needed, add it to .env.example and tell me.
- Do not remove RailwayConnector, the `railway` provider value, its migration, its tests or its UI option.
- Do not rewrite historical entries in docs/PROGRESS.md. Only append.

Changes:
1. compose.yaml: add an `mcp` service built from Dockerfile.mcp.
   - Publish only 127.0.0.1:8765:8765.
   - Set CONTROL_PLANE_URL to http://api:8000 and MCP_ALLOWED_HOSTS to localhost and 127.0.0.1 in the form the SDK expects. Check how mcp_server.py compares Host values, including whether the port is part of them.
   - Load credentials from .env.mcp-local. The service must hold an operate-scoped token, never the master token. If the file lacks the key the service needs, stop and report which key name is missing.
   - depends_on api healthy, restart: unless-stopped, and a healthcheck that uses /healthz.
   - It must start under the existing `make up`. If .env.mcp-local being absent would break `make up` for a fresh clone or CI, use a Compose profile named `mcp` instead, and document that choice. Check .github/workflows/ci.yml and scripts/setup_env.py to decide.
2. .mcp.json: change the default URL to http://127.0.0.1:8765/mcp and keep the ${ORCHESTRA_MCP_URL:-...} form.
3. .codex/config.toml: point at http://127.0.0.1:8765/mcp and fix its header comment.
4. docs/MCP.md: make local the documented path. Remove the hosted Railway endpoint instructions and the Railway hostnames.
5. docs/RAILWAY.md: replace it with a short note saying the Railway deployment was retired, pointing to docs/PROGRESS.md for history and docs/DEPLOY_FREE.md for self-hosting. Remove setup instructions.
6. docs/DEPLOY_FREE.md: state that local Compose is the default, the VM is optional, and the VM profile has never been verified on a real host. Fix the stale Railway row, which describes a trial that no longer applies. Replace the 'Current session' tunnel material in docs/FREE_DEMO.md with a note that Quick Tunnels are no longer used.
7. README.md and docs/ARCHITECTURE.md: fix references to Railway as the deployed stack. Leave text describing the Railway connector alone.
8. docs/PROGRESS.md: append a dated section with what changed, what you ran and what remains unverified. State that the Railway project has not been deleted by this change.

Verification. Run each one and report the real output:
- docker compose config --quiet
- docker compose up -d --build --wait mcp. If something already listens on port 8765, stop and tell me rather than killing it.
- curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8765/healthz should return 200
- curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8765/mcp should return 401 without a token
- docker compose run --rm --no-deps -v "$PWD/backend:/app" api python -m pytest tests -q
- python scripts/mcp_smoke.py if it can target the local endpoint. Read it first and do not run it if it needs changes.
- git grep -n 'up.railway.app' should return only historical lines in docs/PROGRESS.md

Report: what changed, what actually ran, what remains unverified, and any security or compatibility concern.
```

## Manual cutover

Run these yourself, one at a time. Deleting the project destroys the database and its volume permanently.

### 1. Check what you are paying

Open `railway.com/workspace/billing` and note the current usage and any open invoice. Forum answers from Railway staff say open invoices must be paid before you can cancel.

### 2. Archive the Railway databases (optional)

This data is low value, but the archive is cheap. These commands are untested against your service, so confirm the checks pass before going further.

```bash
mkdir -p backups/railway-final && chmod 700 backups/railway-final
```

```bash
railway ssh -s postgres -- sh -c 'pg_dump -U "$POSTGRES_USER" -d orchestra --no-owner' | gzip > backups/railway-final/orchestra.sql.gz
```

```bash
railway ssh -s postgres -- sh -c 'pg_dump -U "$POSTGRES_USER" -d conductor --no-owner' | gzip > backups/railway-final/conductor.sql.gz
```

```bash
gzip -t backups/railway-final/orchestra.sql.gz && gunzip -c backups/railway-final/orchestra.sql.gz | grep -c 'CREATE TABLE'
```

If that database name is wrong, the dump or the count will show it. Do not delete anything until the count is above zero.

Keep this as an archive. Do not merge it into the local database. Railway's `SECRET_KEY` differs from your local one, so its sealed connector credentials cannot be read locally, and the two audit trails would mix.

### 3. Delete the project

Use the dashboard so you can see exactly what you are deleting, or run this from the linked directory:

```bash
railway delete
```

Removing a deployment alone is not enough, because the Postgres volume stays. You need to delete the project.

### 4. Cancel Hobby

Cancel at `railway.com/workspace/billing`. Usage up to the end of the period can still be charged, so check the next invoice. Staff replies on the forum describe this behaviour, but I could not confirm it in Railway's official docs.

### 5. Clean up locally

```bash
railway unlink
```

```bash
docker rm -f orchestra-ai-tunnel
```

Then, by hand:

- Remove the `trycloudflare.com` origin from `APP_ORIGINS` in `.env`, then run `docker compose up -d web`.
- Delete `.env.railway-prod` and `.env.mcp-hosted` once you no longer need them.
- Rotate `CONTROL_PLANE_TOKEN` in `.env`, because the same value was uploaded to Railway. Restart the stack afterwards and re-mint any scoped tokens if the app requires it.
- Unset `ORCHESTRA_MCP_TOKEN` from your shell profile if it holds the hosted token.
- Remove Railway's access to the repository in GitHub under Settings → Applications.

### 6. Make the local stack survive a reboot

Compose services already use `restart: unless-stopped`. Turn on "Start Docker Desktop when you sign in" in Docker Desktop's settings.

## Sources

- [Oracle Always Free resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm)
- [Railway forum: cancelling Hobby](https://station.railway.com/questions/subscription-cancelled-confirm-no-furt-08a1608a)
- [Railway forum: paused usage still billed](https://station.railway.com/questions/i-ve-completely-paused-my-railway-usage-f3f7eaea)
- [Hetzner June 2026 pricing, secondary source](https://wz-it.com/en/blog/hetzner-price-increase-june-2026-cpx-ccx-alternatives/)
