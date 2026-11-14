# Build progress (resume notes)

Done: data generator + GigSim; RAG V0-V5,V8 + claim verification; 3 MCP servers + GitHub/Upwork adapters; both graphs, memory,
interrupts, durability; FastAPI + worker + SSE; React UI (9 screens) + Playwright (10/10); unit/contract/integration tests
(18/18); CI; all evals (rag, decisions + fixes, outcomes, A/B, injection, tool granularity, agent comparison); report PDF;
write-up; README; demo GIF; public LangSmith traces; change request.

Waiting on the user (details in HANDOFF.md, which is git-ignored):
- [ ] DATABASE_URL (Neon) and RENDER_API_KEY in .env -> `python scripts/deploy_render.py`; then fill LIVE_URL in README + report
- [ ] 30 human labels in evals/datasets/judge_labels.csv -> `python evals/runners/judge_calibration.py`; fill KAPPA_SENTENCE in report
- [ ] MCP Inspector screenshots -> docs/images/inspector_*.png
- [ ] demo video, Medium post, Google Classroom submission
