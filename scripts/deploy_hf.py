"""(Alternative host) Deploy GigBid to a Hugging Face Docker Space (needs HF PRO for Docker Spaces since 2026). Secrets are read from .env and set as Space secrets
(never committed). Usage: python scripts/deploy_hf.py [space_name]"""
from __future__ import annotations

import os
import secrets
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values, set_key
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
SPACE_README = """---
title: GigBid
emoji: 🤝
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Multi-agent freelancer copilot (LangGraph, MCP, RAG)
---
GigBid — a multi-agent freelancer copilot. Source: https://github.com/aliawan27/gigbid
"""


def main(name: str = "gigbid"):
    env = dotenv_values(ENV)
    for k in ("APP_SECRET_KEY", "REVIEWER_PASSWORD", "MARKETPLACE_MCP_TOKEN", "GIGSIM_API_TOKEN"):
        if not env.get(k):
            env[k] = secrets.token_urlsafe(12 if k == "REVIEWER_PASSWORD" else 24)
            set_key(str(ENV), k, env[k])
    api = HfApi(token=env["HF_TOKEN"])
    user = api.whoami()["name"]
    repo = f"{user}/{name}"
    api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True, private=False)
    for k in ("GROQ_API_KEYS", "LANGSMITH_API_KEY", "APP_SECRET_KEY", "REVIEWER_PASSWORD", "MARKETPLACE_MCP_TOKEN",
              "GIGSIM_API_TOKEN", "DATABASE_URL", "LANGSMITH_TRACE_BASE"):
        if env.get(k):
            api.add_space_secret(repo, k, env[k])
    api.add_space_variable(repo, "LANGSMITH_PROJECT", "gigbid")
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "README.md").write_text(SPACE_README, encoding="utf-8")
        api.upload_folder(repo_id=repo, repo_type="space", folder_path=str(ROOT), commit_message="deploy",
                          ignore_patterns=[".venv/*", ".env", "**/node_modules/*", "apps/web/dist/*", "data/processed/*",
                                           "data/*.db*", "data/uploads/*", "logs/*", ".git/*", "**/__pycache__/*",
                                           "apps/web/test-results/*", "apps/web/playwright-report/*", "README.md",
                                           "evals/results/raw/*", "docs/report/*.pdf"])
        api.upload_file(path_or_fileobj=str(Path(td) / "README.md"), path_in_repo="README.md", repo_id=repo, repo_type="space")
    print(f"https://huggingface.co/spaces/{repo}  ->  https://{user}-{name}.hf.space")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
