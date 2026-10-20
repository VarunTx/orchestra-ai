---
name: Workflow Safety
description: Review Conductor definitions, worker idempotency, retries, timeouts, duplicate executions and billable AI calls before approving a change to Orchestra AI.
---

# Workflow Safety

Conductor OSS is the only scheduler, state store and retry authority. The API and workers must not duplicate that behavior.
Read `backend/app/definitions.py`, `backend/app/workers.py`, `backend/app/engine.py` and `backend/app/main.py` before judging a change; do not trust comments or the README alone.

## Checklist

**Definitions** (`definitions.py`)
- Changes to `TASK_DEFS` or `WORKFLOWS` are versioned. Breaking input/output changes require `version: 2` and a new name, never an in-place edit of a version already executed.
- `inputParameters` in the workflow must match the worker function signature in `workers.py`.
- Definition registration in `main.py` lifespan must stay idempotent and tolerate Conductor startup order.

**Workers and idempotency** (`workers.py`)
- Delivery is at-least-once: a worker can run twice for one task. Any task that writes outside Conductor (external API, database, paging, ticket creation) must be idempotent.
- Current workers are pure functions returning dicts; that property is what makes retries safe. Call out any new side effect.
- Failure injection (`failure_mode`, `delay_seconds`) is diagnostic-only and must stay restricted to `diagnostic_pipeline`.

**Retries**
- Do not add task-level retries for non-idempotent work.
- `cp_analyze_incident` intentionally has `retryCount=0` so an ambiguous failure never triggers a second paid Gemini call. Keep it at 0 unless the user explicitly accepts duplicate billing.
- Never retry mutations from the gateway: `Engine.request` retries `GET` only. An ambiguous POST may already have started a workflow.

**Timeouts**
- `timeoutSeconds` (90) must exceed `responseTimeoutSeconds` (75) so the engine, not the worker, decides the outcome.
- `timeoutPolicy: RETRY` re-queues timed-out tasks; confirm that is safe for the task's side effects.
- Workflow `timeoutSeconds` (600) must exceed the worst-case sum of task timeouts plus retries.

**Duplicate executions**
- Preserve `engine.workflowExecutionLockEnabled=true` in `infra/conductor.properties`.
- The UI must not start a duplicate execution on retry; retry/terminate act on an existing workflow ID and must keep their status guards.

**Billable calls**
- Gemini runs only when `ENABLE_GEMINI=true` and a key is present; the API returns 409 otherwise. Do not weaken that gate.
- Never add automatic re-analysis, fan-out or background re-runs of `incident_analysis`.
- Incident logs are untrusted data. They belong in prompt context, never in control flow.

**Tests**
- Retry, timeout and recovery behavior must be covered by unit tests or the local smoke scripts. Do not run `scripts/recovery.py` against Railway or any shared environment.

## Report
For each finding: severity, `file:line`, the concrete failure or duplicate-execution path, and the smallest safe fix. State explicitly when a path is unverified rather than assuming it works.
