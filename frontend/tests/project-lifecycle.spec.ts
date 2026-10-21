import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const env = fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8");
const token = env.match(/^CONTROL_PLANE_TOKEN=(.+)$/m)![1].trim();
const origin = process.env.WEB_URL || "http://127.0.0.1:3000";

test("project work, runner pairing, approval guard and release evidence", async ({
  page,
}) => {
  page.setDefaultTimeout(10000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByLabel("Owner password or API token").fill(token);
  await page.getByRole("button", { name: "Open control plane" }).click();
  await expect(
    page.getByRole("heading", { name: "What needs your attention." }),
  ).toBeVisible();
  const projectResponse = await page.request.post("/api/projects", {
    headers: { Origin: origin },
    data: {
      name: `Lifecycle verification ${Date.now()}`,
      repo_url: "https://github.com/VarunTx/aws_hackathon",
    },
  });
  const project = await projectResponse.json();
  try {
    await page.goto(`/projects/${project.id}`);
    await page.getByText("Pair a local runner", { exact: true }).click();
    await page
      .getByLabel("Runner name", { exact: true })
      .fill("Browser test runner");
    await page
      .getByRole("button", { name: "Pair runner", exact: true })
      .click();
    await expect(
      page.getByLabel("Runner token", { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Hide", exact: true }).click();
    await page
      .getByLabel("Title", { exact: true })
      .fill("Synthetic local verification");
    await page
      .getByLabel("Requested change", { exact: true })
      .fill("Do not run an agent; validate the approval guard.");
    await page
      .getByLabel("Acceptance criteria", { exact: true })
      .fill(
        "An unapproved model run must be rejected before Conductor starts.",
      );
    const runner = page.getByRole("combobox", {
      name: "Work runner",
      exact: true,
    });
    await expect(runner.locator("option")).toHaveCount(2);
    await runner.selectOption({ index: 1 });
    await page
      .getByRole("button", { name: "Create request", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Synthetic local verification" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Start work", exact: true }).click();
    await expect(
      page.getByText(
        "Approve model usage when creating this request before starting",
        { exact: true },
      ),
    ).toBeVisible();
    await page.getByRole("tab", { name: "Changes", exact: true }).click();
    await expect(
      page.getByText(
        "CI results describe checks. They do not prove a deployment.",
      ),
    ).toBeVisible();
    await page.getByRole("tab", { name: "Releases", exact: true }).click();
    await page.getByLabel("Expected deployed commit").fill("a".repeat(40));
    await page.getByRole("button", { name: "Record expected release" }).click();
    await page.getByRole("button", { name: "Verify live release" }).click();
    await expect(
      page.getByText("aaaaaaaaaaaa · unverified", { exact: true }),
    ).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true);
    expect(errors).toEqual([]);
  } finally {
    await page.request
      .delete(`/api/projects/${project.id}`, {
        headers: { Origin: origin },
        timeout: 5000,
      })
      .catch(() => {});
  }
});
