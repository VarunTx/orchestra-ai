"use client";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Service, Observation, Connector } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  ErrorBanner,
  Loading,
  PageHeading,
  Status,
  when,
} from "@/components/resource-ui";
export default function ServiceDetail({ id }: { id: string }) {
  const state = useApi<Service>(`services/${id}`, { pollMs: 15000 });
  const history = useApi<Observation[]>(`services/${id}/observations`, {
    pollMs: 15000,
  });
  const connectors = useApi<Connector[]>("connectors");
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState<string | null>(null),
    [success, setSuccess] = useState(false);
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setMessage(null);
    setSuccess(false);
    const f = new FormData(e.currentTarget);
    try {
      await api(`services/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
          name: f.get("name"),
          health_url: f.get("health_url") || null,
          provider: f.get("provider"),
          connector_id: f.get("connector_id") || null,
          monitoring_enabled: f.get("enabled") === "on",
          check_interval_seconds: Number(f.get("interval")),
          expected_status: Number(f.get("expected")),
          timeout_seconds: Number(f.get("timeout")),
          failure_threshold: Number(f.get("failure")),
          recovery_threshold: Number(f.get("recovery")),
          external_ref: {
            ...JSON.parse(String(f.get("mapping"))),
            agentKey: f.get("agent_key") || null,
            version_url: f.get("version_url") || null,
            readiness_url: f.get("readiness_url") || null,
          },
        }),
      });
      setMessage("Service settings saved");
      setSuccess(true);
      await state.reload();
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const s = state.data;
  if (!s)
    return (
      <main className="content">
        <ErrorBanner message={state.error} />
        <Loading />
      </main>
    );
  const evidence = s as Service & {
    evidence_state: string;
    last_known_status: string;
  };
  return (
    <main className="content">
      <PageHeading
        eyebrow="SERVICE"
        title={s.name}
        description="Edit monitoring and provider links. These settings do not change your hosting."
        actions={
          <Link
            className="button button-outline"
            href={`/projects/${s.project_id}`}
          >
            Back to project
          </Link>
        }
      />
      <ErrorBanner
        message={message ?? state.error}
        success={!!message && success}
      />
      <p>
        Current evidence: <Status value={s.current_status} /> ·{" "}
        {evidence.evidence_state}. Last known result:{" "}
        {evidence.last_known_status} · Last healthy: {when(s.last_ok_at)}
      </p>
      <form className="panel form-card stack" onSubmit={save}>
        <div className="form-grid-2">
          <label>
            Service name
            <input name="name" required defaultValue={s.name} />
          </label>
          <label>
            Health endpoint
            <input
              type="url"
              name="health_url"
              defaultValue={s.health_url ?? ""}
            />
          </label>
        </div>
        <div className="form-grid-3">
          {[
            [
              "interval",
              "Monitoring interval (seconds)",
              s.check_interval_seconds,
              15,
              86400,
            ],
            ["expected", "Expected HTTP status", s.expected_status, 100, 599],
            ["timeout", "Timeout (seconds)", s.timeout_seconds, 1, 60],
            ["failure", "Failures before incident", s.failure_threshold, 1, 20],
            [
              "recovery",
              "Successes before recovery",
              s.recovery_threshold,
              1,
              20,
            ],
          ].map(([key, label, value, min, max]) => (
            <label key={String(key)}>
              {label}
              <input
                type="number"
                name={String(key)}
                required
                min={Number(min)}
                max={Number(max)}
                defaultValue={Number(value)}
              />
            </label>
          ))}
        </div>
        <label className="checkbox-row">
          <input
            type="checkbox"
            name="enabled"
            defaultChecked={s.monitoring_enabled}
          />
          Enable monitoring
        </label>
        <label>
          Docker container name
          <input
            name="agent_key"
            defaultValue={String(s.external_ref.agentKey ?? "")}
            placeholder="Exact name reported by docker ps -a"
          />
        </label>
        <label>
          Version endpoint
          <input
            name="version_url"
            type="url"
            defaultValue={String(s.external_ref.version_url ?? "")}
          />
        </label>
        <label>
          Readiness endpoint
          <input
            name="readiness_url"
            type="url"
            defaultValue={String(s.external_ref.readiness_url ?? "")}
          />
        </label>
        <details>
          <summary>Advanced: provider and resource mapping</summary>
          <div className="stack">
            <label>
              Provider
              <select name="provider" defaultValue={s.provider}>
                {["http", "railway", "github", "docker", "manual"].map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </label>
            <label>
              Connection
              <select name="connector_id" defaultValue={s.connector_id ?? ""}>
                <option value="">None</option>
                {connectors.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.provider})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Resource mapping JSON
              <textarea
                name="mapping"
                defaultValue={JSON.stringify(s.external_ref, null, 2)}
              />
            </label>
            <p>
              For Docker set agentKey to the exact container name. For release
              verification set version_url and readiness_url. Credentials belong
              in Integrations.
            </p>
          </div>
        </details>
        <Button disabled={busy}>{busy ? "Saving…" : "Save service"}</Button>
      </form>
      <section className="panel">
        <div className="panel-heading">
          <h2>Observation history</h2>
        </div>
        <ErrorBanner message={history.error} />
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Observed</th>
                <th>Result</th>
                <th>Source</th>
                <th>HTTP</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {history.data?.map((o) => (
                <tr key={o.id}>
                  <td>{when(o.observed_at)}</td>
                  <td>
                    <Status value={o.status} />
                  </td>
                  <td>{o.source}</td>
                  <td>{o.http_status ?? "—"}</td>
                  <td>{o.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {history.data?.length === 0 && <p>No observations yet.</p>}
      </section>
    </main>
  );
}
