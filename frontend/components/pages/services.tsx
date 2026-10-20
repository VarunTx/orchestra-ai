"use client";

import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Project, Service } from "@/lib/types";
import { Empty, ErrorBanner, Loading, PageHeading, Status, ago } from "@/components/resource-ui";
import { Button } from "@/components/ui/button";

export default function ServicesPage() {
  const [status, setStatus] = useState("");
  const [project, setProject] = useState("");
  const suffix = status || project ? `?${new URLSearchParams({ ...(status ? { status } : {}), ...(project ? { project_id: project } : {}) })}` : "";
  const { data, error, loading, reload } = useApi<Service[]>(`services${suffix}`, { pollMs: 10000 });
  const projects = useApi<Project[]>("projects");
  const [message, setMessage] = useState<string | null>(null);

  async function check(service: Service) {
    setMessage(null);
    try {
      const result = await api<{ observation: { status: string; message: string } }>(
        `services/${service.id}/check`,
        { method: "POST", body: "{}" },
      );
      setMessage(`${service.name}: ${result.observation.status} — ${result.observation.message}`);
      await reload();
    } catch (exception) {
      setMessage((exception as Error).message);
    }
  }

  return (
    <main className="content">
      <PageHeading
        eyebrow="CONTROL PLANE / SERVICES"
        title="Every endpoint you depend on."
        description="Each row is a real check result with its source and collection time. Providers that expose no health stay unknown."
        actions={
          <Button variant="outline" onClick={() => void reload()}>
            Refresh
          </Button>
        }
      />
      <ErrorBanner message={error ?? message} />
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          <option value="healthy">Healthy</option>
          <option value="degraded">Degraded</option>
          <option value="down">Down</option>
          <option value="unknown">Unknown</option>
          <option value="disabled">Monitoring disabled</option>
        </select>
        <select value={project} onChange={(event) => setProject(event.target.value)} aria-label="Filter by project">
          <option value="">All projects</option>
          {(projects.data ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </div>
      <section className="panel">
        {loading && !data ? (
          <Loading />
        ) : (data ?? []).length === 0 ? (
          <Empty title="No services match">
            Register services from a project page, or change the filters above.
          </Empty>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Project</th>
                  <th>Environment</th>
                  <th>Status</th>
                  <th>Last check</th>
                  <th>24h checks</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {(data ?? []).map((service) => (
                  <tr key={service.id}>
                    <td>
                      <strong>{service.name}</strong>
                      <div className="subtle mono-cell">
                        {service.kind} · {service.provider} · {service.health_url ?? "no URL"}
                      </div>
                    </td>
                    <td>
                      <Link className="run-link" href={`/projects/${service.project_id}`}>
                        <strong>{service.project_name}</strong>
                      </Link>
                    </td>
                    <td>{service.environment_name ?? "—"}</td>
                    <td>
                      <Status value={service.current_status} />
                    </td>
                    <td className="mono-cell">{ago(service.last_checked_at)}</td>
                    <td className="mono-cell">{service.observations_24h}</td>
                    <td>
                      <button
                        className="text-button"
                        disabled={!service.health_url}
                        onClick={() => void check(service)}
                      >
                        Check now
                      </button>
                    </td>
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
