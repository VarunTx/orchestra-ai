"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import type { Cluster, Project } from "@/lib/types";
import { ErrorBanner, PageHeading } from "@/components/resource-ui";
import { Button } from "@/components/ui/button";

const ENVIRONMENTS = [
  { name: "development", kind: "development" },
  { name: "staging", kind: "staging" },
  { name: "production", kind: "production" },
];

export default function NewProjectPage() {
  const router = useRouter();
  const clusters = useApi<Cluster[]>("clusters");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string[]>(["production"]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const serviceName = String(form.get("service_name") ?? "").trim();
    const healthUrl = String(form.get("health_url") ?? "").trim();
    try {
      const project = await api<Project>("projects", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          description: form.get("description") ?? "",
          cluster_id: form.get("cluster_id") || null,
          repo_url: String(form.get("repo_url") ?? "").trim() || null,
          repo_branch: String(form.get("repo_branch") ?? "").trim() || null,
          environments: ENVIRONMENTS.filter((env) => selected.includes(env.name)).map((env) => ({
            name: env.name,
            kind: env.kind,
          })),
          services: serviceName
            ? [
                {
                  name: serviceName,
                  kind: form.get("service_kind") || "web",
                  health_url: healthUrl || null,
                  monitoring_enabled: Boolean(healthUrl),
                  check_interval_seconds: Number(form.get("check_interval_seconds") ?? 60),
                },
              ]
            : [],
        }),
      });
      router.push(`/projects/${project.id}`);
    } catch (exception) {
      setError((exception as ApiError).message);
      setBusy(false);
    }
  }

  return (
    <main className="content">
      <PageHeading
        eyebrow="CONTROL PLANE / PROJECTS / NEW"
        title="Register a project."
        description="One project, its environments, and the services you want observed. Everything is stored in the platform database."
        actions={<Link className="button button-outline" href="/projects">Cancel</Link>}
      />
      <ErrorBanner message={error} />
      <form className="panel form-card" onSubmit={submit} style={{ maxWidth: 760 }}>
        <div className="form-grid-2">
          <label>
            Project name
            <input name="name" required maxLength={80} placeholder="Checkout Platform" />
          </label>
          <label>
            Logical cluster
            <select name="cluster_id" defaultValue="">
              <option value="">Unassigned</option>
              {(clusters.data ?? []).map((cluster) => (
                <option key={cluster.id} value={cluster.id}>
                  {cluster.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label>
          Description
          <textarea name="description" maxLength={1000} placeholder="Subscriptions, invoicing and payment webhooks." />
        </label>
        <div className="form-grid-2">
          <label>
            GitHub repository
            <input name="repo_url" placeholder="https://github.com/you/repo" />
          </label>
          <label>
            Default branch
            <input name="repo_branch" placeholder="main" />
          </label>
        </div>
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="subtle" style={{ marginBottom: 8 }}>Deployment environments</legend>
          <div className="toolbar">
            {ENVIRONMENTS.map((env) => (
              <label key={env.name} className="checkbox-row" style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                <input
                  type="checkbox"
                  checked={selected.includes(env.name)}
                  onChange={(event) =>
                    setSelected((current) =>
                      event.target.checked
                        ? [...current, env.name]
                        : current.filter((name) => name !== env.name),
                    )
                  }
                />
                {env.name}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="panel" style={{ background: "#fbfcfb" }}>
          <div className="panel-heading">
            <h2>First service (optional)</h2>
            <span className="subtle">HTTP checks only run when a health URL is set</span>
          </div>
          <div className="form-grid-3">
            <label>
              Service name
              <input name="service_name" placeholder="Checkout API" />
            </label>
            <label>
              Kind
              <select name="service_kind" defaultValue="api">
                {["web", "api", "database", "worker", "queue", "cache", "external"].map((kind) => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Check interval (seconds)
              <input name="check_interval_seconds" type="number" min={15} max={86400} defaultValue={60} />
            </label>
          </div>
          <label>
            Health endpoint
            <input name="health_url" placeholder="https://api.example.com/healthz" />
          </label>
          <p className="form-help">
            Health checks are SSRF-protected: private and loopback targets are rejected unless
            HTTP_CHECK_ALLOW_PRIVATE is enabled by the operator.
          </p>
        </div>
        <div className="inline-actions">
          <Button type="submit" disabled={busy}>
            {busy ? "Saving…" : "Create project"}
          </Button>
          <Link className="button button-outline" href="/projects">
            Cancel
          </Link>
        </div>
      </form>
    </main>
  );
}
