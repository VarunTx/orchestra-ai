# Managing a project end to end

Orchestra separates four kinds of evidence that are easy to confuse:

| View | Answers | Never implies |
| --- | --- | --- |
| **Health** | Is each service answering right now? | That the latest commit is deployed |
| **Changes** | What did CI and pull requests report? | That CI evidence is a deployment |
| **Releases** | Is the expected commit live, with readiness passing? | That a green build reached production |
| **Work** | What did you ask for, and what did the coding runner produce? | That the change was merged or deployed |

## Add a project

**Projects → Add project** asks for a name, optional GitHub repository, environment labels and optional service URLs. It creates no hosting resources and contacts no provider.

Monitoring, GitHub reads, coding and release verification each report their own setup state. A missing coding runner does not block URL monitoring, incidents or draft requests.

Open a service to edit its interval, expected status, provider/container link and `version_url` / `readiness_url`, and to read timestamped observation history. Stale evidence becomes `unknown`; the last known state and last healthy time remain visible instead of being overwritten by a guess.

## Pair a laptop runner

A runner is optional and **off by default**. Nothing starts a model session until you pair a machine, approve a work request and launch the runner yourself with `--allow-model-calls`.

1. Open a project → **Work** → **Pair a local runner**. The one-time token is shown once; the server stores only its SHA-256 hash.
2. It can poll and update only the tasks and evidence for its paired runner and project. It cannot call owner interfaces. Revoke it from the project page.
3. Requirements: Python virtualenv with the official Conductor SDK, Git, npm, OpenCode **2.1.1**, and macOS `sandbox-exec`. The runner fails closed on other platforms.

```sh
export ORCHESTRA_RUNNER_TOKEN='<one-time paired token>'
export DEEPSEEK_API_KEY='<your provider key>'
.venv/bin/python scripts/project_runner.py \
  --url http://127.0.0.1:8000 \
  --repo /absolute/path/to/your/clone \
  --state "$HOME/Library/Application Support/Orchestra/runner" \
  --checks /absolute/path/to/your/checks.json \
  --allow-model-calls
```

Keep `--state` on durable private storage. **Do not delete the journal to retry a session** — it is what prevents a duplicate paid run.

### What the runner does

- Creates `codex/work-<request-uuid>` in a separate git worktree and gives the agent only that worktree, an isolated home/config and its model key.
- Denies shell, subagent and web tools; rejects project OpenCode config and symlinks before launch.
- Installs locked dependencies with npm lifecycle scripts disabled, then runs your **trusted local** check commands with no provider or cloud credentials and no outbound network.
- Commits locally only after checks pass, so approval can bind to an immutable commit.
- Uploads bounded progress, summary, changed file names, session ID, commit and check evidence. Raw transcripts stay on your machine.

This is engineering containment, not a claim that untrusted code is safe on any host. Review the repository and the check file before pairing.

### Approval and publication

- A work request needs both server-side model approval and the runner's `--allow-model-calls`.
- Each request has an explicit session time limit (30–3600 s, default 600). That is a runtime bound, **not** a spending cap.
- Conductor tasks for coding and publication have **zero automatic retries**. An ambiguous start is reserved in the SQLite journal and must be reconciled, never relaunched blindly.
- Publication is a separate Conductor task. It requires approval of the exact commit plus passing re-run checks, and needs `gh auth` on the runner. It opens a **draft PR**; it never merges, deploys or migrates data.

## Interruptions and recovery

The SQLite journal reserves a request before anything launches, so a repeated delivery cannot start a second session. If a session's outcome is unknown, use reconcile: the platform keeps the reservation and records `unknown` rather than guessing. Cancelling before launch is safe; cancelling mid-session marks the reservation until the process reports back.

## Limits worth stating

- macOS only for the first runner; no Windows/Linux containment yet.
- The runner writes to a clone you control. Orchestra never touches your production environment.
- CI status refreshes update the same evidence record; they never mutate deployment history.
- Local check commands are trusted input. A malicious check file is equivalent to running that command yourself.
- A passing CI run is not deployment evidence, and a matched version endpoint is not proof that everything else is healthy.
