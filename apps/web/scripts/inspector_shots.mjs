// Screenshots of the official MCP Inspector connected to the Portfolio MCP server.
// node scripts/inspector_shots.mjs "<inspector url with token>" <outDir>
import { chromium } from "@playwright/test";

const [url, out] = process.argv.slice(2);
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1400, height: 900 } });
await p.goto(url);
await p.waitForTimeout(2500);
const transport = p.locator("button[role=combobox]").first();
await transport.click();
await p.getByRole("option", { name: /Streamable HTTP/i }).click();
const urlBox = p.locator("input#sse-url-input, input[placeholder*='URL' i]").first();
await urlBox.fill("http://localhost:8091/mcp/");
await p.getByRole("button", { name: /^Connect$/ }).click();
await p.waitForTimeout(4000);
await p.screenshot({ path: `${out}/inspector_connected.png` });
await p.getByRole("tab", { name: /Tools/i }).click();
await p.getByRole("button", { name: /List Tools/i }).click();
await p.waitForTimeout(2500);
await p.screenshot({ path: `${out}/inspector_tools.png` });
await p.getByText("search_evidence", { exact: true }).first().click();
await p.waitForTimeout(1000);
await p.locator("textarea, input").filter({ hasNot: p.locator("[type=checkbox]") }).locator("visible=true").nth(0);
const req = p.locator("#requirement, [name=requirement], textarea#requirement").first();
if (await req.count()) await req.fill("spaCy NER clinical notes");
await p.getByRole("button", { name: /Run Tool/i }).click();
await p.waitForTimeout(6000);
await p.screenshot({ path: `${out}/inspector_call.png`, fullPage: true });
await p.getByRole("tab", { name: /Resources/i }).click();
await p.getByRole("button", { name: /List Templates/i }).click().catch(() => {});
await p.waitForTimeout(2000);
await p.screenshot({ path: `${out}/inspector_resources.png` });
await p.getByRole("tab", { name: /Prompts/i }).click();
await p.getByRole("button", { name: /List Prompts/i }).click().catch(() => {});
await p.waitForTimeout(2000);
await p.screenshot({ path: `${out}/inspector_prompts.png` });
await b.close();
