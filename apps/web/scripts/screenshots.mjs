// Captures README/report screenshots from a running stack: node scripts/screenshots.mjs <outDir>
import { chromium } from "@playwright/test";

const out = process.argv[2] || "../../docs/images";
const base = process.env.E2E_BASE_URL || "http://localhost:8000";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
await p.goto(`${base}/login`);
await p.getByLabel("Username").fill("reviewer");
await p.getByLabel("Password").fill(process.env.REVIEWER_PASSWORD || "reviewer-dev-pass");
await p.getByRole("button", { name: "Sign in" }).click();
await p.waitForURL(/inbox/);
await p.waitForTimeout(1500);
await p.screenshot({ path: `${out}/inbox.png` });
for (const [path, name] of [["/pipeline", "pipeline"], ["/messages", "messages"], ["/runs", "runs"], ["/analytics", "analytics"], ["/settings", "settings"]]) {
  await p.goto(base + path);
  await p.waitForTimeout(1500);
  await p.screenshot({ path: `${out}/${name}.png`, fullPage: true });
}
await p.goto(`${base}/inbox`);
await p.waitForTimeout(1500);
const appr = p.getByText("APPROVE").first();
if (await appr.count()) {
  await appr.click();
  await p.waitForTimeout(2000);
  await p.screenshot({ path: `${out}/job_detail.png`, fullPage: true });
  await p.getByTestId("open-studio").click();
  await p.waitForTimeout(2000);
  await p.getByTestId("citation").first().hover().catch(() => {});
  await p.screenshot({ path: `${out}/studio.png`, fullPage: true });
}
await b.close();
