# Runbook

## Run locally
```bash
uv venv && uv pip install -e ".[dev]"          # Python 3.12
cp .env.example .env                             # add GROQ_API_KEYS (comma-separated)
make web                                         # build UI (served by the API)
make dev                                         # GigSim :8081, MCP :8091-8093, worker, API+UI :8000
# or everything in one process (what the public deployment runs):
python -m apps.api.allinone                      # http://localhost:7860
# or containers:
docker compose -f infra/docker-compose.yml up --build
```
Reviewer login is seeded at start-up (`scripts/seed_users.py`); its password comes from `REVIEWER_PASSWORD`.

## Scheduling (E1)
* The worker (`worker/main.py`) scouts each user's saved searches every **60 min in GigSim** and every **240 min in live
  Upwork mode** (`agent/config.yaml`). Justification for live mode: freelance posts stay open for days, Upwork's guidance treats
  aggressive polling as bot behaviour, and 6 searches/day per saved search is far below any rate a human would hit by hand; the
  scout only reads through the official MCP server, never scrapes.
* Tasks live in the `tasks` table with a unique `dedup_key` (`bid:<user>:<job>`), so a re-scout never queues a job twice.
* Pipeline sync (proposal statuses, new client messages) runs every 45 s against GigSim.

## Crash safety (C6)
* Graph state is checkpointed after every node (Postgres in deployment, SQLite locally).
* On worker start, tasks left `running` are re-queued; resuming re-enters the graph from its last checkpoint.
* `submit_proposal` uses a deterministic idempotency key (`user:job:submit:<hash of the approved letter>`), so a submit that
  crashed after GigSim accepted it is replayed, not repeated — Connects are spent once (`tests/integration`).
* Demo: approve a proposal, kill the worker before it submits (`Stop-Process` / `kill`), restart → it is submitted exactly once.

## Degraded mode (A6)
If the marketplace MCP server or GigSim is down, MCP calls retry with backoff, then raise `MarketplaceUnavailable`; the job is
**parked** (not lost) and re-queued after 30 s, and the UI shows the "Marketplace unavailable" banner (`/api/health`).

## Budgets (E5)
Declared in `agent/config.yaml` (`budgets:`) and checked per node: max 40 steps and 30k tokens per thread → "needs attention".
Measured values are in `evals/results/decisions.json` and `evals/results/gigsim_outcomes.json`.

## Switching to live Upwork
Set `marketplace.mode: upwork_live` (or `MARKETPLACE_MODE=upwork_live`) and connect Upwork in Settings (OAuth). Only the
adapter changes; the graph, prompts and UI do not. Live writes are drafts the user confirms on Upwork.

## Evaluations
`make eval` (needs Groq keys) regenerates every file in `evals/results/`; `make smoke` is the 30-job CI gate.

## Tracing
Set `LANGSMITH_API_KEY`; every graph run is traced to the `gigbid` project with the run's trace id, user and job id as metadata.
Each node also writes an execution trace (tool calls, tokens, cost, latency) shown in the Agent runs screen.
