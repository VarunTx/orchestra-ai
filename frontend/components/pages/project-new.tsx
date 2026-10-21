"use client";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ErrorBanner, PageHeading } from "@/components/resource-ui";
const STEPS = [
  "Repository",
  "Environments",
  "Running services",
  "Optional connections",
  "Setup summary",
];
export default function NewProjectPage() {
  const router = useRouter();
  const [step, setStep] = useState(0),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null);
  const [name, setName] = useState(""),
    [repo, setRepo] = useState(""),
    [branch, setBranch] = useState("main");
  const [environments, setEnvironments] = useState(["production"]);
  const [services, setServices] = useState<
    { name: string; health_url: string; environment: string }[]
  >([]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    if (step < 4) {
      setStep(step + 1);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const project = await api<{ id: string }>("projects", {
        method: "POST",
        body: JSON.stringify({
          name,
          repo_url: repo,
          repo_branch: branch,
          environments: environments.map((name) => ({ name, kind: name })),
          services: services.map((s) => ({
            ...s,
            kind: "web",
            monitoring_enabled: !!s.health_url,
          })),
        }),
      });
      router.push(`/projects/${project.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }
  return (
    <main className="content">
      <PageHeading
        eyebrow="PROJECTS / ADD"
        title="Add a project"
        description="Start with a GitHub repository and the URLs you want to monitor. Coding setup can wait."
        actions={
          <Link href="/projects" className="button button-outline">
            Cancel
          </Link>
        }
      />
      <ErrorBanner message={error} />
      <form
        className="panel form-card stack"
        onSubmit={submit}
        style={{ maxWidth: 800 }}
      >
        <nav aria-label="Project setup progress" className="toolbar">
          {STEPS.map((name, i) => (
            <Button
              key={name}
              type="button"
              variant={i === step ? "default" : "outline"}
              disabled={busy || i > step}
              onClick={() => setStep(i)}
            >
              {i + 1}. {name}
            </Button>
          ))}
        </nav>
        {step === 0 && (
          <>
            <label>
              Project name
              <input
                required
                maxLength={80}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              GitHub repository
              <input
                required
                type="url"
                pattern="https://github.com/[^/]+/[^/]+/?"
                placeholder="https://github.com/you/repo"
                value={repo}
                onChange={(e) => setRepo(e.target.value.replace(/\.git$/, ""))}
              />
            </label>
            <label>
              Default branch
              <input
                required
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
              />
            </label>
          </>
        )}
        {step === 1 && (
          <fieldset>
            <legend>Where does it run?</legend>
            {["development", "staging", "production"].map((n) => (
              <label className="checkbox-row" key={n}>
                <input
                  type="checkbox"
                  checked={environments.includes(n)}
                  onChange={(e) =>
                    setEnvironments(
                      e.target.checked
                        ? [...environments, n]
                        : environments.filter((x) => x !== n),
                    )
                  }
                />
                {n}
              </label>
            ))}
            <p>
              Select at least one environment. These are labels; Orchestra does
              not create hosting resources.
            </p>
          </fieldset>
        )}
        {step === 2 && (
          <>
            <p>
              Add each website or API you want checked. You can edit intervals
              and expected responses after setup.
            </p>
            {services.map((s, i) => (
              <fieldset key={i} className="stack">
                <legend>Service {i + 1}</legend>
                <label>
                  Service name
                  <input
                    required
                    value={s.name}
                    onChange={(e) =>
                      setServices(
                        services.map((x, j) =>
                          j === i ? { ...x, name: e.target.value } : x,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  Health endpoint
                  <input
                    type="url"
                    value={s.health_url}
                    onChange={(e) =>
                      setServices(
                        services.map((x, j) =>
                          j === i ? { ...x, health_url: e.target.value } : x,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  Environment
                  <select
                    value={s.environment}
                    onChange={(e) =>
                      setServices(
                        services.map((x, j) =>
                          j === i ? { ...x, environment: e.target.value } : x,
                        ),
                      )
                    }
                  >
                    {environments.map((n) => (
                      <option key={n}>{n}</option>
                    ))}
                  </select>
                </label>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    setServices(services.filter((_, j) => j !== i))
                  }
                >
                  Remove service {i + 1}
                </Button>
              </fieldset>
            ))}
            <Button
              type="button"
              variant="outline"
              onClick={() =>
                setServices([
                  ...services,
                  { name: "", health_url: "", environment: environments[0] },
                ])
              }
            >
              Add service
            </Button>
          </>
        )}
        {step === 3 && (
          <>
            <h2>Connections can be added later</h2>
            <p>
              Monitoring live URLs does not require GitHub credentials or a
              coding agent. After saving, connect selected projects under
              Integrations. Public GitHub reads can use an empty token.
            </p>
            <p>
              Coding uses a paired laptop. Release verification needs a version
              endpoint containing the deployed commit.
            </p>
          </>
        )}
        {step === 4 && (
          <>
            <h2>{name}</h2>
            <p>
              {repo} · {branch}
            </p>
            <p>Environments: {environments.join(", ")}</p>
            <ul>
              {services.map((s, i) => (
                <li key={i}>
                  {s.name} · {s.environment} ·{" "}
                  {s.health_url || "No monitoring URL yet"}
                </li>
              ))}
            </ul>
            <p>
              Monitoring starts for provided public URLs. GitHub sync, coding
              and release verification remain separate setup steps.
            </p>
          </>
        )}
        <div className="inline-actions">
          {step > 0 && (
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => setStep(step - 1)}
            >
              Back
            </Button>
          )}
          <Button disabled={busy || (step === 1 && !environments.length)}>
            {busy ? "Saving…" : step === 4 ? "Create project" : "Continue"}
          </Button>
        </div>
      </form>
    </main>
  );
}
