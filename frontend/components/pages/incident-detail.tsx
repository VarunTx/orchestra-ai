"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Incident } from "@/lib/types";
import {
  Empty,
  ErrorBanner,
  Loading,
  PageHeading,
  Status,
  when,
} from "@/components/resource-ui";
import { Button } from "@/components/ui/button";

export default function IncidentDetail({ id }: { id: string }) {
  const { data, error, loading, reload } = useApi<Incident>(`incidents/${id}`, { pollMs: 10000 });
  const [message, setMessage] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function act(path: string, body: Record<string, unknown>, note: string) {
    setBusy(true);
    setMessage(null);
    try {
      await api(path, { method: "POST", body: JSON.stringify(body) });
      setMessage(note);
      await reload();
    } catch (exception) {
      setMessage((exception as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  async function note(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const value = String(new FormData(form).get("note") ?? "").trim();
    if (!value) return;
    await act(`incidents/${id}/notes`, { note: value }, "Note added");
    form.reset();
  }

  async function diagnose() {
    if (!data) return;
    setBusy(true);
    setMessage(null);
    try {
      const evidence = [
        `Incident ${data.title} on ${data.service_name} (${data.project_name}).`,
        `Severity ${data.severity}; status ${data.status}; opened ${data.opened_at}.`,
        `Detection: ${JSON.stringify(data.detection)}`,
        ...(data.observations ?? [])
          .slice(0, 10)
          .map((item) => `${item.observed_at} ${item.status} ${item.http_status ?? ""} ${item.message}`),
      ].join("\n");
      const result = await api<{ workflowId: string }>("executions", {
        method: "POST",
        body: JSON.stringify({
          name: "diagnostic_pipeline",
          service: data.service_name.slice(0, 100),
          severity: data.severity === "critical" ? "critical" : data.severity === "minor" ? "low" : "high",
          logs: evidence.slice(0, 20000),
          failure_mode: "none",
        }),
      });
      setWorkflow(result.workflowId);
      setMessage("Deterministic diagnostics started in Conductor");
    } catch (exception) {
      setMessage((exception as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading && !data)
    return (
      <main className="content">
        <Loading label="Loading incident…" />
      </main>
    );

  if (!data)
    return (
      <main className="content">
        <PageHeading eyebrow="INCIDENTS" title="Incident not found" description="It may not exist." />
        <ErrorBanner message={error} />
        <Link className="button button-outline" href="/incidents">
          Back to incidents
        </Link>
      </main>
    );

  const active = data.resolved_at === null;
  return (
    <main className="content">
      <PageHeading
        eyebrow="CONTROL PLANE / INCIDENTS / DETAIL"
        title={data.title}
        description={`${data.project_name} · ${data.service_name}`}
        actions={
          <>
            <Button variant="outline" onClick={() => void reload()}>
              Refresh
            </Button>
            <Link className="button button-outline" href="/incidents">
              All incidents
            </Link>
          </>
        }
      />
      <ErrorBanner message={error ?? message} />
      <div className="stack">
        <section className="panel">
          <div className="panel-heading">
            <h2>Status</h2>
            <div className="inline-actions">
              <Status value={data.severity} />
              <Status value={data.status} />
            </div>
          </div>
          <dl className="kv">
            <dt>Opened</dt>
            <dd>{when(data.opened_at)}</dd>
            <dt>Acknowledged</dt>
            <dd>{data.acknowledged_at ? when(data.acknowledged_at) : "not acknowledged"}</dd>
            <dt>Resolved</dt>
            <dd>{data.resolved_at ? when(data.resolved_at) : "still active"}</dd>
            <dt>Resolution</dt>
            <dd>{data.resolution_note ?? "—"}</dd>
            <dt>Failure threshold</dt>
            <dd>{String(data.detection?.threshold ?? "—")}</dd>
            <dt>Health URL</dt>
            <dd className="mono-cell">{data.health_url ?? "none"}</dd>
          </dl>
          <div className="inline-actions" style={{ marginTop: 12 }}>
            {active && data.status === "open" && (
              <Button
                disabled={busy}
                onClick={() => void act(`incidents/${id}/acknowledge`, { note: "Acknowledged from detail view" }, "Incident acknowledged")}
              >
                Acknowledge
              </Button>
            )}
            {active && (
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => void act(`incidents/${id}/resolve`, { note: "Resolved manually by the owner" }, "Incident resolved")}
              >
                Resolve
              </Button>
            )}
            <Button variant="outline" disabled={busy} onClick={() => void diagnose()}>
              Run deterministic diagnostics
            </Button>
            {workflow && (
              <Link className="button button-ghost" href={`/executions?run=${workflow}`}>
                Open execution {workflow.slice(0, 8)}
              </Link>
            )}
          </div>
        </section>

        <section className="split-2">
          <div className="panel">
            <div className="panel-heading">
              <h2>Timeline</h2>
              <span className="subtle">{(data.events ?? []).length} events</span>
            </div>
            {(data.events ?? []).length === 0 ? (
              <Empty title="No events">Detection evidence is stored with the incident.</Empty>
            ) : (
              <div className="timeline">
                {(data.events ?? []).map((event) => (
                  <div className="timeline-event" key={event.id}>
                    <time>{when(event.at)}</time>
                    <span className="tag">{event.kind}</span>
                    <div>
                      <strong>{event.message}</strong>
                      <div className="subtle">by {event.actor}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <form className="inline-form" onSubmit={note} style={{ marginTop: 12 }}>
              <label style={{ flex: 1 }}>
                Add a note
                <input name="note" maxLength={2000} placeholder="What did you find?" />
              </label>
              <Button type="submit" disabled={busy}>
                Add note
              </Button>
            </form>
          </div>

          <div className="panel">
            <div className="panel-heading">
              <h2>Detection evidence</h2>
              <span className="subtle">captured from a real check</span>
            </div>
            {(data.observations ?? []).length === 0 ? (
              <Empty title="No observations">The service has no recorded checks.</Empty>
            ) : (
              <div className="timeline">
                {(data.observations ?? []).slice(0, 12).map((observation) => (
                  <div className="timeline-event" key={observation.id}>
                    <time>{when(observation.observed_at)}</time>
                    <Status value={observation.status} />
                    <div>
                      <span className="mono-cell">
                        {observation.source} · {observation.http_status ?? "no status"} ·{" "}
                        {observation.latency_ms ?? "—"} ms
                      </span>
                      <div className="subtle">{observation.message}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <details style={{ marginTop: 12 }}>
              <summary className="subtle">Raw detection payload</summary>
              <pre className="json">{JSON.stringify(data.detection, null, 2)}</pre>
            </details>
          </div>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>Notifications</h2>
            <span className="subtle">webhook deliveries</span>
          </div>
          {(data.notifications ?? []).length === 0 ? (
            <Empty title="No notifications sent">
              Configure a webhook alert on Integrations. Delivery requires an explicit target.
            </Empty>
          ) : (
            <div className="timeline">
              {(data.notifications ?? []).map((notification) => (
                <div className="timeline-event" key={notification.id}>
                  <time>{when(notification.created_at)}</time>
                  <Status value={notification.status} />
                  <div>
                    <strong>{notification.channel}</strong>
                    <div className="subtle">{notification.error ?? "delivered"}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
