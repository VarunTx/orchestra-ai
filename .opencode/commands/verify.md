---
description: Run the verification suite (backend pytest, frontend typecheck, frontend build, local Playwright) and report actual results
---

Verify Orchestra AI by actually running the checks below with the shell tool. Report real output; never infer a result you did not observe. Scope hint: $ARGUMENTS (empty means run everything).

## 1. Preconditions

- Run `git status --short` and record the working tree state.
- Do not modify application code, do not deploy, do not call Gemini, do not run `scripts/recovery.py` (destructive), and never point tests at Railway or any shared environment.

## 2. Backend tests

```sh
PYTHONPATH=backend .venv/bin/pytest backend/tests -q
```

If `.venv` is missing, say so and report the check as BLOCKED rather than installing packages without approval. Include the pytest summary line and the first failing traceback, verbatim and trimmed.

## 3. Frontend type check

```sh
npm --prefix frontend run typecheck
```

Dependencies must already be installed; do not run `npm install`/`npm ci` unless the user approves.

## 4. Frontend production build

```sh
npm --prefix frontend run build
```

Report the build's own output (compiled routes, any warnings, exit status). A type check passing does not imply the build passes.

## 5. Playwright (only with a safe local environment)

Run this check only when all of the following hold:

- `.env` exists at the repository root (the spec reads `CONTROL_PLANE_TOKEN` from it).
- The local stack answers: `curl -fsS http://127.0.0.1:8000/healthz` and `curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:3000` succeed.
- `WEB_URL` is unset or resolves to localhost.

Then run:

```sh
npm --prefix frontend run test:e2e
```

Do not start, stop or rebuild containers for this command, and do not export `WEB_URL` to a public host. If any precondition fails, report the Playwright check as SKIPPED with the exact failed precondition and the command the user should run (`docker compose up -d --build --wait`).

## 6. Report

Return a table, one row per check, in this order: Backend tests, Type check, Production build, Playwright. Each row states PASS, FAIL or SKIPPED, plus the measured detail (test counts, durations, exit code) or the skip reason.

Rules:
- A required check that was not executed is SKIPPED or BLOCKED, never PASS.
- Never silently drop a check because it looked irrelevant or slow.
- If a check fails, quote the real error output and stop recommending merge until it is fixed or the user explicitly accepts it.
- End with an explicit list of anything left unverified.
