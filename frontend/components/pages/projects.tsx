"use client";

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import { api } from "@/lib/api";
import type { Cluster, Project } from "@/lib/types";
import {
  Counts,
  Empty,
  ErrorBanner,
  Loading,
  PageHeading,
  ProjectLink,
  Status,
  ago,
} from "@/components/resource-ui";
import { Button } from "@/components/ui/button";

export default function ProjectsPage() {
  const params = useSearchParams();
  const router = useRouter();
  const [importError, setImportError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [cluster, setCluster] = useState(params.get("cluster") ?? "");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const filters = new URLSearchParams();
  if (cluster) filters.set("cluster_id", cluster);
  if (status) filters.set("status", status);
  if (search) filters.set("q", search);
  const suffix = filters.toString() ? `?${filters}` : "";
  const { data, error, loading, reload } = useApi<Project[]>(
    `projects${suffix}`,
    { pollMs: 20000 },
  );
  const clusters = useApi<Cluster[]>("clusters");

  async function remove(project: Project) {
    if (
      !window.confirm(
        `Delete ${project.name} and its local service configuration? Associated run history remains available.`,
      )
    )
      return;
    try {
      await api(`projects/${project.id}`, { method: "DELETE" });
      await reload();
    } catch (e) {
      setImportError((e as Error).message);
    }
  }

  return (
    <main className="content">
      <PageHeading
        eyebrow="CONTROL PLANE / PROJECTS"
        title="Everything you build, organised."
        description="Projects group environments and services. Status comes from real checks, not estimates."
        actions={
          <>
            <Button
              variant="outline"
              disabled={importing}
              onClick={async () => {
                setImporting(true);
                try {
                  const p = await api<{ id: string }>(
                    "projects/import-sunflower",
                    { method: "POST", body: "{}" },
                  );
                  router.push(`/projects/${p.id}`);
                } catch (e) {
                  setImportError((e as Error).message);
                } finally {
                  setImporting(false);
                }
              }}
            >
              Import Sunflower Grove
            </Button>
            <Button variant="outline" onClick={() => void reload()}>
              Refresh
            </Button>
            <Link className="button button-primary" href="/projects/new">
              Add project
            </Link>
          </>
        }
      />
      <ErrorBanner message={error ?? importError} />
      <div className="toolbar" style={{ marginBottom: 14 }}>
        <input
          placeholder="Search projects"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          aria-label="Search projects"
        />
        <select
          value={cluster}
          onChange={(event) => setCluster(event.target.value)}
          aria-label="Filter by cluster"
        >
          <option value="">All clusters</option>
          {(clusters.data ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          <option value="healthy">Healthy</option>
          <option value="degraded">Degraded</option>
          <option value="down">Down</option>
          <option value="unknown">Unknown</option>
          <option value="disabled">Unmonitored</option>
        </select>
      </div>
      <section className="panel">
        {loading && !data ? (
          <Loading />
        ) : (data ?? []).length === 0 ? (
          <Empty title="No projects yet">
            Register your first project to start observing its services. You can
            add a GitHub repository, environments and health endpoints in one
            step.
          </Empty>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Project group</th>
                  <th>Status</th>
                  <th>Services</th>
                  <th>Incidents</th>
                  <th>Last deploy</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {(data ?? []).map((project) => (
                  <tr key={project.id}>
                    <td>
                      <ProjectLink id={project.id} name={project.name} />
                      {project.record_kind === "verification" && (
                        <span className="tag">verification record</span>
                      )}
                      <div className="subtle mono-cell">{project.slug}</div>
                    </td>
                    <td>
                      {project.cluster_name ?? (
                        <span className="subtle">unassigned</span>
                      )}
                    </td>
                    <td>
                      <Status value={project.status} />
                    </td>
                    <td>
                      <Counts project={project} />
                    </td>
                    <td>
                      {project.open_incidents > 0 ? (
                        <Status value="open" />
                      ) : (
                        <span className="subtle">none</span>
                      )}
                    </td>
                    <td className="mono-cell">
                      {project.last_deployed_at
                        ? ago(project.last_deployed_at)
                        : "never"}
                    </td>
                    <td>
                      <div className="inline-actions">
                        <Link
                          className="text-button"
                          href={`/projects/${project.id}`}
                        >
                          Inspect
                        </Link>
                        <button
                          className="text-button"
                          onClick={() => void remove(project)}
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
      </section>
    </main>
  );
}
