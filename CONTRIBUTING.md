# Contributing

Thanks for taking a look. This project is deliberately small: one owner, one deployment, no microservices.

## Prerequisites

- Docker with Compose v2 (the whole stack runs in containers)
- Python 3.11 for secret generation and host-side tests
- Node 22.18+ only if you want to run the frontend outside Docker

## Get it running

```sh
python3 scripts/setup_env.py
docker compose up -d --build --wait --wait-timeout 240
# http://localhost:3000 — sign in with OWNER_PASSWORD from .env
```

## Before opening a pull request

```sh
make test-db     # complete backend suite inside the Compose network
make typecheck
make build
make browser     # Playwright against the live stack
make smoke       # real Conductor executions
```

`make test` runs the same backend suite on the host; database-backed tests then report as skipped with a reason, so use `test-db` for a full result.

## Rules that keep the project honest

- Conductor OSS is the only scheduler. Do not add a second engine or cache execution state.
- Never fabricate metrics. If a value is unknown, render `unknown`/`—` and say why.
- Do not weaken access controls, the SSRF guard or credential sealing.
- Do not commit `.env`, tokens, dumps or screenshots containing real data.
- Add a test for failure, retry and recovery paths, not just the happy path.
- Keep changes focused; unrelated refactors make review harder.

## Adding a workflow task

New task types require worker code in `backend/app/workers.py` and a task definition in `backend/app/definitions.py`. Definitions registered through the API can only reference existing worker tasks; that is what stops the UI from becoming an arbitrary-execution surface.

## Licence

By contributing you agree that your contribution is licensed under the MIT licence in `LICENSE`.
