# Deploy Orchestra AI on a free VM

The target is one small server you own, running the whole stack with Docker Compose. No PaaS trial, no per-service pricing, no expiring credit.

## Why not Railway/Render/Fly

| Option | Reality (verified October 2026) |
| --- | --- |
| Railway | $5 trial credit, up to 30 days, then it stops. Five-service and 1 GB RAM limits already cap Conductor. |
| Render free | Web services sleep; no free background workers or Postgres beyond a short trial. |
| Fly.io | Free tier removed for new accounts; card required. |
| **Oracle Always Free A1** | **2 OCPU / 12 GB RAM / 200 GB block / 10 TB egress, free for the life of the account** |
| Hetzner CX22 | ~€3.79/mo — the reliable fallback if A1 capacity is unavailable |

Conductor needs a JVM (~1.4 GB), PostgreSQL, Valkey, the API, workers and Next.js. That is roughly 3–4 GB of RAM and fits comfortably on 12 GB.

## Components and licences

| Component | Licence / cost |
| --- | --- |
| Conductor OSS | Apache 2.0 |
| PostgreSQL | PostgreSQL licence |
| Valkey (Redis-compatible lock) | BSD-3 |
| Caddy (public TLS) | Apache 2.0 |
| Next.js, FastAPI, Python SDK | MIT / Apache 2.0 |
| Oracle Always Free VM | Free (account required) |
| Tailscale | Free plan (3 users / 100 devices); proprietary service. [Headscale](https://github.com/juanfont/headscale) is the self-hosted OSS alternative |
| DuckDNS | Free subdomain service (not OSS) |

Nothing in the default profile calls a paid API. Gemini stays disabled.

## Two access models

**Tailscale (recommended).** No open ports, no domain, HTTPS on your private tailnet. `tailscale serve --bg 3000` fronts the dashboard.

**Public HTTPS.** Caddy terminates TLS with a Let's Encrypt certificate for a free DuckDNS name and proxies to `web:3000`. Only ports 80/443 are opened; the API, PostgreSQL, Valkey and Conductor stay on the private Compose network.

## Run the wizard

```sh
./scripts/deploy_wizard.sh
```

It walks you through seven stages — access model, VM creation, Docker install, DNS or Tailscale, secret generation into `.env.deploy` (mode 600), stack start, and a verification checklist. It opens the right console pages and tells you exactly what to click. It never uploads a secret anywhere except the `.env` you copy to the VM.

Manual equivalent:

```sh
ssh ubuntu@<vm-ip>
git clone https://github.com/VarunTx/orchestra-ai.git /opt/orchestra
cd /opt/orchestra
# copy the generated .env next to compose.yaml
docker compose -f compose.yaml -f compose.prod.yaml up -d --build --wait --wait-timeout 600
# public TLS only:
docker compose -f compose.yaml -f compose.prod.yaml --profile public up -d
```

## Memory budget (`compose.prod.yaml`)

| Service | Limit |
| --- | --- |
| conductor | 1408 MB (JVM `-Xmx1024m`) |
| postgres | 768 MB |
| api | 512 MB |
| web | 512 MB |
| workers | 384 MB |
| caddy | 192 MB |
| valkey | 128 MB |

Limits, not reservations: idle usage is lower. The A1 instance has 12 GB, so there is headroom for builds.

## Oracle caveats

- Always Free A1 is **home-region only**; changing region is not possible for free resources.
- Capacity is not guaranteed. If creation fails with "out of host capacity", retry later or try another availability domain.
- Oracle may reclaim an instance that is idle for 7 days, defined as **all** of: 95th-percentile CPU < 20%, network < 20%, and memory < 20% (A1 only). The monitoring collector and Conductor's sweeper keep memory well above 20%, but keep the workload real rather than abandoned.
- You own OS patching. `sudo apt-get upgrade` monthly is enough for a single-owner box.

## Backups

```sh
./scripts/backup.sh                 # both databases, gzipped, 14-day retention
RCLONE_REMOTE=oci:orchestra ./scripts/backup.sh   # optional offsite copy
./scripts/restore.sh backups/orchestra-<stamp>.sql.gz   # restores into orchestra_restore
```

`restore.sh` never touches the live database unless you pass `--in-place` and type the database name. Oracle Object Storage gives 20 GB free, which is far more than these dumps need.

Schedule it:

```cron
15 3 * * * cd /opt/orchestra && ./scripts/backup.sh >> /var/log/orchestra-backup.log 2>&1
```

## Verification checklist after deploy

1. `https://<host>` returns 200 with a valid certificate.
2. Anonymous `GET /api/projects` returns 401.
3. Owner-password login works and the cookie is `HttpOnly` + `Secure`.
4. `/api/infrastructure` reports storage `connected`, engine `connected`, four workers `polling`, and engine telemetry `available`.
5. One real `diagnostic_pipeline` execution reaches `COMPLETED`.
6. Register a project with a public health URL, run "Check now", confirm a real status.
7. Stop the browser for ten minutes; confirm new observations appear (the collector runs in the API process).

## Known limitations

- Single VM: no high availability. A reboot is a short outage; Compose restarts services on boot if Docker is enabled.
- Tailscale mode depends on one free third-party service; Headscale removes that dependency at the cost of running another service.
- Conductor's metrics are scraped on demand, not stored: history lives in the app database, not in Prometheus.
- The Railway trial deployment is separate and will expire; this VM profile does not reuse it.
