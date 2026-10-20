import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const env = fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8");
const token = env.match(/^CONTROL_PLANE_TOKEN=(.+)$/m)![1].trim();
const ORIGIN = process.env.WEB_URL || "http://127.0.0.1:3000";

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByLabel("Owner password or API token").fill(token);
  await page.getByRole("button", { name: "Open control plane" }).click();
  await expect(
    page.getByRole("heading", { name: "What needs your attention." }),
  ).toBeVisible();
}

test("unauthenticated API and origin checks", async ({ request }) => {
  expect((await request.get("/api/executions")).status()).toBe(401);
  expect((await request.get("/api/projects")).status()).toBe(401);
  expect(
    (await request.post("/api/session", { data: { credential: token } })).status(),
  ).toBe(403);
});

test("register a project, observe real health, and follow an incident to recovery", async ({
  page,
}) => {
  const name = `Browser Project ${Date.now()}`;
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  await signIn(page);
  await page.screenshot({ path: "../docs/screenshots/overview.png", fullPage: true });

  await page.goto("/projects/new");
  await page.getByLabel("Project name").fill(name);
  await page
    .getByLabel("Description")
    .fill("Deterministic browser verification project");
  await page.getByLabel("Service name").fill("Browser API");
  await page.getByLabel("Health endpoint").fill("https://example.com");
  await page.getByRole("button", { name: "Create project" }).click();

  await expect(page.getByRole("heading", { name })).toBeVisible();
  const projectId = new URL(page.url()).pathname.split("/").pop()!;
  await page.screenshot({ path: "../docs/screenshots/project.png", fullPage: true });

  // A real HTTP check against example.com.
  const row = page.locator("tbody tr", { hasText: "Browser API" }).first();
  await row.getByRole("button", { name: "Check now" }).click();
  await expect(row.locator(".status-healthy")).toBeVisible({ timeout: 30000 });

  // Make the next genuine check fail (expected 599 vs actual 200) through the same API the UI uses.
  const services = await page.request.get(`/api/services?project_id=${projectId}`, {
    headers: { Origin: ORIGIN },
  });
  const service = (await services.json())[0];
  const patch = await page.request.patch(`/api/services/${service.id}`, {
    headers: { Origin: ORIGIN },
    data: { expected_status: 599, failure_threshold: 1 },
  });
  expect(patch.status()).toBe(200);

  await page.reload();
  const failing = page.locator("tbody tr", { hasText: "Browser API" }).first();
  await failing.getByRole("button", { name: "Check now" }).click();
  await expect(failing.locator(".status-degraded")).toBeVisible({ timeout: 30000 });

  await page.goto("/incidents");
  const incidentRow = page.locator("tbody tr", { hasText: "Browser API" }).first();
  await expect(incidentRow).toBeVisible();
  await incidentRow.getByRole("link").first().click();
  await expect(page.getByRole("heading", { name: /Browser API/ })).toBeVisible();
  await expect(page.getByText("Detection evidence")).toBeVisible();
  await page.screenshot({ path: "../docs/screenshots/incident.png", fullPage: true });

  // Restore the expected status: the next real check recovers the service and resolves the incident.
  await page.request.patch(`/api/services/${service.id}`, {
    headers: { Origin: ORIGIN },
    data: { expected_status: 200 },
  });
  await page.goto(`/projects/${projectId}`);
  const recovered = page.locator("tbody tr", { hasText: "Browser API" }).first();
  await recovered.getByRole("button", { name: "Check now" }).click();
  await expect(recovered.locator(".status-healthy")).toBeVisible({ timeout: 30000 });

  await page.goto("/incidents?filter=resolved");
  await page.getByLabel("Filter incidents").selectOption("resolved");
  await expect(page.locator("tbody tr", { hasText: "Browser API" }).first()).toBeVisible();

  // Clean up the project created by this test.
  await page.request.delete(`/api/projects/${projectId}`, { headers: { Origin: ORIGIN } });
  expect(errors).toEqual([]);
});

test("real Conductor executions, definitions, workers and mobile layout", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  await signIn(page);
  await page.goto("/executions");
  await expect(page.getByRole("heading", { name: "Every run. Every detail." })).toBeVisible();

  await page.getByRole("button", { name: "Run workflow", exact: true }).click();
  await page.getByLabel("Service", { exact: true }).fill("browser-smoke");
  await page.getByLabel("Failure testing").selectOption("once");
  await page.getByRole("button", { name: "Start execution" }).click();
  await expect(page.getByRole("heading", { name: "Execution detail" })).toBeVisible();
  await expect(page.locator(".execution-title .status")).toHaveText("completed", {
    timeout: 60000,
  });
  await expect(page.locator(".task-row")).toHaveCount(4);
  await page.getByRole("button", { name: "Inspect analyze" }).click();
  await expect(page.locator(".inspector")).toContainText("deterministic");
  await page.screenshot({ path: "../docs/screenshots/execution.png", fullPage: true });

  await page.getByRole("button", { name: "Workflows", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Designed to keep moving." })).toBeVisible();
  await page.getByRole("button", { name: "View JSON" }).click();
  await expect(page.locator("pre")).toContainText("incident_analysis");
  await page.getByRole("button", { name: "View graph" }).click();
  await expect(page.locator(".dag-node")).toHaveCount(3);

  await page.getByRole("button", { name: "Infrastructure", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Python worker fleet" })).toBeVisible();
  await expect(page.locator(".worker-row .status-polling")).toHaveCount(4);
  await page.screenshot({ path: "../docs/screenshots/infrastructure.png", fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
  await page.screenshot({ path: "../docs/screenshots/mobile.png", fullPage: true });
  expect(errors).toEqual([]);
});
