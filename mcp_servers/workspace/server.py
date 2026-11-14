"""GigBid Workspace MCP server (A3): calendar free slots, tentative interview holds and email drafts.
Backed by a local mock calendar/mailbox (JSON file), as allowed by the spec; agents only see MCP tools.

Run: python -m mcp_servers.workspace.server --http 8093
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

STORE = Path(os.getenv("WORKSPACE_STORE", Path(__file__).resolve().parents[2] / "logs" / "workspace.json"))
mcp = FastMCP("gigbid-workspace", instructions="Calendar and email drafts for the freelancer. Holds are tentative; "
              "drafts are never sent automatically.")


def _load() -> dict:
    if STORE.exists():
        return json.loads(STORE.read_text())
    return {"busy": {}, "holds": [], "drafts": []}


def _save(d: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, indent=1))


def _busy(user_id: str, day: datetime) -> set[int]:
    # deterministic mock calendar: some hours are busy per user/day
    h = int(hashlib.md5(f"{user_id}{day.date()}".encode()).hexdigest(), 16)
    return {9 + (h >> i) % 8 for i in range(0, 12, 4)}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, destructiveHint=False, openWorldHint=False))
def free_slots(user_id: str, days: Annotated[int, Field(ge=1, le=14)] = 5,
               duration_minutes: Annotated[int, Field(ge=15, le=120)] = 30, max_slots: int = 5) -> list[dict]:
    """Free calendar slots (UTC, working hours 09-17, weekdays) for interviews in the next `days` days."""
    d = _load()
    held = {h["start"] for h in d["holds"] if h["user_id"] == user_id}
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    out = []
    for i in range(1, days + 1):
        day = now + timedelta(days=i)
        if day.weekday() >= 5:
            continue
        for hour in range(9, 17):
            if hour in _busy(user_id, day):
                continue
            start = day.replace(hour=hour).isoformat()
            if start not in held:
                out.append({"start": start, "end": (day.replace(hour=hour) + timedelta(minutes=duration_minutes)).isoformat()})
            if len(out) >= max_slots:
                return out
    return out


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True, destructiveHint=False, openWorldHint=False))
def create_tentative_hold(user_id: str, start: str, title: str, idempotency_key: str) -> dict:
    """Create a TENTATIVE calendar hold for an interview slot (idempotent)."""
    d = _load()
    for h in d["holds"]:
        if h["key"] == idempotency_key:
            return {**h, "idempotent_replay": True}
    h = {"key": idempotency_key, "user_id": user_id, "start": start, "title": title, "status": "tentative"}
    d["holds"].append(h)
    _save(d)
    return h


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=True, destructiveHint=False, openWorldHint=False))
def create_email_draft(user_id: str, to: str, subject: str, body: str, idempotency_key: str) -> dict:
    """Create an email DRAFT in the user's mailbox (never sent automatically; idempotent)."""
    d = _load()
    for x in d["drafts"]:
        if x["key"] == idempotency_key:
            return {**x, "idempotent_replay": True}
    x = {"key": idempotency_key, "user_id": user_id, "to": to, "subject": subject, "body": body, "status": "draft"}
    d["drafts"].append(x)
    _save(d)
    return x


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--http", type=int)
    a = ap.parse_args()
    if a.http:
        mcp.settings.host, mcp.settings.port, mcp.settings.stateless_http = "0.0.0.0", a.http, True
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


if __name__ == "__main__":
    main()
