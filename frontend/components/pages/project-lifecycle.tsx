"use client";

import { useEffect, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { ErrorBanner, when } from "@/components/resource-ui";

type Evidence = {
  phase?: string;
  head_sha?: string;
  base_sha?: string;
  session_id?: string;
  summary?: string;
  changed_files?: string[];
  tests_passed?: boolean;
  dirty?: boolean;
  diff?: string;
  checks?: { name: string; passed: boolean; output?: string }[];
};
type Work = {
  id: string;
  title: string;
  request: string;
  acceptance: string;
  submission: string;
  workflow_id: string | null;
  active: boolean;
  artifacts: Evidence;
  approved_sha: string | null;
  publish_approved: boolean;
  runner_id: string | null;
  model_approved: boolean;
  model_budget_seconds: number;
  publication_submission: string;
  publication_execution: { status: string };
  publication: { state?: string; pr_url?: string };
  execution: { status: string };
};
type Lifecycle = {
  capabilities: Record<
    string,
    { ready: boolean; detail: string; setup_url: string }
  >;
  connections: {
    id: string;
    provider: string;
    status: string;
    last_error: string | null;
    checked_at: string | null;
    evidence: {
      notes?: string;
      pull_requests?: {
        number: number;
        title: string;
        state: string;
        draft: boolean;
        url: string;
        head_sha: string;
        updated_at: string;
      }[];
    };
  }[];
  management: {
    managed_repo?: string;
    deployed_repo?: string;
    hosting_owner?: string;
    dependencies?: {
      name: string;
      status: string;
      observed_at: string | null;
    }[];
    blockers?: string[];
  };
  services: {
    id: string;
    name: string;
    external_ref: Record<string, string>;
  }[];
  runners: {
    id: string;
    name: string;
    connection: string;
    last_seen_at: string | null;
    revoked_at: string | null;
    diagnostics: {
      ready?: boolean;
      checked_at?: string;
      checks?: { name: string; ok: boolean; detail: string }[];
    };
  }[];
  work: Work[];
  ci: {
    id: string;
    status: string;
    commit_sha: string;
    url: string;
    deployed_at: string;
  }[];
  releases: {
    id: string;
    expected_sha: string;
    checked_at: string | null;
    evidence: {
      status?: string;
      services?: {
        service: string;
        version: { status: string; observed_sha?: string };
        readiness: string;
      }[];
    };
  }[];
};

export default function ProjectLifecycle({ projectId }: { projectId: string }) {
  const state = useApi<Lifecycle>(`projects/${projectId}/lifecycle`, {
    pollMs: 15000,
  });
  const [tab, setTab] = useState("Work");
  useEffect(() => {
    const read = () => {
      const t = new URLSearchParams(window.location.search).get("tab");
      setTab(
        ["Work", "Changes", "Releases", "Health"].includes(t ?? "")
          ? t!
          : "Work",
      );
    };
    read();
    window.addEventListener("popstate", read);
    return () => window.removeEventListener("popstate", read);
  }, [projectId]);
  function selectTab(name: string) {
    const url = new URL(window.location.href);
    url.searchParams.set("tab", name);
    window.history.pushState({}, "", url);
    setTab(name);
  }

  const [message, setMessage] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [localRepo, setLocalRepo] = useState("/path/to/your/project");
  const [localState, setLocalState] = useState(
    "/path/to/durable/orchestra-state/" + projectId,
  );
  const [localChecks, setLocalChecks] = useState("/path/to/checks.json");
  const [origin, setOrigin] = useState("");
  useEffect(() => setOrigin(window.location.origin), []);
  const shellQuote = (s: string) => "'" + s.replaceAll("'", "'\"'\"'") + "'";
  const [busy, setBusy] = useState(false);
  async function act(path: string, body?: unknown, method = "POST") {
    if (busy) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await api<Record<string, string>>(path, {
        method,
        ...(method === "DELETE" ? {} : { body: JSON.stringify(body ?? {}) }),
      });
      await state.reload();
      return result;
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function createWork(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const f = new FormData(form);
    const result = await act(`projects/${projectId}/work`, {
      title: f.get("title"),
      request: f.get("request"),
      acceptance: f.get("acceptance"),
      runner_id: f.get("runner_id") || null,
      model_approved: f.get("model_approved") === "on",
      model_budget_seconds: Number(f.get("model_budget_seconds")),
    });
    if (result) form.reset();
  }
  const data = state.data;
  return (
    <section className="panel project-lifecycle" aria-label="Project lifecycle">
      <div className="panel-heading">
        <h2>Project lifecycle</h2>
        <span className="subtle">Development → review → release → health</span>
      </div>
      <ErrorBanner message={message ?? state.error} />
      <div className="setup-grid" aria-label="Project readiness">
        {data &&
          Object.entries(data.capabilities).map(([name, c]) => (
            <p key={name}>
              <strong>
                {name}: {c.ready ? "Configured" : "Setup needed"}
              </strong>
              <br />
              {c.detail} · <a href={c.setup_url}>Open setup</a>
            </p>
          ))}
      </div>
      {data?.management.managed_repo && (
        <p>
          Managed: <strong>{data.management.managed_repo}</strong> · Live
          source: <strong>{data.management.deployed_repo ?? "unknown"}</strong>{" "}
          · Hosting: {data.management.hosting_owner ?? "unknown"}. The deployed
          commit must be verified separately.
        </p>
      )}
      <div
        className="toolbar"
        role="tablist"
        aria-label="Project lifecycle views"
      >
        {["Work", "Changes", "Releases", "Health"].map((name) => (
          <Button
            key={name}
            role="tab"
            aria-selected={tab === name}
            variant={tab === name ? "default" : "outline"}
            onClick={() => selectTab(name)}
          >
            {name}
          </Button>
        ))}
      </div>
      {tab === "Work" && (
        <div className="stack" role="tabpanel">
          <p className="subtle">
            OpenCode runs on your paired laptop. Model usage requires approval
            here and an opt-in on the runner. Publication is approved separately
            for an exact commit.
          </p>
          <details>
            <summary>Pair a local runner</summary>
            <form
              className="inline-form"
              onSubmit={async (e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                const r = await act(`projects/${projectId}/runners`, {
                  name: f.get("name"),
                });
                if (r) setToken(r.token);
              }}
            >
              <label>
                Runner name
                <input
                  name="name"
                  required
                  maxLength={80}
                  placeholder="My laptop"
                />
              </label>
              <Button disabled={busy}>Pair runner</Button>
            </form>
            {token && (
              <div>
                <p>
                  Copy this token now. It is shown once and stored as a hash.
                </p>
                <input
                  aria-label="Runner token"
                  readOnly
                  type="password"
                  value={token}
                />
                <Button
                  variant="outline"
                  onClick={() => void navigator.clipboard.writeText(token)}
                >
                  Copy token
                </Button>
                <Button variant="outline" onClick={() => setToken(null)}>
                  Hide
                </Button>
              </div>
            )}
            <ol>
              <li>
                Use macOS with git, Node/npm, Python, OpenCode and the GitHub
                CLI installed.
              </li>
              <li>
                Clone your project and confirm its origin matches this project.
                In your Orchestra checkout install its existing Python
                requirements in a virtual environment.
              </li>
              <li>
                Create a trusted local checks file, for example{" "}
                <code>
                  [
                  {`{"name":"Docs check","directory":".","argv":["git","diff","--check"]}`}
                  ]
                </code>
                . Choose meaningful tests for your repository.
              </li>
              <li>
                Set ORCHESTRA_RUNNER_TOKEN to the one-time token above and
                DEEPSEEK_API_KEY in your laptop terminal. Keep credentials out
                of this website and repository files.
              </li>
            </ol>
            <label>
              Local repository path
              <input
                value={localRepo}
                onChange={(e) => setLocalRepo(e.target.value)}
              />
            </label>
            <label>
              Durable state directory
              <input
                value={localState}
                onChange={(e) => setLocalState(e.target.value)}
              />
            </label>
            <label>
              Local checks file
              <input
                value={localChecks}
                onChange={(e) => setLocalChecks(e.target.value)}
              />
            </label>
            <p>
              Run from your Orchestra checkout. This enables the companion to
              accept explicitly approved work; pairing itself makes no model
              call.
            </p>
            <pre>{`.venv/bin/python scripts/project_runner.py --url ${shellQuote(origin)} --repo ${shellQuote(localRepo)} --state ${shellQuote(localState)} --checks ${shellQuote(localChecks)} --allow-model-calls`}</pre>
            <p>
              Keep the state directory durable. For multiple projects, use{" "}
              <code>
                scripts/project_companion.py --profiles
                /private/path/profiles.json
              </code>
              ; each profile has separate credentials and a separate journal.
              Daily work and approved publication then happen here.
            </p>
          </details>
          <div>
            {data?.runners.map((r) => (
              <div key={r.id} className="inline-actions">
                <strong>{r.name}</strong>
                <span>
                  {r.connection} ·{" "}
                  {r.last_seen_at ? when(r.last_seen_at) : "never connected"}
                </span>
                <ul>
                  {r.diagnostics.checks?.map((c) => (
                    <li key={c.name}>
                      {c.name}: {c.ok ? "Ready" : c.detail}
                    </li>
                  ))}
                </ul>
                {!r.diagnostics.checked_at && (
                  <p>
                    Waiting for companion preflight. Start the generated command
                    above.
                  </p>
                )}
                {!r.revoked_at && (
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() =>
                      void act(
                        `projects/${projectId}/runners/${r.id}`,
                        undefined,
                        "DELETE",
                      )
                    }
                  >
                    Revoke
                  </button>
                )}
              </div>
            ))}
          </div>
          <form className="stack" onSubmit={createWork}>
            <label>
              Title
              <input
                name="title"
                required
                maxLength={120}
                placeholder="Add readiness and release evidence"
              />
            </label>
            <label>
              Requested change
              <textarea
                name="request"
                required
                minLength={10}
                maxLength={10000}
              />
            </label>
            <label>
              Acceptance criteria
              <textarea
                name="acceptance"
                required
                minLength={10}
                maxLength={5000}
              />
            </label>
            <label>
              Runner
              <select aria-label="Work runner" name="runner_id" defaultValue="">
                <option value="">Save draft without runner</option>
                {data?.runners
                  .filter((r) => !r.revoked_at)
                  .map((r) => (
                    <option value={r.id} key={r.id}>
                      {r.name} ({r.connection})
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Maximum model session time (seconds)
              <input
                type="number"
                name="model_budget_seconds"
                min={30}
                max={3600}
                defaultValue={600}
                required
              />
            </label>
            <label>
              <input type="checkbox" name="model_approved" /> I approve model
              usage for this request; my provider may charge.
            </label>
            <Button disabled={busy}>Create request</Button>
          </form>
          {data?.work.length === 0 && <p>No work requests yet.</p>}
          {data?.work.map((w) => (
            <article className="panel" key={w.id}>
              <h3>{w.title}</h3>
              <p>{w.request}</p>
              <p className="subtle">Acceptance: {w.acceptance}</p>
              <p>
                {w.submission === "draft"
                  ? "Draft"
                  : w.execution.status === "UNAVAILABLE"
                    ? "Engine unavailable — last evidence retained"
                    : w.submission === "cancelled"
                      ? "Cancelled — waiting for stop acknowledgment if reserved"
                      : w.execution.status === "COMPLETED"
                        ? "Ready for review"
                        : ["FAILED", "TERMINATED", "TIMED_OUT"].includes(
                              w.execution.status,
                            )
                          ? w.execution.status
                          : w.active &&
                              !data.runners.some(
                                (r) => r.connection === "online",
                              )
                            ? "Waiting for laptop — work may be interrupted"
                            : w.artifacts.phase === "checks"
                              ? "Running checks"
                              : w.artifacts.phase === "coding"
                                ? "Coding"
                                : "Preparing"}{" "}
                · {w.submission}
                {w.active ? " · project reserved" : ""}
              </p>
              {w.workflow_id && (
                <p className="mono-cell">
                  <a href={`/executions?run=${w.workflow_id}`}>Open run</a> ·{" "}
                  {w.workflow_id}
                </p>
              )}
              {w.submission === "draft" && (
                <details>
                  <summary>Edit draft and model approval</summary>
                  <form
                    className="stack"
                    onSubmit={async (e) => {
                      e.preventDefault();
                      const f = new FormData(e.currentTarget);
                      await act(
                        `work/${w.id}`,
                        {
                          title: f.get("title"),
                          request: f.get("request"),
                          acceptance: f.get("acceptance"),
                          runner_id: f.get("runner_id") || null,
                          model_approved: f.get("model_approved") === "on",
                          model_budget_seconds: Number(f.get("budget")),
                        },
                        "PATCH",
                      );
                    }}
                  >
                    <label>
                      Draft title
                      <input name="title" required defaultValue={w.title} />
                    </label>
                    <label>
                      Draft change
                      <textarea
                        name="request"
                        required
                        minLength={10}
                        defaultValue={w.request}
                      />
                    </label>
                    <label>
                      Draft acceptance
                      <textarea
                        name="acceptance"
                        required
                        minLength={10}
                        defaultValue={w.acceptance}
                      />
                    </label>
                    <label>
                      Paired laptop
                      <select name="runner_id" defaultValue={w.runner_id ?? ""}>
                        <option value="">Not paired yet</option>
                        {data.runners
                          .filter((r) => !r.revoked_at)
                          .map((r) => (
                            <option value={r.id} key={r.id}>
                              {r.name}
                            </option>
                          ))}
                      </select>
                    </label>
                    <label>
                      Session time limit (seconds)
                      <input
                        name="budget"
                        type="number"
                        min={30}
                        max={3600}
                        defaultValue={w.model_budget_seconds}
                      />
                    </label>
                    <label className="checkbox-row">
                      <input
                        name="model_approved"
                        type="checkbox"
                        defaultChecked={w.model_approved}
                      />
                      Approve one model session with this limit
                    </label>
                    <Button disabled={busy}>Save draft</Button>
                  </form>
                </details>
              )}
              <div className="inline-actions">
                {w.submission === "draft" && (
                  <Button
                    disabled={busy}
                    onClick={() => void act(`work/${w.id}/start`)}
                  >
                    Start work
                  </Button>
                )}
                {w.submission === "uncertain" && (
                  <Button
                    disabled={busy}
                    onClick={() => void act(`work/${w.id}/reconcile`)}
                  >
                    Reconcile start
                  </Button>
                )}
                {w.active && w.publication_submission === "draft" && (
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => void act(`work/${w.id}/cancel`)}
                  >
                    Cancel run
                  </Button>
                )}
              </div>
              {w.artifacts.summary && <p>{w.artifacts.summary}</p>}
              {w.artifacts.head_sha && (
                <p className="mono-cell">
                  Commit: {w.artifacts.head_sha} · tests{" "}
                  {w.artifacts.tests_passed ? "passed" : "failed or incomplete"}
                </p>
              )}
              {w.artifacts.changed_files && (
                <p>Changed files: {w.artifacts.changed_files.join(", ")}</p>
              )}
              {w.artifacts.diff && (
                <details open>
                  <summary>Review changes</summary>
                  <pre>{w.artifacts.diff}</pre>
                </details>
              )}
              {w.artifacts.checks?.map((c, i) => (
                <details key={i}>
                  <summary>
                    {c.name}: {c.passed ? "Passed" : "Failed"}
                  </summary>
                  <pre>{c.output}</pre>
                </details>
              ))}
              <details>
                <summary>Advanced: raw evidence</summary>
                <pre>{JSON.stringify(w.artifacts, null, 2)}</pre>
              </details>
              {w.execution.status === "COMPLETED" && w.artifacts.head_sha && (
                <Button
                  variant="outline"
                  disabled={
                    busy || !w.artifacts.tests_passed || w.artifacts.dirty
                  }
                  onClick={() => {
                    if (
                      window.confirm(
                        `Approve publishing commit ${w.artifacts.head_sha} to GitHub as a draft PR?`,
                      )
                    )
                      void act(`work/${w.id}/approve`, {
                        sha: w.artifacts.head_sha,
                        approve_publication: true,
                      });
                  }}
                >
                  Approve exact commit for publication
                </Button>
              )}
              {w.execution.status === "COMPLETED" &&
                w.publication_submission === "draft" && (
                  <Button
                    variant="outline"
                    disabled={busy}
                    onClick={() => void act(`work/${w.id}/reject`)}
                  >
                    Request changes / revoke approval
                  </Button>
                )}
              {w.publish_approved && (
                <div>
                  <p>
                    Publication approved for {w.approved_sha?.slice(0, 12)}.
                  </p>
                  <Button
                    disabled={busy || w.publication_submission !== "draft"}
                    onClick={() => void act(`work/${w.id}/publish`)}
                  >
                    Publish draft PR
                  </Button>
                </div>
              )}
              {w.active && w.publication_submission === "submitted" && (
                <Button
                  disabled={busy}
                  variant="outline"
                  onClick={() => void act(`work/${w.id}/publication/cancel`)}
                >
                  Cancel publication
                </Button>
              )}
              {w.publication_submission === "uncertain" && (
                <Button
                  disabled={busy}
                  onClick={() => void act(`work/${w.id}/publication/reconcile`)}
                >
                  Reconcile publication request
                </Button>
              )}
              {w.submission !== "draft" && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() =>
                    void act(`projects/${projectId}/work`, {
                      title: `Follow-up: ${w.title}`.slice(0, 120),
                      request: w.request,
                      acceptance: w.acceptance,
                      runner_id: w.runner_id,
                      model_approved: false,
                    })
                  }
                >
                  Create follow-up draft
                </Button>
              )}
              {w.publication_submission !== "draft" && (
                <p>
                  Publication task: {w.publication_execution.status} ·{" "}
                  {w.publication_submission}
                </p>
              )}
              {w.publication.state && (
                <p>
                  Publication: {w.publication.state}{" "}
                  {w.publication.pr_url && (
                    <a
                      href={w.publication.pr_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Review PR
                    </a>
                  )}
                </p>
              )}
            </article>
          ))}
        </div>
      )}
      {tab === "Changes" && (
        <div role="tabpanel">
          {data?.connections
            .filter((c) => c.provider === "github")
            .map((c) => (
              <section key={c.id}>
                <p>
                  GitHub evidence observed: {when(c.checked_at)} · {c.status}{" "}
                  {c.last_error}
                </p>
                {c.evidence.pull_requests?.map((p) => (
                  <p key={p.number}>
                    <a href={p.url} target="_blank" rel="noreferrer">
                      #{p.number} {p.title}
                    </a>{" "}
                    · {p.draft ? "draft" : p.state} · {p.head_sha?.slice(0, 12)}
                  </p>
                ))}
              </section>
            ))}
          <p>CI results describe checks. They do not prove a deployment.</p>
          {data?.ci.length === 0 && (
            <p>No CI evidence yet. Sync your GitHub connector.</p>
          )}
          {data?.ci.map((c) => (
            <p key={c.id}>
              <a href={c.url} target="_blank" rel="noreferrer">
                {c.commit_sha.slice(0, 12)} · {c.status}
              </a>{" "}
              · {when(c.deployed_at)}
            </p>
          ))}
        </div>
      )}
      {tab === "Releases" && (
        <div className="stack" role="tabpanel">
          <p>
            Your teammate deploys through the existing process. Verification
            compares the live build SHA and readiness for every registered
            service; it makes no deployment changes.
          </p>
          <form
            className="inline-form"
            onSubmit={async (e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              await act(`projects/${projectId}/releases`, {
                expected_sha: f.get("sha"),
              });
            }}
          >
            <label>
              Expected deployed commit
              <input
                name="sha"
                required
                pattern="[a-f0-9]{40}"
                minLength={40}
                maxLength={40}
                placeholder="Full 40-character commit SHA"
              />
            </label>
            <Button disabled={busy}>Record expected release</Button>
          </form>
          {data?.releases.map((r) => (
            <article key={r.id}>
              <strong>
                {r.expected_sha.slice(0, 12)} ·{" "}
                {r.evidence.status ?? "unverified"}
              </strong>
              <p>Checked: {r.checked_at ? when(r.checked_at) : "never"}</p>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => void act(`releases/${r.id}/verify`)}
              >
                Verify live release
              </Button>
              {r.evidence.services?.map((s) => (
                <p key={s.service}>
                  {s.service}: version {s.version.status}, readiness{" "}
                  {s.readiness}
                  {s.version.observed_sha
                    ? ` (${s.version.observed_sha.slice(0, 12)})`
                    : ""}
                </p>
              ))}
            </article>
          ))}
        </div>
      )}
      {tab === "Health" && (
        <div role="tabpanel">
          <p>
            Service observations and incident history appear below. A responsive
            API does not establish model availability.
          </p>
          {data?.services.map((s) => (
            <details key={s.id}>
              <summary>{s.name}: provider mapping</summary>
              <form
                className="inline-form"
                onSubmit={async (e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  await act(
                    `services/${s.id}`,
                    {
                      external_ref: {
                        ...s.external_ref,
                        version_url: f.get("version_url") || null,
                        readiness_url: f.get("readiness_url") || null,
                      },
                    },
                    "PATCH",
                  );
                }}
              >
                <label>
                  Version URL
                  <input
                    name="version_url"
                    type="url"
                    defaultValue={s.external_ref.version_url ?? ""}
                  />
                </label>
                <label>
                  Readiness URL
                  <input
                    name="readiness_url"
                    type="url"
                    defaultValue={s.external_ref.readiness_url ?? ""}
                  />
                </label>
                <Button disabled={busy}>Save mapping</Button>
              </form>
              <pre className="json">
                {JSON.stringify(s.external_ref, null, 2)}
              </pre>
            </details>
          ))}
          {data?.management.dependencies?.map((d) => (
            <p key={d.name}>
              {d.name}: {d.status} ·{" "}
              {d.observed_at ? when(d.observed_at) : "no dependency evidence"}
            </p>
          ))}
          {data?.management.blockers?.map((b) => (
            <p className="error-banner" key={b}>
              {b}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}
