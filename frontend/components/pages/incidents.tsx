"use client";

import Link from "next/link";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import type { Incident } from "@/lib/types";
import { Empty, ErrorBanner, Loading, PageHeading, Status, ago, duration } from "@/components/resource-ui";
import { Button } from "@/components/ui/button";

export default function IncidentsPage() {
  const [filter, setFilter] = useState("active");
  const { data, error, loading, reload } = useApi<Incident[]>(
    `incidents${filter ? `?status=${filter}` : ""}`,
    { pollMs: 10000 },
  );

  return (
    <main className="content">
      <PageHeading
        eyebrow="CONTROL PLANE / INCIDENTS"
        title="Failures worth a human look."
        description="One incident per continuing failure. Evidence is captured at detection, and recovery is recorded automatically."
        actions={
          <Button variant="outline" onClick={() => void reload()}>
            Refresh
          </Button>
        }
      />
      <ErrorBanner message={error} />
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <select value={filter} onChange={(event) => setFilter(event.target.value)} aria-label="Filter incidents">
          <option value="active">Active (open or acknowledged)</option>
          <option value="open">Open</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
          <option value="">All</option>
        </select>
      </div>
      <section className="panel">
        {loading && !data ? (
          <Loading />
        ) : (data ?? []).length === 0 ? (
          <Empty title="No incidents here">
            Incidents open automatically when a monitored service crosses its failure threshold.
          </Empty>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Incident</th>
                  <th>Project</th>
                  <th>Severity</th>
                  <th>Status</th>
                  <th>Opened</th>
                  <th>Duration</th>
                  <th>Events</th>
                </tr>
              </thead>
              <tbody>
                {(data ?? []).map((incident) => (
                  <tr key={incident.id}>
                    <td>
                      <Link className="run-link" href={`/incidents/${incident.id}`}>
                        <strong>{incident.title}</strong>
                      </Link>
                      <div className="subtle">{incident.service_name}</div>
                    </td>
                    <td>
                      <Link className="run-link" href={`/projects/${incident.project_id}`}>
                        <strong>{incident.project_name}</strong>
                      </Link>
                    </td>
                    <td>
                      <Status value={incident.severity} />
                    </td>
                    <td>
                      <Status value={incident.status} />
                    </td>
                    <td className="mono-cell">{ago(incident.opened_at)}</td>
                    <td className="mono-cell">{duration(incident.opened_at)}</td>
                    <td>{incident.event_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
