import { test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
const env = fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8");
const token = env.match(/^CONTROL_PLANE_TOKEN=(.+)$/m)![1].trim();
test("find overflow infra", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Owner password or API token").fill(token);
  await page.getByRole("button", { name: "Open control plane" }).click();
  await page.goto("/workflows");
  await page.getByRole("button", { name: "Infrastructure", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(1500);
  const offenders = await page.evaluate(() => {
    const width = window.innerWidth;
    return [...document.querySelectorAll<HTMLElement>("body *")]
      .map((el) => ({ el, rect: el.getBoundingClientRect() }))
      .filter(({ rect }) => rect.right > width + 1)
      .slice(0, 10)
      .map(({ el, rect }) => ({ tag: el.tagName, cls: el.className?.toString().slice(0, 50), right: Math.round(rect.right), width: Math.round(rect.width) }));
  });
  console.log("scrollWidth", await page.evaluate(() => document.documentElement.scrollWidth));
  console.log(JSON.stringify(offenders, null, 1));
});
