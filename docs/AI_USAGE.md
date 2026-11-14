# AI usage

| Tool | Used for | Files |
|---|---|---|
| Claude Code (Anthropic) | pair-programming: scaffolding, implementation, tests, eval runners, docs drafts | most of the repository; every file was reviewed, run and tested |
| Groq-hosted open models (gpt-oss-20b/120b, qwen3.8-27b) | the product's own agents, the simulated GigSim clients, the LLM judge | runtime only |

**Things the assistant got wrong that were caught:**
1. It first chose "decomposition + hybrid + outcome boost" as the shipped retrieval variant by intuition; the evaluation showed
   it was *worse* than V0 on nDCG@10, so the shipped variant was changed to V5 + hybrid by measurement.
2. Its claim splitter counted plans ("I will start by indexing your articles") as experience claims, so the verifier deleted
   useful sentences; caught in the proposal studio screenshot and fixed with a plan-sentence filter + unit test.
3. Its first MCP HTTP setup used stateful sessions, which failed with "Task group is not initialized" after the first call;
   fixed by switching the servers to stateless streamable HTTP.
4. It loaded secret tokens before reading `.env`, so the marketplace server rejected the client's bearer token in the
   all-in-one process; fixed by loading `.env` before any module reads configuration.
