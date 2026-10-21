"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { Button } from "@/components/ui/button";
import { Empty, ErrorBanner, Loading, Status } from "@/components/resource-ui";

const EXAMPLE = {
  name: "manual_recheck",
  version: 1,
  schemaVersion: 2,
  description: "Diagnose an incident and publish a report",
  inputParameters: ["service", "severity", "logs"],
  tasks: [
    {
      name: "cp_normalize_incident",
      taskReferenceName: "normalize",
      type: "SIMPLE",
      inputParameters: {
        service: "${workflow.input.service}",
        severity: "${workflow.input.severity}",
        logs: "${workflow.input.logs}",
      },
    },
    {
      name: "cp_diagnose_incident",
      taskReferenceName: "diagnose",
      type: "SIMPLE",
      inputParameters: { incident: "${normalize.output}" },
    },
    {
      name: "cp_publish_report",
      taskReferenceName: "report",
      type: "SIMPLE",
      inputParameters: {
        incident: "${normalize.output}",
        analysis: "${diagnose.output}",
      },
    },
  ],
};

type CatalogEntry = {
  name: string;
  version: number;
  description: string;
  schema_version: number | null;
  timeout_seconds: number | null;
  managed: boolean;
  runnable: boolean;
  dedicated_project_flow: boolean;
  task_count: number;
  task_types: string[];
};

type Schedule = Record<string, unknown>;

export default function WorkflowCatalog() {
  const catalog = useApi<CatalogEntry[]>("workflows/catalog");
  const schedules = useApi<Schedule[]>("schedules");
  const [draft, setDraft] = useState(JSON.stringify(EXAMPLE, null, 2));
  const [success, setSuccess] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState<CatalogEntry | null>(null);
  const [verification, setVerification] = useState(false);
  const [inputs, setInputs] = useState("{}");
  const [definition, setDefinition] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function register() {
    if (busy) return;
    setBusy(true);
    setMessage(null);
    setSuccess(false);
    try {
      let parsed: unknown;
      try {
        parsed = JSON.parse(draft);
      } catch {
        throw new Error("The editor does not contain valid JSON");
      }
      const result = await api<{ name: string; version: number }>(
        "workflows/definitions",
        {
          method: "POST",
          body: JSON.stringify({ definition: parsed }),
        },
      );
      setMessage(`Registered ${result.name} v${result.version}`);
      setSuccess(true);
      await catalog.reload();
    } catch (exception) {
      setMessage((exception as ApiError).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <section className="panel">
        <div className="panel-heading">
          <h2>Engine definitions</h2>
          <span className="subtle">
            every definition registered in Conductor
          </span>
        </div>
        {catalog.loading && !catalog.data ? (
          <Loading label="Reading definitions…" />
        ) : (catalog.data ?? []).length === 0 ? (
          <Empty title="No definitions returned">
            The engine reported no workflow definitions. Managed definitions are
            installed at API startup.
          </Empty>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Name / actions</th>
                  <th>Version</th>
                  <th>Scope</th>
                  <th>Tasks</th>
                  <th>Task types</th>
                  <th>Timeout</th>
                </tr>
              </thead>
              <tbody>
                {(catalog.data ?? []).map((entry) => (
                  <tr key={`${entry.name}-${entry.version}`}>
                    <td>
                      <strong>{entry.name}</strong>
                      {entry.runnable && (
                        <Button
                          variant="outline"
                          disabled={busy}
                          onClick={async () => {
                            setMessage(null);
                            setSuccess(false);
                            try {
                              const d = await api<{
                                inputParameters: string[];
                              }>(
                                `workflows/definitions/${entry.name}/${entry.version}`,
                              );
                              setSelected(entry);
                              setDefinition(d);
                              setInputs(
                                JSON.stringify(
                                  Object.fromEntries(
                                    d.inputParameters.map((n) => [
                                      n,
                                      n === "service"
                                        ? "example"
                                        : n === "logs"
                                          ? "Read-only diagnostic input"
                                          : n === "severity"
                                            ? "medium"
                                            : n === "incident"
                                              ? {
                                                  service: "example",
                                                  logs: "Read-only diagnostic input",
                                                }
                                              : "",
                                    ]),
                                  ),
                                  null,
                                  2,
                                ),
                              );
                            } catch (e) {
                              setMessage((e as Error).message);
                            }
                          }}
                        >
                          Inspect / run
                        </Button>
                      )}
                      <div className="subtle">
                        {entry.description || "no description"}
                      </div>
                    </td>
                    <td className="mono-cell">v{entry.version}</td>
                    <td>
                      <Status
                        value={entry.managed ? "connected" : "unconfigured"}
                      />
                      <span className="subtle">
                        {" "}
                        {entry.managed
                          ? "managed"
                          : entry.dedicated_project_flow
                            ? "project approval flow"
                            : entry.runnable
                              ? "permitted automation"
                              : "read-only"}
                      </span>
                    </td>
                    <td>{entry.task_count}</td>
                    <td className="mono-cell">{entry.task_types.join(", ")}</td>
                    <td className="mono-cell">
                      {entry.timeout_seconds ?? "engine default"}s
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="form-help">
          Use the validated editor below to register permitted worker tasks.
          Project coding uses its separate approval flow.
        </p>
      </section>

      {selected && (
        <section className="panel form-card stack">
          <h2>
            {selected.name} v{selected.version}
          </h2>
          <details>
            <summary>Validated definition</summary>
            <pre>{JSON.stringify(definition, null, 2)}</pre>
          </details>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={verification}
              onChange={(e) => setVerification(e.target.checked)}
            />
            Verification run
          </label>
          <label>
            Automation inputs JSON
            <textarea
              value={inputs}
              onChange={(e) => setInputs(e.target.value)}
            />
          </label>
          <Button
            disabled={busy}
            onClick={async () => {
              if (busy) return;
              setBusy(true);
              setSuccess(false);
              setMessage(null);
              try {
                const result = await api<{ workflowId: string }>(
                  `workflows/definitions/${selected.name}/${selected.version}/run`,
                  {
                    method: "POST",
                    body: JSON.stringify({
                      inputs: JSON.parse(inputs),
                      record_kind: verification ? "verification" : "project",
                    }),
                  },
                );
                window.location.href = `/executions?run=${result.workflowId}`;
              } catch (e) {
                setMessage((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Run permitted automation
          </Button>
        </section>
      )}
      <section className="panel">
        <div className="panel-heading">
          <h2>Conductor schedules</h2>
          <span className="subtle">read-only view of the engine scheduler</span>
        </div>
        <ErrorBanner message={schedules.error} />
        {schedules.loading && !schedules.data ? (
          <Loading label="Reading schedules…" />
        ) : schedules.error ? (
          <p className="form-help">
            Unavailable on this engine. No schedules have been confirmed.
          </p>
        ) : (schedules.data ?? []).length === 0 ? (
          <Empty title="No schedules registered">
            The scheduler API responded with an empty list. Monitoring does not
            depend on it: the collector runs inside the API process.
          </Empty>
        ) : (
          <div className="timeline">
            {(schedules.data ?? []).map((schedule, index) => (
              <div className="timeline-event" key={index}>
                <time>
                  {String(schedule.name ?? schedule.workflowName ?? "schedule")}
                </time>
                <span className="tag">
                  {String(
                    schedule.cronExpression ??
                      (schedule.paused ? "paused" : "active"),
                  )}
                </span>
                <div className="mono-cell">
                  {JSON.stringify(schedule).slice(0, 160)}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <h2>Register a definition</h2>
          <span className="subtle">worker-backed SIMPLE tasks only</span>
        </div>
        <p className="subtle">
          Definitions are validated server-side: only the four registered worker
          tasks are accepted, HTTP/Event/Sub-workflow tasks are rejected, and an
          existing name+version cannot be overwritten. Registering a new version
          is a reviewable code change in Conductor, not arbitrary execution.
        </p>
        <ErrorBanner message={message} success={success} />
        <textarea
          aria-label="Workflow definition JSON"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          spellCheck={false}
          style={{
            width: "100%",
            minHeight: 260,
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: 12,
            border: "1px solid var(--line)",
            borderRadius: 8,
            padding: 12,
            background: "#fff",
          }}
        />
        <div className="inline-actions" style={{ marginTop: 10 }}>
          <Button onClick={() => void register()} disabled={busy}>
            {busy ? "Validating…" : "Validate and register"}
          </Button>
          <button
            className="text-button"
            onClick={() => setDraft(JSON.stringify(EXAMPLE, null, 2))}
          >
            Reset example
          </button>
        </div>
      </section>
    </div>
  );
}
