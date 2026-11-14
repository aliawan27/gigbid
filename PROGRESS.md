# Build progress (resume notes)

Done:
- [x] Synthetic data generator (scripts/generate_data.py) + GigSim simulator (gigsim/)
- [x] RAG: loaders, indexes, variants V0,V1,V2,V3,V4,V5,V8, claim verification
- [x] MCP servers: portfolio (8091), marketplace (8092, bearer token), workspace (8093); agent/mcp_client.py allowlists
Next:
- [x] agent: handoffs, state, nodes, prompts, bid graph, conversation graph, memory
- [x] API (FastAPI) + worker + SSE
- [x] Web (Vite React TS) 9 screens + Playwright (10 passing)
- [ ] tests (unit/contract/integration), CI
- [ ] evals (rag, decisions, gigsim outcomes, tool study, single-agent comparison, judge calibration, injection)
- [ ] Dockerfiles/compose, HF Space deploy
- [ ] docs, README, report PDF, write-up, change request

Local run: GigSim :8081, portfolio :8091, marketplace :8092, workspace :8093 (see Makefile `dev`).
