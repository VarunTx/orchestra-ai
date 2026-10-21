"use client";

import Link from "next/link";
import { useApi } from "@/lib/hooks";
import type { Dashboard } from "@/lib/types";
import {
  Empty,
  ErrorBanner,
  Loading,
  PageHeading,
  ProjectLink,
  Status,
  ago,
  duration,
  when,
} from "@/components/resource-ui";
import { Button } from "@/components/ui/button";

export default function Overview() {
  const { data, error, loading, reload } = useApi<Dashboard>("dashboard", { pollMs: 15000 });

  return (
    <main className="content">
      <PageHeading
        eyebrow="CONTROL PLANE / OVERVIEW"
        title="What needs your attention."
        description="Real health checks, real incidents, real Conductor executions. Unknown stays unknown."
        actions={
          <>
            <Button variant="outline" onClick={() => void reload()}>
              Refresh
            </Button>
            <Link className="button button-primary" href="/projects/new">
              Add project
            </Link>
          </>
        }
      />
      <ErrorBanner message={error} />
      {loading && !data && <Loading />}
      {data && (
        <div className="stack">
          <section className="kpi-grid">
            <div className="kpi">
              <span>Projects</span>
              <strong>{data.totals.projects}</strong>
              <small>{data.totals.services} services registered</small>
            </div>
            <div className="kpi">
              <span>Healthy services</span>
              <strong>{data.totals.healthy}</strong>
              <small>
                {data.totals.degraded} degraded · {data.totals.down} down
              </small>
            </div>
            <div className={`kpi ${data.totals.active_incidents > 0 ? "alert" : ""}`}>
              <span>Active incidents</span>
              <strong>{data.totals.active_incidents}</strong>
              <small>{data.totals.stale} services with stale checks</small>
            </div>
            <div className="kpi">
              <span>Monitoring coverage</span>
              <strong>
                {data.totals.services - data.totals.disabled}/{data.totals.services}
              </strong>
              <small>
                {data.totals.unknown} unknown · {data.totals.connectors} connectors
              </small>
            </div>
          </section>

          <section className="split-2">
            <div className="panel">
              <div className="panel-heading">
                <h2>Needs attention</h2>
                <span className="subtle">worst first</span>
              </div>
              {data.needs_attention.length === 0 ? (
                <Empty title="Nothing is failing">
                  No service is currently down or degraded. New checks run every interval,
                  even with this tab closed.
                </Empty>
              ) : (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Service</th>
                        <th>Project</th>
                        <th>Status</th>
                        <th>Since</th>
                        <th>Last error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.needs_attention.map((service) => (
                        <tr key={service.id}>
                          <td>
                            <Link className="run-link" href={`/projects/${service.project_id}`}>
                              <strong>{service.name}</strong>
                            </Link>
                          </td>
                          <td>
                            <ProjectLink id={service.project_id} name={service.project_name} />
                          </td>
                          <td>
                            <Status value={service.current_status} />
                          </td>
                          <td className="mono-cell">{duration(service.last_checked_at)}</td>
                          <td className="mono-cell">{service.last_error ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="panel">
              <div className="panel-heading">
                <h2>Open incidents</h2>
                <Link className="text-button" href="/incidents">
                  All incidents
                </Link>
              </div>
              {data.incidents.length === 0 ? (
                <Empty title="No active incidents">
                  Incidents open automatically when a service crosses its failure threshold.
                </Empty>
              ) : (
                <div className="timeline">
                  {data.incidents.map((incident) => (
                    <div className="timeline-event" key={incident.id}>
                      <time>{when(incident.opened_at)}</time>
                      <Status value={incident.severity} />
                      <div>
                        <Link className="run-link" href={`/incidents/${incident.id}`}>
                          <strong>{incident.title}</strong>
                        </Link>
                        <div className="subtle">
                          {incident.project_name} · {incident.status}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="split-3">
            <div className="panel">
              <div className="panel-heading">
                <h2>Project groups</h2>
                <Link className="text-button" href="/clusters">
                  Manage
                </Link>
              </div>
              <div className="timeline">
                {data.clusters.map((cluster) => (
                  <div className="timeline-event" key={cluster.id}>
                    <time>{cluster.kind}</time>
                    <span className="tag">{cluster.projects} projects</span>
                    <div>
                      <strong>{cluster.name}</strong>
                      <div className="subtle">
                        {cluster.down > 0 ? `${cluster.down} services down` : "no down services"}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="panel">
              <div className="panel-heading">
                <h2>Recent deployments</h2>
                <Link className="text-button" href="/deployments">
                  History
                </Link>
              </div>
              {data.deployments.length === 0 ? (
                <Empty title="No deployments recorded">
                  Record a historical deployment under Deployments. Verify its commit separately in the project Releases tab.
                </Empty>
              ) : (
                <div className="timeline">
                  {data.deployments.map((deployment) => (
                    <div className="timeline-event" key={deployment.id}>
                      <time>{when(deployment.deployed_at)}</time>
                      <span className="tag">{deployment.provider}</span>
                      <div>
                        <ProjectLink id={deployment.project_id} name={deployment.project_name} />
                        <div className="subtle">
                          {deployment.status} · {deployment.commit_sha.slice(0, 7) || "no sha"}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="panel">
              <div className="panel-heading">
                <h2>Stale monitoring</h2>
                <span className="subtle">older than 3× interval</span>
              </div>
              {data.stale.length === 0 ? (
                <Empty title="Checks are current">Every monitored service reported recently.</Empty>
              ) : (
                <div className="timeline">
                  {data.stale.map((service) => (
                    <div className="timeline-event" key={service.id}>
                      <time>{ago(service.last_checked_at)}</time>
                      <span className="tag">{service.check_interval_seconds}s</span>
                      <div>
                        <strong>{service.name}</strong>
                        <div className="subtle">{service.project_name}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="panel">
            <div className="panel-heading">
              <h2>Recent failed runs</h2>
              {data.workflows.status === "unavailable" ? (
                <span className="tag">engine unavailable</span>
              ) : (
                <Link className="text-button" href="/executions">
                  Open runs
                </Link>
              )}
            </div>
            {data.workflows.status === "unavailable" ? (
              <Empty title="Conductor is not reachable">
                Failed executions cannot be listed right now. This is a monitoring gap,
                not a claim that nothing failed.
              </Empty>
            ) : data.workflows.failed.length === 0 ? (
              <Empty title="No failed executions in the latest search window">
                Conductor reported zero failed workflows of the two managed types.
              </Empty>
            ) : (
              <div className="timeline">
                {data.workflows.failed.map((run) => (
                  <div className="timeline-event" key={run.workflowId}>
                    <time>{when(String(run.startTime))}</time>
                    <Status value={run.status} />
                    <div>
                      <Link className="run-link" href={`/executions?run=${run.workflowId}`}>
                        <strong>{run.workflowType ?? run.workflowName}</strong>
                      </Link>
                      <div className="subtle mono-cell">{run.workflowId}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </main>
  );
}
