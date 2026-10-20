"use client";

import { useApi } from "@/lib/hooks";
import { Empty, ErrorBanner, Loading, Status } from "@/components/resource-ui";

type CatalogEntry = {
  name: string;
  version: number;
  description: string;
  schema_version: number | null;
  timeout_seconds: number | null;
  managed: boolean;
  task_count: number;
  task_types: string[];
};

type Schedule = Record<string, unknown>;

export default function WorkflowCatalog() {
  const catalog = useApi<CatalogEntry[]>("workflows/catalog");
  const schedules = useApi<Schedule[]>("schedules");

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-heading">
          <h2>Engine definitions</h2>
          <span className="subtle">every definition registered in Conductor</span>
        </div>
        {catalog.loading && !catalog.data ? (
          <Loading label="Reading definitions…" />
        ) : (catalog.data ?? []).length === 0 ? (
          <Empty title="No definitions returned">
            The engine reported no workflow definitions. Managed definitions are installed at
            API startup.
          </Empty>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Version</th>
                  <th>Scope</th>
                  <th>Tasks</th>
                  <th>Task types</th>
                  <th>Timeout</th>
                </tr>
              </thead>
              <tbody>
                {(catalog.data ?? []).map((entry) => (
                  <tr key={`${entry.name}-${entry.version}`}>
                    <td>
                      <strong>{entry.name}</strong>
                      <div className="subtle">{entry.description || "no description"}</div>
                    </td>
                    <td className="mono-cell">v{entry.version}</td>
                    <td>
                      <Status value={entry.managed ? "connected" : "unconfigured"} />
                      <span className="subtle"> {entry.managed ? "managed" : "read-only"}</span>
                    </td>
                    <td>{entry.task_count}</td>
                    <td className="mono-cell">{entry.task_types.join(", ")}</td>
                    <td className="mono-cell">{entry.timeout_seconds ?? "engine default"}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="form-help">
          Registration of new definitions is intentionally not exposed to the browser. Add
          definitions through reviewed backend code so arbitrary workflows cannot be executed.
        </p>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <h2>Conductor schedules</h2>
          <span className="subtle">read-only view of the engine scheduler</span>
        </div>
        <ErrorBanner message={schedules.error} />
        {schedules.loading && !schedules.data ? (
          <Loading label="Reading schedules…" />
        ) : (schedules.data ?? []).length === 0 ? (
          <Empty title="No schedules registered">
            The scheduler API responded with an empty list. Monitoring does not depend on it:
            the collector runs inside the API process.
          </Empty>
        ) : (
          <div className="timeline">
            {(schedules.data ?? []).map((schedule, index) => (
              <div className="timeline-event" key={index}>
                <time>{String(schedule.name ?? schedule.workflowName ?? "schedule")}</time>
                <span className="tag">{String(schedule.cronExpression ?? schedule.paused ? "paused" : "active")}</span>
                <div className="mono-cell">{JSON.stringify(schedule).slice(0, 160)}</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
