"use client";

import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Alert, Connector, Project } from "@/lib/types";
import { Empty, ErrorBanner, Loading, PageHeading, Status, when } from "@/components/resource-ui";
import { Button } from "@/components/ui/button";

export default function IntegrationsPage() {
  const connectors = useApi<Connector[]>("connectors", { pollMs: 30000 });
  const alerts = useApi<Alert[]>("alerts");
  const projects = useApi<Project[]>("projects");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function act(run: () => Promise<unknown>, note: string) {
    setBusy(true);
    setMessage(null);
    try {
      await run();
      setMessage(note);
      await connectors.reload();
      await alerts.reload();
    } catch (exception) {
      setMessage((exception as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function addConnector(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    await act(
      () =>
        api("connectors", {
          method: "POST",
          body: JSON.stringify({
            provider: values.get("provider"),
            name: values.get("name"),
            token: values.get("token"),
          }),
        }),
      "Connector saved. Credentials are sealed at rest and never returned.",
    );
    form.reset();
  }

  async function addAlert(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    await act(
      () =>
        api("alerts", {
          method: "POST",
          body: JSON.stringify({
            name: values.get("name"),
            target: values.get("target"),
            project_id: values.get("project_id") || null,
            min_severity: values.get("min_severity"),
            cooldown_seconds: Number(values.get("cooldown_seconds") ?? 900),
          }),
        }),
      "Webhook alert created",
    );
    form.reset();
  }

  return (
    <main className="content">
      <PageHeading
        eyebrow="CONTROL PLANE / INTEGRATIONS"
        title="Connect the providers you already use."
        description="Credentials stay server-side, sealed at rest. Validation and sync are explicit actions, never background guesses."
      />
      <ErrorBanner message={connectors.error ?? alerts.error ?? message} />
      <div className="stack">
        <section className="panel">
          <div className="panel-heading">
            <h2>Provider connectors</h2>
            <span className="subtle">read-only by default</span>
          </div>
          {connectors.loading && !connectors.data ? (
            <Loading />
          ) : (connectors.data ?? []).length === 0 ? (
            <Empty title="No connectors yet">
              Railway tokens read project and service inventory. GitHub tokens read repositories,
              commits and workflow runs. Docker uses a push agent.
            </Empty>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Provider</th>
                    <th>Status</th>
                    <th>Validated</th>
                    <th>Last sync</th>
                    <th>Detail</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(connectors.data ?? []).map((connector) => (
                    <tr key={connector.id}>
                      <td>
                        <strong>{connector.name}</strong>
                      </td>
                      <td>{connector.provider}</td>
                      <td>
                        <Status value={connector.status} />
                      </td>
                      <td className="mono-cell">{connector.last_validated_at ? when(connector.last_validated_at) : "never"}</td>
                      <td className="mono-cell">{connector.last_sync_at ? when(connector.last_sync_at) : "never"}</td>
                      <td className="mono-cell">
                        {connector.last_error ?? String(connector.config.notes ?? connector.config.account ?? "—")}
                      </td>
                      <td>
                        <div className="inline-actions">
                          {connector.provider !== "docker" && (
                            <>
                              <button
                                className="text-button"
                                disabled={busy}
                                onClick={() =>
                                  void act(
                                    () => api(`connectors/${connector.id}/validate`, { method: "POST", body: "{}" }),
                                    "Connector validated",
                                  )
                                }
                              >
                                Validate
                              </button>
                              <button
                                className="text-button"
                                disabled={busy}
                                onClick={() =>
                                  void act(
                                    () => api(`connectors/${connector.id}/sync`, { method: "POST", body: "{}" }),
                                    "Sync complete",
                                  )
                                }
                              >
                                Sync
                              </button>
                            </>
                          )}
                          <button
                            className="text-button"
                            disabled={busy}
                            onClick={() =>
                              void act(
                                () => api(`connectors/${connector.id}`, { method: "DELETE" }),
                                "Connector removed",
                              )
                            }
                          >
                            Remove
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <form className="inline-form" onSubmit={addConnector} style={{ marginTop: 14 }}>
            <label>
              Provider
              <select name="provider" defaultValue="railway">
                <option value="railway">Railway</option>
                <option value="github">GitHub</option>
                <option value="docker">Docker agent</option>
              </select>
            </label>
            <label>
              Name
              <input name="name" required maxLength={80} placeholder="Railway production" />
            </label>
            <label>
              Token
              <input name="token" type="password" required minLength={8} placeholder="project or account token" />
            </label>
            <Button type="submit" disabled={busy}>
              Save connector
            </Button>
          </form>
          <p className="form-help">
            Railway uses a project token against its public GraphQL API; the inventory query is
            exercised only when a valid token is present. GitHub supports optional tokens for
            private repositories and rate limits.
          </p>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>Webhook alerts</h2>
            <span className="subtle">deduplicated with a cooldown</span>
          </div>
          {(alerts.data ?? []).length === 0 ? (
            <Empty title="No alert targets">
              Notifications are never sent until you configure an explicit webhook target.
            </Empty>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Scope</th>
                    <th>Min severity</th>
                    <th>Cooldown</th>
                    <th>Last sent</th>
                    <th>Enabled</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {(alerts.data ?? []).map((alert) => (
                    <tr key={alert.id}>
                      <td>
                        <strong>{alert.name}</strong>
                      </td>
                      <td>{alert.project_name ?? "all projects"}</td>
                      <td>{alert.min_severity}</td>
                      <td>{alert.cooldown_seconds}s</td>
                      <td className="mono-cell">{alert.last_notified_at ? when(alert.last_notified_at) : "never"}</td>
                      <td>{alert.enabled ? "yes" : "no"}</td>
                      <td>
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() =>
                            void act(() => api(`alerts/${alert.id}`, { method: "DELETE" }), "Alert removed")
                          }
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <form className="inline-form" onSubmit={addAlert} style={{ marginTop: 14 }}>
            <label>
              Name
              <input name="name" required maxLength={80} placeholder="Ops webhook" />
            </label>
            <label>
              Target URL
              <input name="target" required type="url" placeholder="https://hooks.example.com/orchestra" />
            </label>
            <label>
              Project
              <select name="project_id" defaultValue="">
                <option value="">All projects</option>
                {(projects.data ?? []).map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Min severity
              <select name="min_severity" defaultValue="major">
                <option value="critical">critical</option>
                <option value="major">major</option>
                <option value="minor">minor</option>
              </select>
            </label>
            <label>
              Cooldown (s)
              <input name="cooldown_seconds" type="number" min={0} max={86400} defaultValue={900} />
            </label>
            <Button type="submit" disabled={busy}>
              Add alert
            </Button>
          </form>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>Local Docker agent</h2>
            <span className="subtle">for machines the platform cannot reach</span>
          </div>
          <p className="subtle">
            Create a Docker connector above and use its token as <code>X-Agent-Token</code>. The
            agent pushes observations; it never accepts commands from the platform.
          </p>
          <pre className="json">{`curl -X POST $ORCHESTRA_URL/api/agent/observations \\
  -H "Content-Type: application/json" \\
  -H "X-Agent-Token: $AGENT_TOKEN" \\
  -d '{"agent_key":"local-worker","status":"healthy","latency_ms":12,"message":"docker ps ok"}'`}</pre>
          <p className="form-help">
            Link a service to the agent by setting <code>external_ref.agentKey</code> on the
            service (for example <code>{'{"agentKey":"local-worker"}'}</code>).
          </p>
        </section>
      </div>
    </main>
  );
}
