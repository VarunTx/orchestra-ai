"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Cluster, Project, Service } from "@/lib/types";
import {
  Empty,
  ErrorBanner,
  Loading,
  PageHeading,
  Status,
  ago,
  when,
} from "@/components/resource-ui";
import { Button } from "@/components/ui/button";

export default function ProjectDetail({ id }: { id: string }) {
  const { data, error, loading, reload } = useApi<Project>(`projects/${id}`, { pollMs: 15000 });
  const clusters = useApi<Cluster[]>("clusters");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function act(action: () => Promise<unknown>, note?: string) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      if (note) setMessage(note);
      await reload();
    } catch (exception) {
      setMessage((exception as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function check(service: Service) {
    await act(async () => api(`services/${service.id}/check`, { method: "POST", body: "{}" }),
      `Checked ${service.name}`);
  }

  async function addService(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    await act(async () => {
      await api("services", {
        method: "POST",
        body: JSON.stringify({
          project_id: id,
          environment_id: data.get("environment_id") || null,
          name: data.get("name"),
          kind: data.get("kind"),
          health_url: String(data.get("health_url") ?? "").trim() || null,
          monitoring_enabled: Boolean(String(data.get("health_url") ?? "").trim()),
          check_interval_seconds: Number(data.get("check_interval_seconds") ?? 60),
          failure_threshold: Number(data.get("failure_threshold") ?? 2),
        }),
      });
      form.reset();
    }, "Service registered");
  }

  async function addEnvironment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    await act(async () => {
      await api(`projects/${id}/environments`, {
        method: "POST",
        body: JSON.stringify({ name: data.get("name"), kind: data.get("kind") }),
      });
      form.reset();
    }, "Environment added");
  }

  if (loading && !data)
    return (
      <main className="content">
        <Loading label="Loading project…" />
      </main>
    );

  if (!data)
    return (
      <main className="content">
        <PageHeading eyebrow="PROJECTS" title="Project not found" description="It may have been deleted." />
        <ErrorBanner message={error} />
        <Link className="button button-outline" href="/projects">
          Back to projects
        </Link>
      </main>
    );

  const services = data.services ?? [];
  return (
    <main className="content">
      <PageHeading
        eyebrow={`PROJECTS / ${data.slug.toUpperCase()}`}
        title={data.name}
        description={data.description || "No description yet."}
        actions={
          <>
            <Button variant="outline" onClick={() => void reload()}>
              Refresh
            </Button>
            <Link className="button button-outline" href="/projects">
              All projects
            </Link>
          </>
        }
      />
      <ErrorBanner message={error ?? message} />
      <div className="stack">
        <section className="panel">
          <div className="panel-heading">
            <h2>Project facts</h2>
            <Status value={data.status} />
          </div>
          <dl className="kv">
            <dt>Cluster</dt>
            <dd>{data.cluster_name ?? "Unassigned"}</dd>
            <dt>Repository</dt>
            <dd>
              {data.repo_url ? (
                <a href={data.repo_url} target="_blank" rel="noreferrer">
                  {data.repo_url.replace("https://github.com/", "")}
                </a>
              ) : (
                <span className="subtle">not linked</span>
              )}
            </dd>
            <dt>Environments</dt>
            <dd>{(data.environments ?? []).map((env) => `${env.name} (${env.kind})`).join(", ") || "none"}</dd>
            <dt>Services</dt>
            <dd>
              {data.service_count} total · {data.healthy_count} healthy · {data.down_count} down ·{" "}
              {data.unknown_count} unknown
            </dd>
            <dt>Open incidents</dt>
            <dd>{data.open_incidents}</dd>
            <dt>Last deployment</dt>
            <dd>{data.last_deployed_at ? when(data.last_deployed_at) : "never recorded"}</dd>
          </dl>
          <form
            className="inline-form"
            style={{ marginTop: 12 }}
            onSubmit={async (event) => {
              event.preventDefault();
              const value = new FormData(event.currentTarget).get("cluster_id");
              await act(
                () =>
                  api(`projects/${id}`, {
                    method: "PATCH",
                    body: JSON.stringify({ cluster_id: value || null }),
                  }),
                "Cluster updated",
              );
            }}
          >
            <label>
              Move to cluster
              <select name="cluster_id" defaultValue={data.cluster_id ?? ""}>
                <option value="">Unassigned</option>
                {(clusters.data ?? []).map((cluster) => (
                  <option key={cluster.id} value={cluster.id}>
                    {cluster.name}
                  </option>
                ))}
              </select>
            </label>
            <Button type="submit" variant="outline" disabled={busy}>
              Move
            </Button>
          </form>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>Edit project</h2>
            <span className="subtle">persisted through PATCH /api/projects</span>
          </div>
          <form
            className="inline-form"
            onSubmit={async (event) => {
              event.preventDefault();
              const values = new FormData(event.currentTarget);
              await act(
                () =>
                  api(`projects/${id}`, {
                    method: "PATCH",
                    body: JSON.stringify({
                      name: values.get("name"),
                      description: values.get("description") ?? "",
                      repo_url: String(values.get("repo_url") ?? "").trim() || null,
                      repo_branch: String(values.get("repo_branch") ?? "").trim() || null,
                    }),
                  }),
                "Project updated",
              );
            }}
          >
            <label>
              Name
              <input name="name" defaultValue={data.name} required maxLength={80} />
            </label>
            <label>
              Description
              <input name="description" defaultValue={data.description} maxLength={1000} />
            </label>
            <label>
              Repository
              <input name="repo_url" defaultValue={data.repo_url ?? ""} placeholder="https://github.com/owner/repo" />
            </label>
            <label>
              Branch
              <input name="repo_branch" defaultValue={data.repo_branch ?? ""} placeholder="main" />
            </label>
            <Button type="submit" variant="outline" disabled={busy}>
              Save
            </Button>
          </form>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>Services</h2>
            <span className="subtle">real observations only</span>
          </div>
          {services.length === 0 ? (
            <Empty title="No services registered">
              Add a service below. A health URL enables automatic monitoring; without one the
              service stays explicitly unknown.
            </Empty>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>Kind</th>
                    <th>Environment</th>
                    <th>Status</th>
                    <th>Last check</th>
                    <th>Interval</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {services.map((service) => (
                    <tr key={service.id}>
                      <td>
                        <strong>{service.name}</strong>
                        <div className="subtle mono-cell">{service.health_url ?? "no health URL"}</div>
                      </td>
                      <td>{service.kind}</td>
                      <td>{service.environment_name ?? "—"}</td>
                      <td>
                        <Status value={service.current_status} />
                        {service.consecutive_failures > 0 && (
                          <div className="subtle">{service.consecutive_failures} fails in a row</div>
                        )}
                      </td>
                      <td className="mono-cell">{ago(service.last_checked_at)}</td>
                      <td className="mono-cell">{service.check_interval_seconds}s</td>
                      <td>
                        <div className="inline-actions">
                          <button
                            className="text-button"
                            disabled={busy || !service.health_url}
                            onClick={() => void check(service)}
                          >
                            Check now
                          </button>
                          <button
                            className="text-button"
                            disabled={busy}
                            onClick={() =>
                              void act(
                                () =>
                                  api(`services/${service.id}`, {
                                    method: "PATCH",
                                    body: JSON.stringify({
                                      monitoring_enabled: !service.monitoring_enabled,
                                    }),
                                  }),
                                service.monitoring_enabled ? "Monitoring disabled" : "Monitoring enabled",
                              )
                            }
                          >
                            {service.monitoring_enabled ? "Disable" : "Enable"}
                          </button>
                          <button
                            className="text-button"
                            disabled={busy}
                            onClick={() =>
                              void act(
                                () => api(`services/${service.id}`, { method: "DELETE" }),
                                "Service deleted",
                              )
                            }
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <form className="inline-form" onSubmit={addService} style={{ marginTop: 14 }}>
            <label>
              Service name
              <input name="name" required maxLength={80} placeholder="Payments worker" />
            </label>
            <label>
              Kind
              <select name="kind" defaultValue="web">
                {["web", "api", "database", "worker", "queue", "cache", "external"].map((kind) => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Environment
              <select name="environment_id" defaultValue={data.environments?.[0]?.id ?? ""}>
                <option value="">none</option>
                {(data.environments ?? []).map((env) => (
                  <option key={env.id} value={env.id}>
                    {env.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Health URL
              <input name="health_url" placeholder="https://example.com/healthz" />
            </label>
            <label>
              Interval (s)
              <input name="check_interval_seconds" type="number" min={15} max={86400} defaultValue={60} />
            </label>
            <label>
              Failure threshold
              <input name="failure_threshold" type="number" min={1} max={20} defaultValue={2} />
            </label>
            <Button type="submit" disabled={busy}>
              Add service
            </Button>
          </form>
        </section>

        <section className="split-2">
          <div className="panel">
            <div className="panel-heading">
              <h2>Incidents</h2>
              <Link className="text-button" href="/incidents">
                All incidents
              </Link>
            </div>
            {(data.incidents ?? []).length === 0 ? (
              <Empty title="No incidents recorded">Incidents appear when a check crosses its failure threshold.</Empty>
            ) : (
              <div className="timeline">
                {(data.incidents ?? []).map((incident) => (
                  <div className="timeline-event" key={incident.id}>
                    <time>{when(incident.opened_at)}</time>
                    <Status value={incident.status} />
                    <div>
                      <Link className="run-link" href={`/incidents/${incident.id}`}>
                        <strong>{incident.title}</strong>
                      </Link>
                      <div className="subtle">
                        {incident.severity} · {incident.event_count} events
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div className="panel">
            <div className="panel-heading">
              <h2>Deployments</h2>
              <Link className="text-button" href="/deployments">
                History
              </Link>
            </div>
            {(data.deployments ?? []).length === 0 ? (
              <Empty title="No deployments recorded">
                Deployments come from a GitHub connector sync or the deployments API.
              </Empty>
            ) : (
              <div className="timeline">
                {(data.deployments ?? []).map((deployment) => (
                  <div className="timeline-event" key={deployment.id}>
                    <time>{when(deployment.deployed_at)}</time>
                    <span className="tag">{deployment.provider}</span>
                    <div>
                      <strong>{deployment.status}</strong>
                      <div className="subtle mono-cell">
                        {deployment.commit_sha.slice(0, 7) || "no sha"}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>Environments</h2>
            <span className="subtle">development · staging · production</span>
          </div>
          <div className="toolbar">
            {(data.environments ?? []).map((env) => (
              <span className="tag" key={env.id}>
                {env.name} · {env.kind} · {env.service_count} services
              </span>
            ))}
            {(data.environments ?? []).length === 0 && <span className="subtle">No environments yet.</span>}
          </div>
          <form className="inline-form" onSubmit={addEnvironment} style={{ marginTop: 14 }}>
            <label>
              New environment
              <input name="name" required maxLength={60} placeholder="preview" />
            </label>
            <label>
              Kind
              <select name="kind" defaultValue="custom">
                {["development", "staging", "production", "custom"].map((kind) => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </label>
            <Button type="submit" disabled={busy}>
              Add environment
            </Button>
          </form>
        </section>
      </div>
    </main>
  );
}
