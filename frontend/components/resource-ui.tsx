"use client";

import Link from "next/link";
import type { ReactNode } from "react";

const KNOWN = new Set([
  "healthy",
  "degraded",
  "down",
  "unknown",
  "disabled",
  "open",
  "acknowledged",
  "resolved",
  "critical",
  "major",
  "minor",
  "connected",
  "error",
  "unconfigured",
  "polling",
  "unavailable",
]);

export function Status({ value }: { value: string }) {
  const key = value.toLowerCase().replaceAll(" ", "_");
  return (
    <span className={`status ${KNOWN.has(key) ? `status-${key}` : "status-unknown"}`}>
      <span />
      {value.replaceAll("_", " ").toLowerCase()}
    </span>
  );
}

export function PageHeading({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions && <div className="heading-actions">{actions}</div>}
    </div>
  );
}

export function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="error-banner" role="alert">
      <strong>Request failed</strong>
      <span>{message}</span>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

export function Loading({ label = "Loading observations…" }: { label?: string }) {
  return <p className="subtle loading-line">{label}</p>;
}

export function when(value: string | null | undefined) {
  if (!value) return "never";
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function ago(value: string | null | undefined) {
  if (!value) return "never";
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

export function duration(value: string | null | undefined) {
  if (!value) return "—";
  const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}

export function ProjectLink({ id, name }: { id: string; name: string }) {
  return (
    <Link className="run-link" href={`/projects/${id}`}>
      <strong>{name}</strong>
    </Link>
  );
}

export function Counts({ project }: { project: { healthy_count: number; degraded_count: number; down_count: number; unknown_count: number; disabled_count: number } }) {
  return (
    <span className="counts">
      {project.healthy_count > 0 && <span className="count count-healthy">{project.healthy_count} up</span>}
      {project.degraded_count > 0 && <span className="count count-degraded">{project.degraded_count} degraded</span>}
      {project.down_count > 0 && <span className="count count-down">{project.down_count} down</span>}
      {project.unknown_count > 0 && <span className="count">{project.unknown_count} unknown</span>}
      {project.disabled_count > 0 && <span className="count">{project.disabled_count} unmonitored</span>}
    </span>
  );
}
