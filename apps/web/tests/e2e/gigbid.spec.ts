import { expect, test, type Page } from "@playwright/test";

// Onboarding runs against the real API. Approval flows mock only the job endpoints so they are deterministic
// (no LLM in CI) while still asserting the exact request the UI sends to resume the interrupted graph.
const draft = {
  kind: "proposal", job_id: "job-test", title: "RAG support bot",
  draft: { cover_letter: "You need a RAG assistant over your help centre. I built one that deflected 34% of tickets [E1].",
    screening_answers: [], evidence_map: { E1: "ai_ml:cs:rag-support-bot" } },
  evidence: [{ id: "ai_ml:cs:rag-support-bot", title: "Case study: RAG customer-support assistant", type: "case_study",
    source: "case_studies/rag-support-bot.md", snippet: "deflected 34% of tickets" }],
  claim_checks: [{ claim: "I built one that deflected 34% of tickets", label: "supported" }],
  risk_report: { score: 0.1, flags: [] }, price: { amount: 2400, rationale: "market median" },
  compliance: { violations: [] }, critiques: [{ approve: true, grounding: 5, personalisation: 4, issues: [] }],
  dry_run: { connects_cost: 12, connects_balance_after: 188 },
};

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Username").fill("reviewer");
  await page.getByLabel("Password").fill(process.env.REVIEWER_PASSWORD || "reviewer-dev-pass");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/inbox/);
}

async function mockStudio(page: Page) {
  const sent: unknown[] = [];
  await page.route("**/api/jobs/job-test", (r) => r.fulfill({ json: { job: { job_id: "job-test", title: "RAG support bot" },
    status: "awaiting_approval", thread_id: "t", state: {}, pending_approval: draft } }));
  await page.route("**/api/proposals/job-test/decision", async (r) => {
    sent.push(r.request().postDataJSON());
    await r.fulfill({ json: { queued: true, task_id: 1, message: "ok" } });
  });
  return sent;
}

test("onboarding: register, choose persona, land in inbox", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill(`e2e${Date.now()}`);
  await page.getByLabel("Password").fill("secret123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByTestId("onboarding")).toBeVisible();
  await page.getByLabel(/Full-stack/).check();
  await page.getByLabel("Weekly Connects budget").fill("80");
  await page.getByTestId("finish-onboarding").click();
  await expect(page.getByRole("heading", { name: "Job inbox" })).toBeVisible();
});

test("approving a proposal resumes the graph with approve", async ({ page }) => {
  await login(page);
  const sent = await mockStudio(page);
  await page.goto("/studio/job-test");
  await expect(page.getByTestId("citation").first()).toBeVisible();
  await page.getByTestId("citation").first().hover();
  await expect(page.getByText("Case study: RAG customer-support assistant")).toBeVisible();
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("decision-msg")).toContainText("exactly once");
  expect(sent[0]).toMatchObject({ action: "approve" });
});

test("rejecting requires and sends a reason", async ({ page }) => {
  await login(page);
  const sent = await mockStudio(page);
  await page.goto("/studio/job-test");
  await page.getByTestId("reject").click();
  await expect(page.getByTestId("decision-msg")).toContainText("reason");
  expect(sent.length).toBe(0);
  await page.getByTestId("reject-reason").fill("client budget too low");
  await page.getByTestId("reject").click();
  await expect.poll(() => sent.length).toBe(1);
  expect(sent[0]).toMatchObject({ action: "reject", reason: "client budget too low" });
});

test("editing a draft sends an edit that is re-checked", async ({ page }) => {
  await login(page);
  const sent = await mockStudio(page);
  await page.goto("/studio/job-test");
  const ed = page.getByTestId("draft-editor");
  await ed.fill("Your help centre needs a RAG assistant. I built one that deflected 34% of tickets [E1].");
  await page.getByTestId("approve").click();
  await expect(page.getByTestId("decision-msg")).toContainText("re-checking compliance");
  expect(sent[0]).toMatchObject({ action: "edit", edited_text: expect.stringContaining("Your help centre") });
});

test("degraded-mode banner when the marketplace is down", async ({ page }) => {
  await login(page);
  await page.route("**/api/health", (r) => r.fulfill({ json: { api: true, marketplace: false, portfolio: true, workspace: true,
    degraded: true, mode: "gigsim" } }));
  await page.reload();
  await expect(page.getByTestId("degraded-banner")).toContainText("Marketplace unavailable");
});
