"""Claim verification node (B3): split draft into claims, check each against evidence, remove/rewrite
unsupported ones BEFORE the Critic sees the draft; records unsupported-claim rate before and after."""
from __future__ import annotations

import asyncio

from agent.nodes._common import node
from rag.verify import apply_fixes, unsupported_rate, verify


@node("verifier")
async def verifier(state, store):
    d = dict(state["draft"])
    ev = state.get("evidence") or []
    emap = d.get("evidence_map", {})
    # make tags explicit so the checker sees which evidence each sentence cites
    tagged = [{**e, "id": next((k for k, v in emap.items() if v == e["id"]), e["id"])} for e in ev]
    checks = await asyncio.to_thread(verify, d["cover_letter"], tagged)
    before = unsupported_rate(checks)
    fixed = apply_fixes(d["cover_letter"], checks)
    after = before
    if fixed != d["cover_letter"]:
        rechecks = await asyncio.to_thread(verify, fixed, tagged)
        after = unsupported_rate(rechecks)
        d["cover_letter"] = fixed
    return {"draft": d, "claim_checks": [c.model_dump() for c in checks], "unsupported_before": before,
            "unsupported_after": after,
            "_summary": f"{len(checks)} claims; unsupported {before:.0%} -> {after:.0%}"}
