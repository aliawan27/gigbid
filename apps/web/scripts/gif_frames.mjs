// Captures demo frames from a running stack: node scripts/gif_frames.mjs <outDir>  (REVIEWER_PASSWORD env)
import { chromium } from "@playwright/test";
const out = process.argv[2];
const base = process.env.E2E_BASE_URL || "http://localhost:7860";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1100, height: 700 } });
let i = 0;
const shot = async () => p.screenshot({ path: `${out}/f${String(i++).padStart(2, "0")}.png` });
await p.goto(`${base}/login`);
await p.getByLabel("Username").fill("reviewer");
await p.getByLabel("Password").fill(process.env.REVIEWER_PASSWORD);
await shot();
await p.getByRole("button", { name: "Sign in" }).click();
await p.waitForURL(/inbox/); await p.waitForTimeout(1500); await shot();
await p.getByText("SCAM").first().click(); await p.waitForTimeout(1500); await shot();
await p.goto(`${base}/inbox`); await p.waitForTimeout(1200);
const appr = p.getByText("APPROVE").first();
if (await appr.count()) {
  await appr.click(); await p.waitForTimeout(1500); await shot();
  await p.mouse.wheel(0, 500); await p.waitForTimeout(500); await shot();
  await p.getByTestId("open-studio").click(); await p.waitForTimeout(1500); await shot();
  await p.getByTestId("citation").first().hover(); await p.waitForTimeout(500); await shot();
}
for (const path of ["/pipeline", "/messages", "/runs"]) { await p.goto(base + path); await p.waitForTimeout(1500); await shot(); }
const run = p.locator(".tr").first(); if (await run.count()) { await run.click(); await p.waitForTimeout(2000); await shot(); }
await b.close();
