"""Shared helpers for evaluation runners: dev sets, metrics, an isolated GigSim+MCP stack, result writing."""
from __future__ import annotations

import json
import math
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "evals" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)
PERSONAS = ["ai_ml", "fullstack", "data_analyst"]
JOBS = {j["job_id"]: j for j in json.loads((ROOT / "gigsim" / "seed" / "jobs.json").read_text())}


def public_job(j: dict) -> dict:
    return {k: v for k, v in j.items() if not k.startswith("_")}


def dev(persona: str) -> list[dict]:
    return json.loads((ROOT / "evals" / "datasets" / f"dev_{persona}.json").read_text())


def recall_at(ranked: list[str], gold: set[str], k: int) -> float:
    return len(set(ranked[:k]) & gold) / len(gold) if gold else 0.0


def mrr(ranked: list[str], gold: set[str]) -> float:
    for i, r in enumerate(ranked, 1):
        if r in gold:
            return 1 / i
    return 0.0


def ndcg_at(ranked: list[str], gold: set[str], k: int) -> float:
    dcg = sum(1 / math.log2(i + 2) for i, r in enumerate(ranked[:k]) if r in gold)
    idcg = sum(1 / math.log2(i + 2) for i in range(min(k, len(gold))))
    return dcg / idcg if idcg else 0.0


def f1(tp: int, fp: int, fn: int) -> float:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def pct(vals: list[float], q: float) -> float | None:
    v = sorted(x for x in vals if x is not None)
    return round(v[min(len(v) - 1, int(q * len(v)))], 3) if v else None


def mean(vals) -> float | None:
    v = [x for x in vals if x is not None]
    return round(statistics.mean(v), 4) if v else None


def write(name: str, data: dict) -> Path:
    data = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), **data}
    p = RESULTS / f"{name}.json"
    p.write_text(json.dumps(data, indent=1, default=str))
    print(f"wrote {p.relative_to(ROOT)}")
    return p


class Stack:
    """Starts an isolated all-in-one GigBid process (fresh GigSim state) and points the MCP client at it."""

    def __init__(self, client_llm: bool = True):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        self.port = s.getsockname()[1]
        s.close()
        self.dir = Path(tempfile.mkdtemp(prefix="gigbid-eval-"))
        self.client_llm = client_llm

    def __enter__(self):
        env = {**os.environ, "PORT": str(self.port), "PYTHONPATH": str(ROOT), "GIGSIM_ERROR_RATE": "0",
               "GIGSIM_CLIENT_LLM": "1" if self.client_llm else "0", "GIGBID_APP_DB": str(self.dir / "app.db"),
               "GIGBID_SQLITE": str(self.dir / "g.db"), "GIGBID_AUDIT_LOG": str(self.dir / "audit.jsonl"),
               "WORKSPACE_STORE": str(self.dir / "ws.json"), "WORKER_SYNC_EVERY_S": "100000", "GIGSIM_STATE": str(self.dir / "gigsim.json"),
               "MARKETPLACE_USER_RPM": "1000", "GIGSIM_RATE_PER_MIN": "2000",
               "GIGBID_WORKER": "0"}  # eval stacks serve GigSim + MCP only; no background scouting
        for k in ("GIGSIM_BASE_URL", "PORTFOLIO_MCP_URL", "MARKETPLACE_MCP_URL", "WORKSPACE_MCP_URL"):
            env.pop(k, None)
        self.proc = subprocess.Popen([sys.executable, "-m", "apps.api.allinone"], cwd=ROOT, env=env,
                                     stdout=open(self.dir / "log.txt", "w"), stderr=subprocess.STDOUT)
        import httpx
        self.base = f"http://127.0.0.1:{self.port}"
        for _ in range(120):
            try:
                if httpx.get(self.base + "/gigsim/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(1)
        from dotenv import dotenv_values
        tok = dotenv_values(ROOT / ".env").get("MARKETPLACE_MCP_TOKEN") or os.getenv("MARKETPLACE_MCP_TOKEN", "marketplace-dev-token")
        self.gigsim_token = dotenv_values(ROOT / ".env").get("GIGSIM_API_TOKEN") or "gigsim-dev-token"
        os.environ.update({"PORTFOLIO_MCP_URL": f"{self.base}/mcp-portfolio/mcp/", "MARKETPLACE_MCP_URL": f"{self.base}/mcp-marketplace/mcp/",
                           "WORKSPACE_MCP_URL": f"{self.base}/mcp-workspace/mcp/", "MARKETPLACE_MCP_TOKEN": tok,
                           "MARKETPLACE_USER_RPM": "1000"})
        from agent import mcp_client
        mcp_client._tools_cache.clear()
        return self

    def __exit__(self, *a):
        self.proc.terminate()

    def gigsim(self, method: str, path: str, **kw):
        import httpx
        return httpx.request(method, self.base + "/gigsim" + path, headers={"Authorization": f"Bearer {self.gigsim_token}"},
                             timeout=120, **kw).json()


def persona_prefs(persona: str) -> dict:
    p = json.loads((ROOT / "data" / "personas" / persona / "persona.json").read_text())
    return {"rate_floor": p["rate_floor"], "connects_weekly_budget": 100000}
