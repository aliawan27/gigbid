"""Conversation graph (one thread per client conversation):
load_thread -> classify -(interview/hire)-> slots -> draft_reply -> reply_compliance -> reply_approval
reply_approval -(approve)-> send ; -(edit)-> reply_compliance ; -(reject)-> END"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.nodes.client_liaison import classify, draft_reply, load_thread, reply_approval, reply_compliance, send, slots
from agent.state import ConvState

STOP = {"rejected", "needs_attention", "dead_letter", "parked", "sent"}


def _go(t):
    return lambda s: END if s.get("status") in STOP else t


def after_classify(s):
    if s.get("status") in STOP:
        return END
    return "find_slots" if s["intent"]["intent"] in ("interview_request", "hire") else "draft_reply"


def after_approval(s):
    return {"approved": "send", "running": "reply_compliance"}.get(s.get("status"), END)


def build_conversation_graph(checkpointer=None, store=None):
    g = StateGraph(ConvState)
    for n, f in [("load_thread", load_thread), ("classify", classify), ("find_slots", slots), ("draft_reply", draft_reply),
                 ("reply_compliance", reply_compliance), ("reply_approval", reply_approval), ("send", send)]:
        g.add_node(n, f)
    g.add_edge(START, "load_thread")
    g.add_conditional_edges("load_thread", _go("classify"), ["classify", END])
    g.add_conditional_edges("classify", after_classify, ["find_slots", "draft_reply", END])
    g.add_conditional_edges("find_slots", _go("draft_reply"), ["draft_reply", END])
    g.add_conditional_edges("draft_reply", _go("reply_compliance"), ["reply_compliance", END])
    g.add_conditional_edges("reply_compliance", _go("reply_approval"), ["reply_approval", END])
    g.add_conditional_edges("reply_approval", after_approval, ["send", "reply_compliance", END])
    g.add_edge("send", END)
    return g.compile(checkpointer=checkpointer, store=store)
