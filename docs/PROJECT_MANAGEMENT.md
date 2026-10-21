# Managing projects through Orchestra

Orchestra manages development and technical operations. Preschool conversations, bookings and policy decisions remain in Sunflower's existing dashboard. The managed fork is `VarunTx/aws_hackathon`; the documented live source/hosting belongs to the teammate. A passing CI run never proves that the fork is deployed.

## Add a project and use it daily

Choose **Projects → Add project**. The guide asks for a GitHub repository, environment labels and optional service URLs. It does not create hosting resources. Sunflower remains an optional reusable example, not a prerequisite.

Monitoring, GitHub reads, coding and release verification have separate setup indicators. A missing coding agent does not stop URL monitoring or draft requests. Open a service to edit its interval, expected HTTP response, provider/container link and version/readiness URLs, and inspect timestamped observation history. Stale evidence becomes unknown; the last known state and last healthy time remain available.

Work and project tabs are shareable URLs. **Runs** links to the same authorized Conductor evidence shown in history, including after project configuration is deleted. Active work must be cancelled/reconciled before project deletion. Legacy coding executions whose ownership cannot be established remain in Conductor but are omitted from application history. Verification projects are labelled, not automatically deleted; the label can be edited in project settings.

GitHub connections have explicit project scope. Public reads can use an empty token; validate and sync after selecting projects. Actions runs appear as CI under Changes, alongside timestamped recent PR metadata. A permission/rate-limit failure preserves old evidence and displays its error. It never becomes deployment success. Railway account tokens support read-only inventory discovery and selected local resource links. Project tokens cannot use account inventory; this unsupported scope has an explicit explanation. No Railway resource is changed. Docker agent/container links use the exact name from `docker ps -a`; stopped containers report down and lost contact becomes stale/unknown.

Webhook delivery attempts and failures appear under Integrations. The engine scheduler and runtime settings remain read-only; an unavailable scheduler is not reported as an empty successful response.

## Start locally

Build the API and web after pulling these changes (`docker compose up -d --build api web`). The API applies the additive application-database migration and registers `project_change` v1 and the separate `project_publication` v1. Existing incident workflow versions and engine persistence are unchanged.

Open Projects and choose **Import Sunflower Grove**. Import is explicit and idempotent. It creates three HTTP-monitored services with Cloudflare resource mappings, readiness/version URLs, three dependency records that initially remain unknown, and the application-authentication blocker. The importer does not contact Cloudflare or change the deployed app. Health monitoring performs ordinary read-only GETs.

Project lifecycle views:

- **Work:** requests, acceptance criteria, paired runners, engine status and bounded evidence.
- **Changes:** CI runs, separate from deployment records. Existing GitHub Actions records are retained and reclassified as CI.
- **Releases:** expected commit plus individual version/readiness observations. Every service must match and pass before verification succeeds.
- **Health:** dependency uncertainty, application blockers and editable provider mappings. Existing service health/incident history remains below.

The generic execution inspector also accepts project executions created by Orchestra; manual retry is disabled for these workflows.

## Pair a laptop

Expand **Pair a local runner** under Work. Copy its one-time token into `ORCHESTRA_RUNNER_TOKEN` in your terminal. The server stores only its SHA-256 hash. The token can poll/update only tasks and evidence for its paired runner/project; it cannot use owner interfaces. Revoke it from the project page.

Use the existing Python virtualenv (it includes the official Conductor SDK), Git, npm, OpenCode **2.1.1**, and macOS `sandbox-exec`. This first runner deliberately fails closed on other operating systems. Use a trusted, clean local clone of the managed fork with `main` checked out. It uses the local base commit and never fetches automatically; update the clone yourself before requesting work.

Create a trusted local checks file; the checked-in example is `integrations/sunflower/checks.json`. Commands are configured on your machine, never taken from workflow inputs or model output. The runner installs locked dependencies with npm lifecycle scripts disabled before the agent edits files. Check subprocesses have no provider/cloud credentials and outbound networking is denied. Tests may bind loopback ports.

```sh
export ORCHESTRA_RUNNER_TOKEN='<one-time paired token>'
export DEEPSEEK_API_KEY='<your provider key>'
.venv/bin/python scripts/project_runner.py \
  --url http://127.0.0.1:8000 \
  --repo /absolute/path/to/aws_hackathon \
  --state "$HOME/Library/Application Support/Orchestra/sunflower" \
  --checks /absolute/path/to/Orchestra\ AI/integrations/sunflower/checks.json \
  --allow-model-calls
```

Keep `--state` on durable private local storage. **Do not delete the journal to retry a session.** Start requires both model approval on the work request and the local `--allow-model-calls` opt-in. Those approvals permit provider charges. Each request carries an explicit session time limit (30–3600 seconds; default 600), checked during coding. This is a runtime limit, not a monetary billing cap. No real model call was made during implementation.

The runner exposes no listener to Orchestra. It uses SDK task polling/results through two restricted gateway paths; Conductor remains private and owns queueing, execution state and timeouts. Each runner has a strict task domain with no default-domain fallback. Only one coding/publication task may reserve a project. Before reservation the API requires a recent successful companion preflight. Missing repository access, CLI capabilities, provider configuration, sandbox/tools or trusted checks are actionable setup failures. Publication separately requires GitHub CLI authentication. Check commands cannot directly deploy, migrate/reset databases or publish. General checks run offline; the fixed built-in `git diff --check` runs through the same read-only host Git boundary used to collect diffs, with hooks, fsmonitor, external diff and text conversion disabled. The agent executable alone is granted an exact file read when installed under the user home directory; credentials and the rest of that directory remain outside its sandbox.

Each request gets `codex/work-<request UUID>` in a separate worktree. The agent receives only its model key, isolated configuration/home, and access to that worktree and required runtimes. Shell/subagent/web tools are denied; project OpenCode configurations and symlinks are rejected before launch. Raw session transcripts stay local. Only bounded progress, summary, file names, session ID, commit and test evidence are uploaded. This is an engineering containment layer, not a claim that untrusted code is safe on an arbitrary host; review the repository and local check configuration before pairing it.

## Interruptions and recovery

The SQLite journal reserves the request before launching anything. A repeated delivery cannot launch another session. Conductor task retries are zero. Gateway task polls are single-attempt because polling changes queue state.

A lost connection during coding stops the subprocess. Runner-process death is different: an orphan may still exist. A restarted runner reports that request as interrupted/uncertain and does not relaunch it. Stop/inspect the recorded process and worktree, then explicitly resolve it:

```sh
# Use the same --url, --repo, --state and --checks arguments as above:
.venv/bin/python scripts/project_runner.py ... --resolve <work-id>
```

Resolution reports failure, retains local files and releases the reservation after terminal engine confirmation. Cancelled delivered tasks keep their project reservation until the runner acknowledges stopping. If a workflow-start response is lost, use **Reconcile start**; Orchestra searches by correlation ID and never blindly submits another workflow.

Completed evidence is saved locally before upload. An acknowledgment loss retries evidence/result delivery, not coding. Evidence updates invalidate any previous approval.

## Review and publish

Inspect the changed files, local diff and recorded checks. Approval requires a clean, passing commit and a completed Conductor workflow. The UI binds publication approval to its exact full SHA. Choose **Publish draft PR** on the website after exact-commit approval. This starts `project_publication` in Conductor, routed only to the paired companion. There is no daily publication terminal command. The existing `--publish` CLI remains an advanced compatibility interface and still requires exact server approval.

The companion durably reserves publication before a Git/GitHub write. Identical evidence redelivery preserves approval; changed commit or review evidence invalidates it, and evidence is frozen once publication starts. A lost acknowledgment triggers a read-only GitHub PR query matching the exact head SHA before any further write. An uncertain attempt never blindly repeats push/PR creation. The UI can reconcile uncertain scheduling and cancel publication; a write already sent to GitHub may still have succeeded, so cancellation cannot promise remote undo. Follow-ups are new drafts with model approval off.

Nothing auto-merges or deploys. Teammates deploy through the existing process; an expected-release entry is verified only against version evidence and successful checks.

## One companion, several explicitly paired profiles

Store a private local JSON file, outside the repository, containing profiles such as:

```json
[
  {
    "name": "Sunflower",
    "url": "http://127.0.0.1:8000",
    "repo": "/absolute/path/to/aws_hackathon",
    "state": "/absolute/path/to/durable/private/sunflower-state",
    "checks": "/absolute/path/to/Orchestra AI/integrations/sunflower/checks.json",
    "token_env": "SUNFLOWER_RUNNER_TOKEN",
    "provider_key_env": "SUNFLOWER_DEEPSEEK_KEY",
    "github_token_env": "SUNFLOWER_GITHUB_TOKEN",
    "allow_model_calls": true
  }
]
```

Use environment variable names rather than putting credential values in JSON. `github_token_env` is optional when `gh auth` already supplies the intended identity; `gh_config_dir` can select a separate local CLI profile. Each project needs its own pairing token, checkout and journal directory. Start `.venv/bin/python scripts/project_companion.py --profiles /private/path/profiles.json`. One companion supervises the existing project-scoped SDK runners; it does not schedule workflows or duplicate Conductor state. Profiles are never added implicitly.


## Sunflower changes prepared separately

`integrations/sunflower/readiness-release-ci.patch` contains the companion changes, based on `f32d8b5c7776732090e9646fb62f129ce321a583`. It adds bounded, read-only D1 readiness, build SHA evidence for all three apps, pinned Wrangler, a local-only D1 check and GitHub Actions. The implementation checkout is `/private/tmp/orchestra-sunflower`; the patch is the durable deliverable in this repository.

Apply the patch to a clean checkout with `git apply --check` followed by `git apply`. Review and commit it before publication. An uncommitted frontend build reports a null SHA unless BUILD_SHA is explicitly supplied; it must not masquerade as a committed release. Frontend build artifacts contain `/version.json`; the engine exposes `/api/version`. `/api/health` retains its contract. `/api/ready` returns 503 when D1 cannot complete a bounded read and never calls Gemini/n8n.

Your teammate continues deploying through the existing process. The API deploy must supply `BUILD_SHA` for the exact reviewed commit (`wrangler deploy --var BUILD_SHA:<full-sha>`); this command is documentation, not deployment authorization. Frontends derive the clean build commit. Record the expected SHA in Orchestra and verify it after deployment. Missing endpoints, mismatches and failing readiness remain unverified. CI success and Gemini configuration do not prove live model availability.

## Security and verification limits

Sunflower's existing administrative routes have no authentication. This change records that blocker; it does not remediate the app's authentication or authorize real family data. Orchestra does not call policy approval, reset, booking, conversation or model interfaces. Cloudflare credentials and family conversations are not imported.

The new migration is additive. GitHub CI records remain in the same table for compatibility but have `evidence_kind=ci`, are excluded from deployment lists and do not set project last-deployed timestamps.

Run `make test-db`, `make typecheck`, `make build`, focused Playwright tests and the opt-in local engine contract test:

```sh
docker compose run --rm --no-deps -e ORCHESTRA_ENGINE_TEST=true \
  -v "$PWD/backend:/app" api python -m pytest tests/test_lifecycle_engine.py -q
```

Never point recovery tests at Railway/shared hosting. Live DeepSeek coding, GitHub publication and teammate deployment require their respective approvals and remain separate acceptance steps.
