"""Client Liaison (conversation graph): read thread, classify intent, propose interview slots (Workspace MCP),
draft a reply, compliance, human approval, send exactly once."""
from __future__ import annotations

import hashlib

from langgraph.types import interrupt

from agent.config import prompt
from agent.handoffs import ApprovalDecision, ReplyDraft, ReplyIntent
from agent.llm import LLMUnavailable
from agent.mcp_client import call
from agent.memory.store import record_edit
from agent.nodes._common import llm_structured, node, tool_rec
from agent.nodes.compliance import check_text
from agent.safety import detect_injection, untrusted

SCAM_WORDS = ("telegram", "whatsapp", "crypto", "outside the platform", "off platform", "bank details", "pay you directly")


@node("load_thread")
async def load_thread(state, store):
    args = {"user_id": state["user_id"], "trace_id": state.get("trace_id", "")}
    threads = await call("client_liaison", "list_messages", args)
    t = next((x for x in threads if x["thread_id"] == state["thread_id"]), None)
    if not t:
        return {"status": "dead_letter", "errors": [f"thread {state['thread_id']} not found"]}
    last = next((m["text"] for m in reversed(t["messages"]) if m["from"] == "client"), "")
    return {"thread": t, "last_client_message": last, "status": "running",
            "_tools": [tool_rec("list_messages", args, len(threads))], "_summary": last[:120]}


@node("classify")
async def classify(state, store):
    msg = state["last_client_message"]
    inj = detect_injection(msg)
    try:
        it = await llm_structured("client_liaison", prompt("liaison_intent"), untrusted("CLIENT MESSAGE", msg), ReplyIntent, 400)
    except LLMUnavailable:
        low = msg.lower()
        intent = ("scam_signal" if any(w in low for w in SCAM_WORDS) else "interview_request" if "call" in low or "schedule" in low
                  else "hire" if "move forward" in low else "question")
        it = ReplyIntent(intent=intent, summary=msg[:100])
    if any(w in msg.lower() for w in SCAM_WORDS):
        it.intent = "scam_signal"
    it.injection_hits = inj
    return {"intent": it.model_dump(), "_summary": f"{it.intent}: {it.summary[:100]}"}


@node("slots")
async def slots(state, store):
    args = {"user_id": state["user_id"], "days": 5, "duration_minutes": 30, "max_slots": 3}
    s = await call("client_liaison", "free_slots", args)
    return {"slots": s, "_tools": [tool_rec("free_slots", args, len(s))], "_summary": f"{len(s)} free slots"}


@node("draft_reply")
async def draft_reply(state, store):
    t = state["thread"]
    hist = "\n".join(f"{m['from'].upper()}: {m['text']}" for m in t["messages"][-6:])
    user = (untrusted("THREAD", hist) + f"\nINTENT: {state['intent']}\nFREE SLOTS (UTC): {[s['start'] for s in state.get('slots') or []]}")
    try:
        r = await llm_structured("client_liaison", prompt("client_liaison"), user, ReplyDraft, 700)
    except LLMUnavailable:
        if state["intent"]["intent"] == "scam_signal":
            txt = "Thanks for the message. I keep all communication and payments on the platform, so let's continue here."
        elif state.get("slots"):
            txt = "Thanks! I'd be glad to talk. These times work for me (UTC): " + ", ".join(s["start"][:16] for s in state["slots"]) + "."
        else:
            txt = "Thanks for your reply. Happy to answer any questions about scope and milestones here."
        r = ReplyDraft(text=txt, proposed_slots=[s["start"] for s in state.get("slots") or []])
    return {"reply": r.model_dump(), "_summary": r.text[:150]}


@node("reply_compliance")
async def reply_compliance(state, store):
    rep = dict(state["reply"])
    v = check_text(rep["text"], injection_hits=state.get("intent", {}).get("injection_hits"))
    rep["text"] = v.cleaned_text
    return {"reply": rep, "compliance": v.model_dump(), "status": "awaiting_approval",
            "_summary": f"{len(v.violations)} fixes"}


@node("reply_approval")
async def reply_approval(state, store):
    d = ApprovalDecision(**interrupt({"kind": "message", "thread_id": state["thread_id"], "reply": state["reply"],
                                      "intent": state.get("intent"), "compliance": state.get("compliance"),
                                      "dry_run": {"thread_id": state["thread_id"], "text": state["reply"]["text"], "cost": 0}}))
    if d.action == "reject":
        return {"approval": d.model_dump(), "status": "rejected"}
    if d.action == "edit":
        if store:
            await record_edit(store, state["user_id"], state["reply"]["text"], d.edited_text or "")
        return {"approval": d.model_dump(), "reply": {**state["reply"], "text": d.edited_text}, "status": "running"}
    return {"approval": d.model_dump(), "status": "approved"}


@node("send")
async def send(state, store):
    key = f"{state['user_id']}:{state['thread_id']}:msg:" + hashlib.sha1(state["reply"]["text"].encode()).hexdigest()[:10]
    args = {"m": {"user_id": state["user_id"], "thread_id": state["thread_id"], "text": state["reply"]["text"],
                  "idempotency_key": key, "trace_id": state.get("trace_id", "")}}
    res = await call("client_liaison", "send_message", args)
    tools = [tool_rec("send_message", args, res)]
    if state.get("reply", {}).get("proposed_slots"):
        h = {"user_id": state["user_id"], "start": state["reply"]["proposed_slots"][0],
             "title": f"Interview (thread {state['thread_id']})", "idempotency_key": key + ":hold"}
        tools.append(tool_rec("create_tentative_hold", h, await call("client_liaison", "create_tentative_hold", h)))
    return {"sent": res, "status": "sent", "_tools": tools, "_summary": "message sent"}
