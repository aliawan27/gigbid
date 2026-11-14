"""Bid graph (one thread per job), hand-written LangGraph StateGraph.

scout -> [Send] analyst || risk_assessor || fit_matcher -> decide -(bid)-> pricing -> writer -> verifier -> critic
critic -(revise, max 2)-> writer ; critic -> compliance_guard -(blocked)-> END ; compliance_guard -> preview -> human_approval
approval -(approve)-> submit ; approval -(edit)-> compliance ; approval -(reject)-> END
Any node may set status parked / dead_letter / needs_attention, which routes to END."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.config import CONFIG
from agent.nodes.analyst import analyst
from agent.nodes.approval import approval, preview, submit
from agent.nodes.compliance import compliance
from agent.nodes.critic import critic
from agent.nodes.decision import decide
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.pricing import pricing
from agent.nodes.risk_assessor import risk_assessor
from agent.nodes.scout import scout
from agent.nodes.verifier import verifier
from agent.nodes.writer import writer
from agent.state import BidState

STOP = {"skipped", "watch", "rejected", "needs_attention", "dead_letter", "parked", "submitted"}


def _go(target):
    def route(s):
        return END if s.get("status") in STOP else target
    return route


def fan_out(s):
    if s.get("status") in STOP:
        return END
    return [Send("analyst", s), Send("risk_assessor", s), Send("fit_matcher", s)]


def after_critic(s):
    if s.get("status") in STOP:
        return END
    last = (s.get("critiques") or [{}])[-1]
    if not last.get("approve") and s.get("revisions", 0) < CONFIG["budgets"]["max_revisions"]:
        return "writer"
    return "compliance_guard"


def after_approval(s):
    st = s.get("status")
    if st == "approved":
        return "submit"
    if st == "running":  # user edited -> re-check compliance, then ask again
        return "compliance_guard"
    return END


def build_bid_graph(checkpointer=None, store=None):
    g = StateGraph(BidState)
    for name, fn in [("scout", scout), ("analyst", analyst), ("risk_assessor", risk_assessor), ("fit_matcher", fit_matcher),
                     ("decide", decide), ("pricing", pricing), ("writer", writer), ("verifier", verifier),
                     ("critic", critic), ("compliance_guard", compliance), ("preview", preview), ("human_approval", approval),
                     ("submit", submit)]:
        g.add_node(name, fn)
    g.add_edge(START, "scout")
    g.add_conditional_edges("scout", fan_out, ["analyst", "risk_assessor", "fit_matcher", END])
    g.add_edge(["analyst", "risk_assessor", "fit_matcher"], "decide")
    g.add_conditional_edges("decide", _go("pricing"), ["pricing", END])
    g.add_conditional_edges("pricing", _go("writer"), ["writer", END])
    g.add_conditional_edges("writer", _go("verifier"), ["verifier", END])
    g.add_conditional_edges("verifier", _go("critic"), ["critic", END])
    g.add_conditional_edges("critic", after_critic, ["writer", "compliance_guard", END])
    g.add_conditional_edges("compliance_guard", _go("preview"), ["preview", END])
    g.add_conditional_edges("preview", _go("human_approval"), ["human_approval", END])
    g.add_conditional_edges("human_approval", after_approval, ["submit", "compliance_guard", END])
    g.add_edge("submit", END)
    return g.compile(checkpointer=checkpointer, store=store)
