# Security policy

Orchestra AI is a **single-owner** control plane. It is designed to be run by one person on a server they control, not as a multi-tenant service. Do not give untrusted people accounts, and do not treat it as an internet-facing SaaS.

## Reporting a vulnerability

Open a private [GitHub security advisory](https://github.com/VarunTx/orchestra-ai/security/advisories/new) rather than a public issue. Please include:

- the affected route, file or connector,
- a minimal reproduction,
- what an attacker gains.

Never include live credentials, tokens or customer data in a report.

## Supported versions

Only the `main` branch is maintained. There are no backports.

## Security model (what is already enforced)

- **Owner sessions**: the password (or master API token) is exchanged server-side for an opaque session token stored hashed in PostgreSQL. The browser never receives the master token; the cookie is `HttpOnly`, `SameSite=strict` and `Secure` when configured.
- **Authorization**: every resource route requires a session or the master token. The Next.js proxy exposes an explicit allowlist of API segments and checks `Origin` on mutations.
- **Credentials at rest**: connector tokens and webhook targets are sealed with AES-GCM using a key derived from `SECRET_KEY`.
- **SSRF protection**: health checks and webhook deliveries reject non-HTTP(S) schemes, embedded credentials and hosts resolving to loopback, private, link-local or reserved addresses (unless `HTTP_CHECK_ALLOW_PRIVATE=true` is deliberately set for local development).
- **Bounded input**: request models forbid extra fields and bound lengths, counts, versions and intervals.
- **Defined workflows only**: registration accepts worker-backed `SIMPLE` tasks only; `HTTP`, `EVENT` and `SUB_WORKFLOW` tasks are rejected.

## Deployment checklist

Run through this before exposing an instance:

1. `OWNER_PASSWORD` is long and unique; `SECRET_KEY` and `CONTROL_PLANE_TOKEN` are generated, not reused.
2. `COOKIE_SECURE=true` and `APP_ORIGINS` lists your exact HTTPS origin.
3. PostgreSQL, Valkey, Conductor and the API are **not** published to the internet. Only the dashboard (or Caddy) is.
4. `ENABLE_GEMINI=false` unless you accept provider cost.
5. `.env` is not committed and the host is patched.
6. Backups exist (`scripts/backup.sh`) and you have completed one restore drill.

## Known limits

- Health checks resolve hostnames and then connect by hostname, so a DNS-rebinding attack between resolution and connection is theoretically possible. Redirects are not followed and targets are owner-configured.
- The login rate limiter is per process, not distributed.
- The monitoring collector runs inside the API process; there is no separate worker fleet to isolate it from API load.
- There is no MFA, RBAC or tenant isolation, by design.
