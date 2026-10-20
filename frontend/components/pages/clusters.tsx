"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Cluster } from "@/lib/types";
import { Empty, ErrorBanner, Loading, PageHeading } from "@/components/resource-ui";
import { Button } from "@/components/ui/button";

export default function ClustersPage() {
  const { data, error, loading, reload } = useApi<Cluster[]>("clusters", { pollMs: 30000 });
  const [message, setMessage] = useState<string | null>(null);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const values = new FormData(form);
    try {
      await api("clusters", {
        method: "POST",
        body: JSON.stringify({
          name: values.get("name"),
          kind: values.get("kind"),
          description: values.get("description") ?? "",
        }),
      });
      form.reset();
      setMessage(null);
      await reload();
    } catch (exception) {
      setMessage((exception as ApiError).message);
    }
  }

  async function remove(cluster: Cluster) {
    if (!window.confirm(`Delete the cluster "${cluster.name}"? Projects stay, unassigned.`)) return;
    try {
      await api(`clusters/${cluster.id}`, { method: "DELETE" });
      await reload();
    } catch (exception) {
      setMessage((exception as ApiError).message);
    }
  }

  return (
    <main className="content">
      <PageHeading
        eyebrow="CONTROL PLANE / CLUSTERS"
        title="Logical groups, honestly labelled."
        description="Clusters group projects. They are not Kubernetes clusters unless a connected provider discovers real infrastructure."
        actions={
          <Button variant="outline" onClick={() => void reload()}>
            Refresh
          </Button>
        }
      />
      <ErrorBanner message={error ?? message} />
      <div className="stack">
        <section className="card-list">
          {loading && !data && <Loading />}
          {(data ?? []).map((cluster) => (
            <div className="card" key={cluster.id}>
              <div className="section-title">
                <h3>{cluster.name}</h3>
                <span className="tag">{cluster.kind}</span>
              </div>
              <p className="muted">{cluster.description || "No description."}</p>
              <div className="counts">
                <span className="count">{cluster.project_count} projects</span>
                <span className="count">{cluster.service_count} services</span>
                {cluster.down_count > 0 && <span className="count count-down">{cluster.down_count} down</span>}
                {cluster.open_incidents > 0 && (
                  <span className="count count-down">{cluster.open_incidents} incidents</span>
                )}
              </div>
              <div className="inline-actions">
                <Link className="text-button" href={`/projects?cluster=${cluster.id}`}>
                  View projects
                </Link>
                <button className="text-button" onClick={() => void remove(cluster)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
          {(data ?? []).length === 0 && !loading && (
            <Empty title="No clusters yet">Create a logical group such as “Production Applications”.</Empty>
          )}
        </section>

        <section className="panel">
          <div className="panel-heading">
            <h2>New cluster</h2>
            <span className="subtle">logical, provider or local</span>
          </div>
          <form className="inline-form" onSubmit={create}>
            <label>
              Name
              <input name="name" required maxLength={80} placeholder="AI Services" />
            </label>
            <label>
              Kind
              <select name="kind" defaultValue="logical">
                <option value="logical">logical group</option>
                <option value="provider">provider environment</option>
                <option value="local">local development</option>
              </select>
            </label>
            <label>
              Description
              <input name="description" maxLength={500} placeholder="Optional context" />
            </label>
            <Button type="submit">Create cluster</Button>
          </form>
        </section>
      </div>
    </main>
  );
}
