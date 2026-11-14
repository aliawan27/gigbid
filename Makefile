PY ?= .venv/Scripts/python
export PYTHONPATH := .

.PHONY: dev test eval seed demo lint smoke web

dev:            ## run every service locally (GigSim, 3 MCP servers, worker, API+UI on :8000)
	$(PY) scripts/start_all.py

web:            ## build the web UI (served by the API) and regenerate the typed client
	cd apps/web && npm ci && npm run gen:api && npm run build

seed:           ## regenerate synthetic data + seed users
	$(PY) scripts/generate_data.py && $(PY) scripts/seed_users.py

test:           ## unit + contract + integration
	$(PY) -m pytest tests -q

lint:
	$(PY) -m ruff check agent rag mcp_servers apps worker gigsim evals scripts
	$(PY) scripts/ci_checks.py

eval:           ## full evaluation suite -> evals/results/*.json (needs GROQ_API_KEYS)
	$(PY) evals/runners/rag_eval.py
	$(PY) evals/runners/decision_eval.py
	$(PY) evals/runners/gigsim_outcomes.py
	$(PY) evals/runners/injection_eval.py
	$(PY) evals/runners/tool_granularity.py
	$(PY) evals/runners/agent_comparison.py
	$(PY) evals/runners/judge_calibration.py
	$(PY) evals/runners/make_tables.py

smoke:          ## 30-job smoke eval with failure thresholds (CI)
	$(PY) evals/runners/smoke_eval.py --n 30

demo:           ## run one job end to end in the terminal
	$(PY) scripts/run_one.py job-0002 ai_ml
