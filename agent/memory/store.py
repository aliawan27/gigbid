"""Long-term memory on the LangGraph store (style + outcome), written only via promotion_rules."""
from __future__ import annotations

from agent.memory import promotion_rules as rules


async def record_edit(store, user_id: str, original: str, edited: str) -> list[str]:
    """Called when the user approves an edited draft. Returns newly promoted rule keys."""
    ns_c = ("style_candidates", user_id)
    promoted = []
    for c in rules.style_candidates(original, edited):
        item = await store.aget(ns_c, c["key"])
        n = (item.value["count"] if item else 0) + 1
        await store.aput(ns_c, c["key"], {"count": n, "rule": c["rule"]})
        if c["key"] in rules.promote_style({c["key"]: n}):
            if not await store.aget(("style", user_id), c["key"]):
                await store.aput(("style", user_id), c["key"], {"rule": c["rule"], "evidence_edits": n})
                promoted.append(c["key"])
    return promoted


async def style_rules(store, user_id: str) -> list[str]:
    return [it.value["rule"] for it in await store.asearch(("style", user_id), limit=50)]


async def record_outcome(store, user_id: str, category: str, status: str, meta: dict) -> dict:
    ns = ("outcome", user_id)
    item = await store.aget(ns, category or "general")
    stats = rules.outcome_update(item.value if item else None, status, meta)
    await store.aput(ns, category or "general", stats)
    return stats


async def outcome_lessons(store, user_id: str, category: str) -> dict | None:
    item = await store.aget(("outcome", user_id), category or "general")
    if item and item.value.get("promoted"):
        return item.value
    return None


async def list_memory(store, user_id: str) -> list[dict]:
    out = []
    for ns in (("style", user_id), ("outcome", user_id), ("style_candidates", user_id)):
        for it in await store.asearch(ns, limit=100):
            out.append({"namespace": ns[0], "key": it.key, "value": it.value})
    return out


async def delete_memory(store, user_id: str, namespace: str, key: str) -> None:
    await store.adelete((namespace, user_id), key)
