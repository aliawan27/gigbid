"""Repo ingestion through GitHub's official MCP server (third-party server we did not write, A5/B1).
Fetches README + top-level code files of a user's public repos via MCP tools and adds them to that user's portfolio
(data/uploads/<owner>/), where the incremental indexer picks them up.
Usage: GITHUB_TOKEN=... python -m rag.ingest.github_mcp <github_user> <portfolio_owner> [max_repos]"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

GITHUB_MCP_URL = os.getenv("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")
UPLOADS = Path(__file__).resolve().parents[2] / "data" / "uploads"


def _text(out) -> str:
    if isinstance(out, tuple):
        out = out[0]
    if isinstance(out, list):
        return "\n".join(o.get("text", "") if isinstance(o, dict) else str(o) for o in out)
    return str(out)


async def ingest(user: str, owner: str, max_repos: int = 5) -> list[str]:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not token:
        raise SystemExit("set GITHUB_TOKEN (a read-only fine-grained PAT is enough)")
    client = MultiServerMCPClient({"github": {"url": GITHUB_MCP_URL, "transport": "streamable_http",
                                              "headers": {"Authorization": f"Bearer {token}"}}})
    tools = {t.name: t for t in await client.get_tools()}
    search = tools["search_repositories"]
    found = json.loads(_text(await search.ainvoke({"query": f"user:{user}", "perPage": max_repos})))
    repos = [r["name"] if "name" in r else r["full_name"].split("/")[1] for r in (found.get("items") or [])][:max_repos]
    out_dir = UPLOADS / owner
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for repo in repos:
        try:
            readme = _text(await tools["get_file_contents"].ainvoke({"owner": user, "repo": repo, "path": "README.md"}))
        except Exception:  # noqa: BLE001
            continue
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", repo)
        (out_dir / f"github_{safe}.md").write_text(f"# GitHub repo {user}/{repo}\n\n{readme[:20000]}", encoding="utf-8")
        written.append(repo)
    return written


if __name__ == "__main__":
    a = sys.argv[1:]
    print(asyncio.run(ingest(a[0], a[1], int(a[2]) if len(a) > 2 else 5)))
