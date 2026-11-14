"""Create / update the GigBid web service on Render (free plan, Docker) from the public GitHub repo, with secrets read
from .env (never committed). Usage: RENDER_API_KEY=... python scripts/deploy_render.py"""
from __future__ import annotations

import os
import secrets
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
API = "https://api.render.com/v1"
REPO = os.getenv("GIGBID_REPO", "https://github.com/aliawan27/gigbid")


def main():
    env = dotenv_values(ENV)
    key = os.getenv("RENDER_API_KEY") or env.get("RENDER_API_KEY")
    if not key:
        sys.exit("set RENDER_API_KEY")
    for k in ("APP_SECRET_KEY", "REVIEWER_PASSWORD", "MARKETPLACE_MCP_TOKEN", "GIGSIM_API_TOKEN"):
        if not env.get(k):
            env[k] = secrets.token_urlsafe(12 if k == "REVIEWER_PASSWORD" else 24)
            set_key(str(ENV), k, env[k])
    h = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    owner = httpx.get(f"{API}/owners", headers=h, timeout=30).json()[0]["owner"]["id"]
    env_vars = [{"key": k, "value": env[k]} for k in ("GROQ_API_KEYS", "DATABASE_URL", "LANGSMITH_API_KEY", "APP_SECRET_KEY",
                                                       "REVIEWER_PASSWORD", "MARKETPLACE_MCP_TOKEN", "GIGSIM_API_TOKEN") if env.get(k)]
    env_vars += [{"key": "PORT", "value": "7860"}, {"key": "LANGSMITH_PROJECT", "value": "gigbid"}]
    name = os.getenv("RENDER_SERVICE_NAME", "gigbid")
    existing = [s["service"] for s in httpx.get(f"{API}/services", headers=h, params={"name": name}, timeout=30).json()]
    if existing:
        sid = existing[0]["id"]
        httpx.put(f"{API}/services/{sid}/env-vars", headers=h, json=env_vars, timeout=30).raise_for_status()
        httpx.post(f"{API}/services/{sid}/deploys", headers=h, json={}, timeout=30).raise_for_status()
        url = existing[0]["serviceDetails"]["url"]
    else:
        body = {"type": "web_service", "name": name, "ownerId": owner, "repo": REPO, "branch": "main", "autoDeploy": "yes",
                "envVars": env_vars,
                "serviceDetails": {"runtime": "docker", "plan": "free", "region": os.getenv("RENDER_REGION", "singapore"),  # next to the Neon DB "healthCheckPath": "/healthz",
                                   "envSpecificDetails": {"dockerfilePath": "./Dockerfile", "dockerContext": "."}}}
        r = httpx.post(f"{API}/services", headers=h, json=body, timeout=60)
        if r.status_code >= 400:
            sys.exit(f"Render error {r.status_code}: {r.text[:500]}")
        s = r.json()["service"]
        sid, url = s["id"], s["serviceDetails"]["url"]
    print("service", sid, url)
    for _ in range(90):  # wait for the deploy (docker build ~10 min on the free plan)
        d = httpx.get(f"{API}/services/{sid}/deploys", headers=h, params={"limit": 1}, timeout=30).json()[0]["deploy"]
        print("deploy status:", d["status"], flush=True)
        if d["status"] in ("live", "build_failed", "update_failed", "canceled", "deactivated"):
            break
        time.sleep(20)
    print(url)


if __name__ == "__main__":
    main()
