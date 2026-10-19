import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const env = fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8");
const token = env.match(/^CONTROL_PLANE_TOKEN=(.+)$/m)![1];

test("unauthenticated API and origin checks", async ({ request }) => {
  expect((await request.get("/api/executions")).status()).toBe(401);
  expect(
    (await request.post("/api/session", { data: { token } })).status(),
  ).toBe(403);
});

test("real browser runs diagnostics, inspects task output, explores definitions and health", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("Workspace token").fill(token);
  await page.getByRole("button", { name: "Open control plane" }).click();
  await expect(
    page.getByRole("heading", { name: "Your orchestration, in focus." }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/overview.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Run workflow", exact: true }).click();
  await page.getByLabel("Service", { exact: true }).fill("browser-smoke");
  await page.getByLabel("Failure testing").selectOption("once");
  await page.getByRole("button", { name: "Start execution" }).click();
  await expect(
    page.getByRole("heading", { name: "Execution detail" }),
  ).toBeVisible();
  await expect(page.locator(".execution-title .status")).toHaveText(
    "completed",
    { timeout: 60000 },
  );
  await expect(page.locator(".task-row")).toHaveCount(4);
  await page.getByRole("button", { name: "Inspect analyze" }).click();
  await expect(page.locator(".inspector")).toContainText("deterministic");
  await page.screenshot({
    path: "../docs/screenshots/execution.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: /Workflows/ })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Designed to keep moving." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "View JSON" }).click();
  await expect(page.locator("pre")).toContainText("incident_analysis");
  await page.getByRole("button", { name: "View graph" }).click();
  await expect(page.locator(".dag-node")).toHaveCount(3);
  await page
    .getByRole("button", { name: "Infrastructure", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Python worker fleet" }),
  ).toBeVisible();
  await expect(page.locator(".worker-row .status-polling")).toHaveCount(4);
  await page.screenshot({
    path: "../docs/screenshots/infrastructure.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    )
    .toBe(true);
  await page.screenshot({
    path: "../docs/screenshots/mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
