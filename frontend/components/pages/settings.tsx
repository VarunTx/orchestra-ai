"use client";

import { useApi } from "@/lib/hooks";
import type { Cluster } from "@/lib/types";
import { Empty, ErrorBanner, Loading, PageHeading, Status, when } from "@/components/resource-ui";

type SettingsView = {
  monitoring: {
    enabled: boolean;
    tick_seconds: number;
    concurrency: number;
    retention_days: number;
    allow_private_targets: boolean;
  };
  auth: { password_login: boolean; session_ttl_hours: number; api_token_configured: boolean };
  providers: { gemini_enabled: boolean; gemini_model: string | null };
  secrets: { owner_password: string };
  version: string;
};

type AuditEntry = {
  id: number;
  at: string;
  actor: string;
  action: string;
  resource_type: string;
  resource_id: string;
  detail: Record<string, unknown>;
};

export default function SettingsPage() {
  const settings = useApi<SettingsView>("settings");
  const audit = useApi<AuditEntry[]>("audit?limit=50", { pollMs: 30000 });
  const clusters = useApi<Cluster[]>("clusters");

  return (
    <main className="content">
      <PageHeading
        eyebrow="CONTROL PLANE / SETTINGS"
        title="How this instance behaves."
        description="Read-only runtime configuration and the audit trail. Secrets are reported as configured or not, never displayed."
      />
      <ErrorBanner message={settings.error ?? audit.error} />
      <div className="stack">
        <section className="split-2">
          <div className="panel">
            <div className="panel-heading">
              <h2>Runtime</h2>
              <span className="tag">v{settings.data?.version ?? "—"}</span>
            </div>
            {settings.loading && !settings.data ? (
              <Loading label="Reading configuration…" />
            ) : (
              <dl className="kv">
                <dt>Monitoring collector</dt>
                <dd>{settings.data?.monitoring.enabled ? "enabled (runs in the API process)" : "disabled"}</dd>
                <dt>Tick / concurrency</dt>
                <dd>
                  {settings.data?.monitoring.tick_seconds}s · {settings.data?.monitoring.concurrency} parallel checks
                </dd>
                <dt>Observation retention</dt>
                <dd>{settings.data?.monitoring.retention_days} days</dd>
                <dt>Private targets</dt>
                <dd>{settings.data?.monitoring.allow_private_targets ? "allowed (development)" : "blocked by SSRF guard"}</dd>
                <dt>Password login</dt>
                <dd>{settings.data?.auth.password_login ? "enabled" : "disabled (API token only)"}</dd>
                <dt>Session lifetime</dt>
                <dd>{settings.data?.auth.session_ttl_hours} hours</dd>
                <dt>Gemini</dt>
                <dd>{settings.data?.providers.gemini_enabled ? `enabled · ${settings.data.providers.gemini_model}` : "disabled"}</dd>
                <dt>Owner password</dt>
                <dd>{settings.data?.secrets.owner_password}</dd>
              </dl>
            )}
          </div>
          <div className="panel">
            <div className="panel-heading">
              <h2>Clusters</h2>
              <span className="subtle">{clusters.data?.length ?? 0} groups</span>
            </div>
            {(clusters.data ?? []).map((cluster) => (
              <div className="timeline-event" key={cluster.id}>
                <time>{cluster.kind}</time>
                <span className="tag">{cluster.service_count} services</span>
                <div>
                  <strong>{cluster.name}</strong>
                  <div className="subtle">{cluster.project_count} projects</div>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>Audit trail</h2>
            <span className="subtle">owner and monitor actions</span>
          </div>
          {(audit.data ?? []).length === 0 ? (
            <Empty title="No recorded actions">
              Project, connector, incident and workflow changes are written here.
            </Empty>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Actor</th>
                    <th>Action</th>
                    <th>Resource</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {(audit.data ?? []).map((entry) => (
                    <tr key={entry.id}>
                      <td className="mono-cell">{when(entry.at)}</td>
                      <td>
                        <Status value={entry.actor === "monitor" ? "polling" : "connected"} />
                        <span className="subtle"> {entry.actor}</span>
                      </td>
                      <td>{entry.action}</td>
                      <td className="mono-cell">
                        {entry.resource_type} {entry.resource_id.slice(0, 8)}
                      </td>
                      <td className="mono-cell">{JSON.stringify(entry.detail).slice(0, 120)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
