"use client";

import { useApi } from "@/lib/hooks";
import type { Infrastructure } from "@/lib/types";
import { Empty, ErrorBanner, Loading, Status } from "@/components/resource-ui";

function percent(used?: number | null, max?: number | null) {
  if (!used || !max) return "not reported";
  return `${Math.round((used / max) * 100)}%`;
}

function uptime(seconds?: number) {
  if (seconds === undefined) return "not reported";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export default function EngineTelemetry() {
  const { data, error, loading } = useApi<Infrastructure>("infrastructure", { pollMs: 10000 });
  const telemetry = data?.engine.telemetry;

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Engine telemetry</h2>
        <span className="subtle">measured by Conductor, scraped from its Prometheus endpoint</span>
      </div>
      <ErrorBanner message={error} />
      {loading && !data ? (
        <Loading label="Reading engine metrics…" />
      ) : !telemetry || !telemetry.available ? (
        <Empty title="Engine metrics unavailable">
          {telemetry?.error ?? "The metrics endpoint did not respond."} Values are not estimated.
        </Empty>
      ) : (
        <div className="stack">
          <div className="kpi-grid">
            <div className="kpi">
              <span>Task execution (mean)</span>
              <strong>{telemetry.task_execution_ms ?? "—"} ms</strong>
              <small>since engine start</small>
            </div>
            <div className="kpi">
              <span>Queue wait (mean)</span>
              <strong>{telemetry.task_queue_wait_ms ?? "—"} ms</strong>
              <small>time between schedule and poll</small>
            </div>
            <div className="kpi">
              <span>Tasks in flight</span>
              <strong>{telemetry.tasks_in_flight ?? 0}</strong>
              <small>{telemetry.workflow_start_success ?? 0} workflows started</small>
            </div>
            <div className="kpi">
              <span>JVM heap</span>
              <strong>{percent(telemetry.heap_used_mb, telemetry.heap_max_mb)}</strong>
              <small>
                {telemetry.heap_used_mb ?? "—"} MB of {telemetry.heap_max_mb ?? "—"} MB · uptime{" "}
                {uptime(telemetry.uptime_seconds)}
              </small>
            </div>
          </div>

          <div className="split-2">
            <div>
              <div className="section-title">
                <h3>Task queues</h3>
                <span className="subtle">depth from /tasks/queue/size</span>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Queue</th>
                      <th>Depth</th>
                      <th>Polls</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(telemetry.queues ?? []).map((queue) => (
                      <tr key={queue.task}>
                        <td className="mono-cell">{queue.task}</td>
                        <td>{queue.depth === null ? <span className="subtle">unknown</span> : queue.depth}</td>
                        <td className="mono-cell">{telemetry.task_poll_total?.[queue.task] ?? 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div>
              <div className="section-title">
                <h3>Terminal outcomes</h3>
                <span className="subtle">counters since engine start</span>
              </div>
              {Object.keys(telemetry.workflow_failures ?? {}).length === 0 ? (
                <Empty title="No failed executions since start">
                  Counters reset whenever the engine restarts; that is not proof of health over time.
                </Empty>
              ) : (
                <div className="timeline">
                  {Object.entries(telemetry.workflow_failures ?? {}).map(([status, count]) => (
                    <div className="timeline-event" key={status}>
                      <time>{count}</time>
                      <Status value={status === "TIMED_OUT" ? "timed_out" : status.toLowerCase()} />
                      <div className="mono-cell">{status}</div>
                    </div>
                  ))}
                </div>
              )}
              <p className="form-help">
                Hidden metrics stay hidden: if a series is absent the dashboard shows “—”, never zero as a claim.
              </p>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
