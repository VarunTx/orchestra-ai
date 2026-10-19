# Engineering instructions
- Build the brief in CONDUCTOR_CONTROL_PLANE_BRIEF.md; never replace Conductor with a scheduler.
- All dashboard execution and health data must come from real services. Mark unknown/unavailable explicitly.
- Keep secrets out of tracked files and browser bundles. Management API requires a token.
- Use Python 3.11+, FastAPI, the official conductor-python SDK, Next.js and TypeScript.
- Run backend tests, frontend type checks/build, and real engine smoke/browser tests when available.
- Update docs/PROGRESS.md with verified results and blockers. Do not claim external tests passed without evidence.
- No public deployment or paid API calls without user approval.
