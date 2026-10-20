---
description: Review the git diff for regressions, broken contracts, security issues, missing tests and unrelated changes
---

Review the current change for Orchestra AI. Target: $ARGUMENTS (empty means the whole working tree against `HEAD`).

This is a review. Do not edit files, do not run destructive commands, do not deploy, and do not call Gemini.

## Establish scope

- `git status --short`
- `git diff HEAD` for tracked changes, and list untracked files separately (say plainly that their contents were not part of the diff).
- If a ref or path was passed above, use `git diff <ref>...HEAD` or restrict to that path and say which range you reviewed.

## Review axes

**Regressions**
- Behavior that worked before and is now broken or unreachable.
- Error handling, empty/loading states, and polling that could now loop, race or leak timers.
- Anything that changes existing verified behavior recorded in `docs/PROGRESS.md`.

**Contract alignment** — frontend, API and Conductor must move together:
- `backend/app/definitions.py` task input/output vs. `backend/app/workers.py` signatures.
- `backend/app/main.py` request models (`extra='forbid'`, bounds, `Literal` values) vs. what `frontend/components/control-plane.tsx` actually sends.
- `frontend/lib/types.ts` vs. the JSON returned by the API and Conductor.
- `frontend/app/api/[...path]/route.ts` allowlist vs. new endpoints.
- Breaking workflow changes without a version bump.

**Security** (apply `.opencode/skills/enterprise-security/SKILL.md`)
- New route without `Depends(authorize)`; widened proxy allowlist; weakened origin check.
- Token or secret reaching client code, logs, docs or fixtures; `.env` accidentally tracked.
- Cross-tenant or unscoped resource access by ID.

**Workflow safety** (apply `.opencode/skills/workflow-safety/SKILL.md`)
- Non-idempotent task side effects under at-least-once delivery.
- Added retries for billable or non-idempotent work; mutation retries in `Engine.request`.
- Timeout relationships, duplicate execution paths, Gemini gate weakened.

**Tests**
- Is the new behavior covered? Name the missing case (failure path, retry, recovery, auth rejection, validation boundary) and the file where it belongs.
- Flag tests that assert on mocks where the change needs a real-engine check.

**Unrelated changes**
- Refactors, formatting, renames, dependency bumps or doc rewrites outside the stated scope. List them; do not fix them.

## Report

Order by severity: Blocker, Major, Minor, Nit. For each item: `file:line`, the concrete consequence, and the smallest fix. Separate confirmed defects from questions and unverified concerns. End with:
1. A one-line verdict (merge-ready, needs changes, or blocked).
2. The checks from `/verify` that this diff needs but that you did not run.
