"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Deployment, Project } from "@/lib/types";
import { Empty, ErrorBanner, Loading, PageHeading, when } from "@/components/resource-ui";
import { Button } from "@/components/ui/button";

export default function DeploymentsPage() {
  const { data, error, loading, reload } = useApi<Deployment[]>("deployments?limit=100", { pollMs: 30000 });
  const projects = useApi<Project[]>("projects");
  const [success, setSuccess] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  async function record(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    try {
      await api("deployments", {
        method: "POST",
        body: JSON.stringify({
          project_id: values.get("project_id"),
          provider: values.get("provider") || "manual",
          version: String(values.get("version") ?? "").trim() || null,
          commit_sha: String(values.get("commit_sha") ?? "").trim(),
          status: values.get("status") || "succeeded",
          url: String(values.get("url") ?? "").trim() || null,
        }),
      });
      form.reset();
      setMessage("Deployment recorded. Verify its commit in the project Releases tab."); setSuccess(true);
      await reload();
    } catch (exception) {
      setMessage((exception as ApiError).message);
    }
  }

  return (
    <main className="content">
      <PageHeading
        eyebrow="CONTROL PLANE / DEPLOYMENTS"
        title="What shipped, and when."
        description="Deployments are recorded events from historical recordss or explicit writes. Nothing here is inferred."
        actions={
          <Button variant="outline" onClick={() => void reload()}>
            Refresh
          </Button>
        }
      />
      <ErrorBanner message={message ?? error} success={!!message && success} />
      <div className="stack">
        <section className="panel">
          {loading && !data ? (
            <Loading />
          ) : (data ?? []).length === 0 ? (
            <Empty title="No deployments recorded">
              Record a manual deployment event below. GitHub Actions checks appear under project Changes; verify deployed commits under Releases.
            </Empty>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Project</th>
                    <th>Provider</th>
                    <th>Status</th>
                    <th>Version</th>
                    <th>Commit</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {(data ?? []).map((deployment) => (
                    <tr key={deployment.id}>
                      <td className="mono-cell">{when(deployment.deployed_at)}</td>
                      <td>
                        <Link className="run-link" href={`/projects/${deployment.project_id}`}>
                          <strong>{deployment.project_name}</strong>
                        </Link>
                        {deployment.environment_name && (
                          <div className="subtle">{deployment.environment_name}</div>
                        )}
                      </td>
                      <td>{deployment.provider}</td>
                      <td>{deployment.status}</td>
                      <td>{deployment.version ?? "—"}</td>
                      <td className="mono-cell">{deployment.commit_sha.slice(0, 7) || "—"}</td>
                      <td>
                        {deployment.url && (
                          <a className="text-button" href={deployment.url} target="_blank" rel="noreferrer">
                            Open
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>Record a deployment</h2>
            <span className="subtle">audited event, no provider call</span>
          </div>
          <form className="inline-form" onSubmit={record}>
            <label>
              Project
              <select name="project_id" required defaultValue="">
                <option value="" disabled>
                  Select project
                </option>
                {(projects.data ?? []).map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Provider
              <input name="provider" defaultValue="manual" maxLength={40} />
            </label>
            <label>
              Version
              <input name="version" placeholder="v1.4.0" maxLength={200} />
            </label>
            <label>
              Commit SHA
              <input name="commit_sha" placeholder="abc1234" maxLength={80} />
            </label>
            <label>
              Status
              <select name="status" defaultValue="succeeded">
                {["succeeded", "failed", "in_progress", "unknown"].map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
            <label>
              URL
              <input name="url" placeholder="https://example.com" />
            </label>
            <Button type="submit" disabled={(projects.data ?? []).length === 0}>
              Record
            </Button>
          </form>
        </section>
      </div>
    </main>
  );
}
