"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  Boxes,
  ChevronRight,
  Folder,
  LayoutDashboard,
  LogOut,
  Plug,
  Rocket,
  Server,
  Settings,
  ShieldAlert,
  Terminal,
  Workflow,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import type { Infrastructure } from "@/lib/types";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/projects", label: "Projects", icon: Folder },
  { href: "/clusters", label: "Clusters", icon: Boxes },
  { href: "/services", label: "Services", icon: Server },
  { href: "/deployments", label: "Deployments", icon: Rocket },
  { href: "/executions", label: "Executions", icon: Terminal },
  { href: "/workflows", label: "Workflows", icon: Workflow },
  { href: "/incidents", label: "Incidents", icon: ShieldAlert },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/settings", label: "Settings", icon: Settings },
];

type SessionState = "loading" | "authenticated" | "anonymous";

export default function AppShell({
  children,
  environment,
}: {
  children: ReactNode;
  environment: string;
}) {
  const pathname = usePathname();
  const [state, setState] = useState<SessionState>("loading");
  const [credential, setCredential] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [infra, setInfra] = useState<Infrastructure | null>(null);

  const check = useCallback(async () => {
    try {
      await api("session");
      setState("authenticated");
    } catch {
      setState("anonymous");
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  useEffect(() => {
    if (state !== "authenticated") return;
    const load = () =>
      api<Infrastructure>("infrastructure")
        .then(setInfra)
        .catch(() => setInfra(null));
    void load();
    const timer = setInterval(load, 30000);
    return () => clearInterval(timer);
  }, [state]);

  async function signIn(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("session", {
        method: "POST",
        body: JSON.stringify({ credential }),
      });
      setCredential("");
      await check();
    } catch (exception) {
      setError((exception as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  if (state === "loading")
    return (
      <main className="login">
        <section className="login-form">
          <p className="subtle">Checking your session…</p>
        </section>
      </main>
    );

  if (state === "anonymous")
    return (
      <main className="login">
        <div className="login-art">
          <div className="brand">
            <span className="brand-icon">
              <Workflow size={25} />
            </span>
            Orchestra AI<span className="brand-period">.</span>
          </div>
          <div>
            <span className="eyebrow">PERSONAL DEVELOPER CONTROL PLANE</span>
            <h1>
              Every project.
              <br />
              <em>One clear signal.</em>
            </h1>
            <p>
              Register your projects, watch real health checks, and investigate
              incidents with durable Conductor workflows.
            </p>
          </div>
          <small>ORCHESTRA AI / 02</small>
        </div>
        <section className="login-form">
          <ShieldAlert size={30} />
          <h2>Connect to your workspace</h2>
          <p>
            Enter the owner password or the API token from your private
            <code> .env</code>. The browser only ever receives an HTTP-only
            session cookie.
          </p>
          <form onSubmit={signIn}>
            <label htmlFor="credential">Owner password or API token</label>
            <input
              id="credential"
              type="password"
              autoComplete="current-password"
              required
              value={credential}
              onChange={(event) => setCredential(event.target.value)}
              placeholder="Enter OWNER_PASSWORD or CONTROL_PLANE_TOKEN"
            />
            {error && (
              <p role="alert" className="error-text">
                {error}
              </p>
            )}
            <Button disabled={busy} type="submit">
              {busy ? "Connecting…" : "Open control plane"}
            </Button>
          </form>
          <small>
            <span className="tiny-dot" />
            {environment === "hosted" ? "Protected hosted workspace" : "Private local deployment"}
          </small>
        </section>
      </main>
    );

  const current = NAV.find((item) =>
    item.href === "/" ? pathname === "/" : pathname.startsWith(item.href),
  );

  return (
    <div className="shell">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="Orchestra AI home">
          <span className="brand-icon">
            <Workflow size={22} />
          </span>
          Orchestra AI<span className="brand-period">.</span>
        </Link>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {NAV.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={active ? "nav-item active" : "nav-item"}
              >
                <item.icon size={17} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-note">
          <span className="sidebar-note-icon">
            <Zap size={18} />
          </span>
          <strong>Real observations only.</strong>
          <p>
            Health data comes from real checks.
            <br />
            Unknown stays unknown.
          </p>
        </div>
        <div className="sidebar-bottom">
          <span className={`live-dot ${infra?.engine.status === "connected" ? "" : "offline"}`} />
          <div>
            <strong>
              {infra?.engine.status === "connected" ? "Engine connected" : "Engine unavailable"}
            </strong>
            <small>Conductor OSS · PostgreSQL</small>
          </div>
        </div>
        <button
          className="signout"
          onClick={async () => {
            await fetch("/api/session", { method: "DELETE" });
            window.location.href = "/";
          }}
        >
          <LogOut size={14} /> Sign out
        </button>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{current?.label ?? "Overview"}</strong>
          </div>
          <div className="topbar-right">
            <span className="environment">
              <span className="tiny-dot" />{" "}
              {environment === "hosted" ? "Hosted environment" : "Local development"}
            </span>
            <span className="avatar">OA</span>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}
