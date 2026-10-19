# Conductor Control Plane

You are my autonomous principal software engineer and AI infrastructure architect.

Build a working, impressive, deployable MVP called Conductor Control Plane, inspired by the capabilities of Orkes and powered by the actual open-source Conductor OSS engine.

I want you to take ownership of the entire engineering workflow: architecture, scaffolding, dependencies, backend, frontend, AI integrations, Docker, tests, debugging, documentation, and deployment preparation.

My primary language is Python. I want a polished product suitable for demonstrating to AI infrastructure startups.

## Stack

- Python + FastAPI
- Official Conductor Python SDK
- Conductor OSS
- Next.js + TypeScript + Tailwind + shadcn/ui
- Gemini API
- Docker Compose
- Playwright for browser tests
- GitHub Actions for CI

## Features

1. Premium enterprise-style dashboard
2. Workflow definition explorer
3. Visual DAG representation
4. Real workflow execution
5. Execution history and task inspector
6. Python AI task workers
7. Infrastructure/environment overview
8. Real worker and service health indicators where available
9. AI incident analysis workflow
10. Failure handling, retries, and execution observability

## Working Style

- Be autonomous. Research official documentation yourself.
- Make reasonable implementation decisions without repeatedly asking me.
- Create AGENTS.md and a short execution plan.
- Prioritize a complete working vertical slice before expanding.
- Build the backend and frontend and integrate them.
- Install dependencies and execute tests.
- Use browser automation to verify the user experience.
- Debug errors and continue until tests pass or a real blocker is reached.
- Keep all execution data real; do not fabricate metrics or cluster information.
- Use the actual Conductor engine rather than implementing your own scheduler.
- Create Git commits at working checkpoints.
- Keep a running progress report.
- Keep credentials out of source control.
- Never execute destructive actions, incur cloud costs, or deploy publicly without approval.

## Reliability

- Validate inputs.
- Handle network and API failures.
- Implement bounded retries and timeouts.
- Test worker failures and restarts.
- Protect management endpoints.
- Add smoke tests and integration tests.
- Use reproducible dependencies.

## Definition of Done

- Entire stack starts reproducibly.
- A real workflow executes through Conductor.
- Python workers process tasks.
- Gemini produces an AI result.
- Dashboard displays real execution information.
- Core automated tests pass.
- Browser workflow works end-to-end.
- README contains setup, architecture, screenshots, and limitations.
- Deployment is prepared and verified if hosting access is available.

Start immediately. Do not stop after writing a plan or scaffolding. Implement, run, test, fix, and continue. Ask me only when genuinely blocked by credentials, permissions, paid infrastructure, or a significant decision.
