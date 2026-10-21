import { test, expect, type Page, type BrowserContext } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const token = fs
  .readFileSync(path.resolve(__dirname, "../../.env"), "utf8")
  .match(/^CONTROL_PLANE_TOKEN=(.+)$/m)![1]
  .trim();
let cachedCookies: Awaited<ReturnType<BrowserContext["cookies"]>> | null = null;
async function signIn(page: Page) {
  if (cachedCookies) await page.context().addCookies(cachedCookies);
  await page.goto("/");
  if (!cachedCookies) {
    await page.getByLabel("Owner password or API token").fill(token);
    await page.getByRole("button", { name: "Open control plane" }).click();
  }
  await expect(
    page.getByRole("heading", { name: "What needs your attention." }),
  ).toBeVisible();
  cachedCookies = await page.context().cookies();
}

test("shared navigation and controls fit at every supported width", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/executions");
  await expect(page.locator(".loading-line")).toHaveCount(0);
  await expect(page.locator(".runs-panel .run-link").first()).toBeVisible();
  for (const width of [390, 650, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const nav = page.getByRole("link", { name: "Runs", exact: true });
    await expect(nav).toBeVisible();
    for (const control of await page
      .locator("main button:visible, main input:visible, main select:visible")
      .all()) {
      const box = await control.boundingBox();
      expect(box, await control.innerText()).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
    }
    await page.screenshot({
      path: `../docs/screenshots/stabilization-runs-${width}.png`,
    });
    await page
      .getByRole("button", { name: "Run automation", exact: true })
      .click();
    const dialog = page.getByRole("dialog");
    for (const control of await dialog
      .locator("button:visible,input:visible,textarea:visible,select:visible")
      .all()) {
      await control.scrollIntoViewIfNeeded();
      const box = await control.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
    }
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  }
  await page.getByRole("link", { name: "Infrastructure", exact: true }).click();
  await expect(page).toHaveURL(/\/infrastructure/);
});

test("two generic projects, service editing, draft work and URL tabs work without a runner", async ({
  page,
}) => {
  await signIn(page);
  const ids: string[] = [];
  const headers = { Origin: "http://127.0.0.1:3000" };
  try {
    for (const repository of ["example/first", "example/second"]) {
      await page.goto("/projects/new");
      await page
        .getByLabel("Project name")
        .fill("Verification " + repository + " " + Date.now());
      await page
        .getByLabel("GitHub repository")
        .fill("https://github.com/" + repository);
      await page.getByRole("button", { name: "Continue", exact: true }).click();
      await page.getByRole("button", { name: "Continue", exact: true }).click();
      await page
        .getByRole("button", { name: "Add service", exact: true })
        .click();
      await page.getByLabel("Service name").fill("Local setup service");
      await page.getByRole("button", { name: "Continue", exact: true }).click();
      await page.getByRole("button", { name: "Continue", exact: true }).click();
      await page
        .getByRole("button", { name: "Create project", exact: true })
        .click();
      await expect(page).toHaveURL(/\/projects\/[0-9a-f-]{36}$/);
      const id = new URL(page.url()).pathname.split("/").pop()!;
      ids.push(id);
      await page.request.patch(`/api/projects/${id}`, {
        headers,
        data: { record_kind: "verification" },
      });
      await page
        .getByLabel("Title", { exact: true })
        .fill("Draft without laptop");
      await page
        .getByLabel("Requested change", { exact: true })
        .fill("Update documentation after laptop setup");
      await page
        .getByLabel("Acceptance criteria", { exact: true })
        .fill("Documentation describes the existing behavior");
      await page
        .getByRole("button", { name: "Create request", exact: true })
        .click();
      await expect(
        page.getByRole("heading", {
          name: "Draft without laptop",
          exact: true,
        }),
      ).toBeVisible();
      await page
        .getByRole("button", { name: "Start work", exact: true })
        .click();
      await expect(page.locator(".error-banner")).toContainText(
        "Approve model usage",
      );
      await page.getByRole("tab", { name: "Changes", exact: true }).click();
      await expect(page).toHaveURL(/tab=Changes/);
      await page.reload();
      await expect(
        page.getByRole("tab", { name: "Changes", exact: true }),
      ).toHaveAttribute("aria-selected", "true");
      await page.getByRole("tab", { name: "Health", exact: true }).click();
      await page.goBack();
      await expect(
        page.getByRole("tab", { name: "Changes", exact: true }),
      ).toHaveAttribute("aria-selected", "true");
      const services = await (
        await page.request.get(`/api/services?project_id=${id}`)
      ).json();
      await page.goto(`/services/${services[0].id}`);
      await page.getByLabel("Monitoring interval (seconds)").fill("120");
      await page.getByLabel("Expected HTTP status").fill("204");
      await page
        .getByLabel("Docker container name")
        .fill("synthetic-container");
      await page
        .getByRole("button", { name: "Save service", exact: true })
        .click();
      await expect(page.locator(".success-banner")).toContainText(
        "Service settings saved",
      );
      const updated = await (
        await page.request.get(`/api/services/${services[0].id}`)
      ).json();
      expect(updated.expected_status).toBe(204);
      expect(updated.check_interval_seconds).toBe(120);
      expect(updated.external_ref.agentKey).toBe("synthetic-container");
      await expect(
        page.getByRole("heading", { name: "Observation history" }),
      ).toBeVisible();
    }
  } finally {
    for (const id of ids)
      await page.request.delete(`/api/projects/${id}`, { headers });
  }
});

test("existing screens expose reachable controls at four widths and handle session expiry", async ({
  page,
}) => {
  await signIn(page);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  for (const route of [
    "/projects",
    "/services",
    "/deployments",
    "/executions",
    "/workflows",
    "/clusters",
    "/incidents",
    "/integrations",
    "/settings",
    "/infrastructure",
    "/projects/new",
  ]) {
    const primary: Record<string, string[]> = {
      "/projects": ["projects"],
      "/services": ["services"],
      "/deployments": ["deployments"],
      "/executions": ["executions", "infrastructure", "workflows"],
      "/workflows": ["workflows", "workflows/catalog", "infrastructure"],
      "/clusters": ["clusters"],
      "/incidents": ["incidents"],
      "/integrations": ["connectors", "alerts", "projects", "notifications"],
      "/settings": ["settings", "audit"],
      "/infrastructure": ["infrastructure", "workflows", "executions"],
      "/projects/new": [],
    };
    const loaded = primary[route].map((path) =>
      page
        .waitForResponse(
          (r) =>
            new URL(r.url()).pathname === `/api/${path}` &&
            r.request().method() === "GET",
        )
        .then((r) => r.finished()),
    );
    await page.goto(route);
    await Promise.all(loaded);
    await expect(page.locator(".loading-line")).toHaveCount(0);
    if (route === "/executions")
      await expect(page.locator(".runs-panel")).toBeVisible();
    if (route === "/workflows")
      await expect(page.locator(".dag-node").first()).toBeVisible();
    if (route === "/infrastructure")
      await expect(
        page.getByRole("heading", { name: "Python worker fleet" }),
      ).toBeVisible();
    await expect(page.locator("main").first()).toBeVisible();
    for (const width of [390, 650, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const control of await page
        .locator(
          "main button:visible,main input:visible,main select:visible,main textarea:visible",
        )
        .all()) {
        await control.scrollIntoViewIfNeeded();
        const box = await control.boundingBox();
        expect(
          box,
          `${route} ${width}: ${await control.getAttribute("name")}`,
        ).not.toBeNull();
        expect(box!.x, `${route} ${width}: left`).toBeGreaterThanOrEqual(-1);
        expect(
          box!.x + box!.width,
          `${route} ${width}: right`,
        ).toBeLessThanOrEqual(width + 1);
      }
    }
  }
  expect(errors).toEqual([]);
  await page.route("**/api/services", (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Expired" }),
    }),
  );
  await page.goto("/services");
  await expect(
    page.getByRole("button", { name: "Open control plane" }),
  ).toBeVisible();
});

test("an unavailable run keeps its explanation across background refresh", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/executions?run=11111111-1111-4111-8111-111111111111");
  await expect(page.locator(".error-banner")).toContainText(
    "Run evidence unavailable",
  );
  await page.getByRole("button", { name: "Refresh executions" }).click();
  await expect(page.locator(".error-banner")).toContainText(
    "Run evidence unavailable",
  );
  await expect(page).toHaveURL(/run=11111111/);
});

test("validated automation editor runs deterministic tasks through Conductor", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/workflows");
  const editor = page.getByLabel("Workflow definition JSON");
  await expect(editor).toBeVisible();
  const definition = JSON.parse(await editor.inputValue());
  definition.name = "verification_recheck_" + Date.now();
  await editor.fill(JSON.stringify(definition));
  await page
    .getByRole("button", { name: "Validate and register", exact: true })
    .click();
  await expect(page.locator(".success-banner")).toContainText(
    "Registered " + definition.name,
  );
  const row = page.locator("tbody tr", { hasText: definition.name });
  await row.getByRole("button", { name: "Inspect / run", exact: true }).click();
  await page.getByLabel("Verification run", { exact: true }).check();
  await page
    .getByRole("button", { name: "Run permitted automation", exact: true })
    .click();
  await expect(page).toHaveURL(/executions\?run=/);
  await expect(page.locator(".execution-title .status")).toHaveText(
    "completed",
    { timeout: 30000 },
  );
  await expect(
    page.getByText("verification record", { exact: false }).first(),
  ).toBeVisible();
});

test("public connector setup shows success and retains a provider failure", async ({
  page,
}) => {
  await signIn(page);
  const headers = { Origin: "http://127.0.0.1:3000" };
  const p = await (
    await page.request.post("/api/projects", {
      headers,
      data: {
        name: "Connection verification " + Date.now(),
        repo_url: "https://github.com/example/fixture",
      },
    })
  ).json();
  let id: string | undefined;
  try {
    await page.request.patch(`/api/projects/${p.id}`, {
      headers,
      data: { record_kind: "verification" },
    });
    await page.goto("/integrations");
    const form = page.locator("form").filter({
      has: page.getByRole("button", { name: "Save connector", exact: true }),
    });
    await form.locator('select[name="provider"]').selectOption("github");
    await form
      .locator('input[name="name"]')
      .fill("Public verification " + Date.now());
    await form
      .getByLabel("Connection projects", { exact: true })
      .selectOption(p.id);
    await form
      .getByRole("button", { name: "Save connector", exact: true })
      .click();
    await expect(page.locator(".success-banner")).toContainText(
      "Connector saved",
    );
    const all = await (await page.request.get("/api/connectors")).json();
    const c = all.find((c: { project_ids: string[] }) =>
      c.project_ids.includes(p.id),
    );
    id = c.id;
    expect((await page.request.get("/api/notifications")).status()).toBe(200);
    expect(
      (
        await page.request.put(`/api/connectors/${id}/projects`, {
          headers,
          data: { project_ids: [p.id] },
        })
      ).status(),
    ).toBe(200);
    await page.route(`**/api/connectors/${id}/sync`, (route) =>
      route.fulfill({
        status: 502,
        contentType: "application/json",
        body: JSON.stringify({
          detail:
            "Synthetic GitHub permission failure; reconnect the selected repository",
        }),
      }),
    );
    await page
      .locator("tbody tr", { hasText: c.name })
      .getByRole("button", { name: "Sync", exact: true })
      .click();
    await expect(page.locator(".error-banner")).toContainText(
      "Synthetic GitHub permission failure",
    );
  } finally {
    if (id) await page.request.delete(`/api/connectors/${id}`, { headers });
    await page.request.delete(`/api/projects/${p.id}`, { headers });
  }
});

test("website requests an exact-commit publication task and shows its failure without a remote write", async ({
  page,
}) => {
  await signIn(page);
  const headers = { Origin: "http://127.0.0.1:3000" };
  const p = await (
    await page.request.post("/api/projects", {
      headers,
      data: {
        name: "Publication verification " + Date.now(),
        repo_url: "https://github.com/example/fixture",
      },
    })
  ).json();
  const pair = await (
    await page.request.post(`/api/projects/${p.id}/runners`, {
      headers,
      data: { name: "Synthetic queue fixture" },
    })
  ).json();
  const runnerHeaders = { "X-Runner-Token": pair.token };
  const api = "http://127.0.0.1:8000/api";
  const sha = "a".repeat(40);
  let work: { id: string } | undefined;
  try {
    await page.request.patch(`/api/projects/${p.id}`, {
      headers,
      data: { record_kind: "verification" },
    });
    await page.request.post(`${api}/runner/preflight`, {
      headers: runnerHeaders,
      data: {
        checks: [
          {
            name: "Synthetic test only",
            ok: true,
            detail: "No model or publication process",
          },
        ],
        publication_ready: true,
      },
    });
    work = await (
      await page.request.post(`/api/projects/${p.id}/work`, {
        headers,
        data: {
          runner_id: pair.id,
          title: "Synthetic review evidence",
          request: "Verify local queue and website only",
          acceptance: "Never run a model or make a remote write",
          model_approved: true,
          model_budget_seconds: 30,
        },
      })
    ).json();
    expect(
      (
        await page.request.post(`/api/work/${work!.id}/start`, {
          headers,
          data: {},
        })
      ).ok(),
    ).toBeTruthy();
    let task: {
      taskId: string;
      workflowInstanceId: string;
      inputData: { sha?: string };
    } | null = null;
    await expect
      .poll(async () => {
        task = await (
          await page.request.get(
            `${api}/runner/conductor/tasks/poll/cp_project_code`,
            { headers: runnerHeaders },
          )
        ).json();
        return !!task;
      })
      .toBe(true);
    await page.request.post(`${api}/runner/artifacts`, {
      headers: runnerHeaders,
      data: {
        work_id: work!.id,
        data: {
          head_sha: sha,
          base_sha: "b".repeat(40),
          tests_passed: true,
          dirty: false,
          summary:
            "Explicit synthetic queue verification. No coding agent ran.",
          changed_files: ["README.md"],
          diff: "Synthetic fixture: README only",
          checks: [
            {
              name: "Synthetic fixture check",
              passed: true,
              output: "No provider calls",
            },
          ],
        },
      },
    });
    expect(
      (
        await page.request.post(`${api}/runner/conductor/tasks`, {
          headers: runnerHeaders,
          data: {
            taskId: task!.taskId,
            workflowInstanceId: task!.workflowInstanceId,
            status: "COMPLETED",
          },
        })
      ).ok(),
    ).toBeTruthy();
    await expect
      .poll(
        async () =>
          (await (await page.request.get(`/api/work/${work!.id}`)).json())
            .execution.status,
      )
      .toBe("COMPLETED");
    await page.goto(`/projects/${p.id}`);
    await expect(
      page.getByText("Synthetic fixture: README only", { exact: true }),
    ).toBeVisible();
    page.once("dialog", (d) => d.accept());
    await page
      .getByRole("button", {
        name: "Approve exact commit for publication",
        exact: true,
      })
      .click();
    await page
      .getByRole("button", { name: "Publish draft PR", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Publish draft PR", exact: true }),
    ).toBeDisabled();
    task = null;
    await expect
      .poll(async () => {
        task = await (
          await page.request.get(
            `${api}/runner/conductor/tasks/poll/cp_project_publish`,
            { headers: runnerHeaders },
          )
        ).json();
        return !!task;
      })
      .toBe(true);
    expect(task!.inputData.sha).toBe(sha);
    await page.request.post(`${api}/runner/publication`, {
      headers: runnerHeaders,
      data: { work_id: work!.id, sha, state: "failed" },
    });
    await page.request.post(`${api}/runner/conductor/tasks`, {
      headers: runnerHeaders,
      data: {
        taskId: task!.taskId,
        workflowInstanceId: task!.workflowInstanceId,
        status: "FAILED",
        reasonForIncompletion: "Synthetic failure fixture; no remote write",
      },
    });
    await page.reload();
    await expect(
      page.getByText("Publication: failed", { exact: true }),
    ).toBeVisible();
  } finally {
    if (work) {
      await page.request
        .post(`/api/work/${work.id}/publication/cancel`, { headers, data: {} })
        .catch(() => {});
      await page.request
        .post(`${api}/runner/publication/stopped/${work.id}`, {
          headers: runnerHeaders,
        })
        .catch(() => {});
      await page.request
        .post(`/api/work/${work.id}/cancel`, { headers, data: {} })
        .catch(() => {});
    }
    await page.request.delete(`/api/projects/${p.id}`, { headers });
  }
});

test("run search renders the same rows counted by the server", async ({
  page,
}) => {
  await signIn(page);
  const response = await page.request.get(
    "/api/executions?size=100&search=smoke-test",
  );
  const history = await response.json();
  expect(history.totalHits).toBeGreaterThan(0);
  await page.goto("/executions");
  await page.getByLabel("Search runs", { exact: true }).fill("smoke-test");
  await expect(page.locator(".runs-panel button.run-link")).toHaveCount(
    Math.min(20, history.totalHits),
  );
});
