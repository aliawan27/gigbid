"""LangSmith tracing with PII masking (E3/E4). One trace per graph run (run_id = the request's trace id); every Groq call
is an LLM span with token usage, so the trace shows tokens per node. Inputs/outputs are masked before upload."""
from __future__ import annotations

import os
from functools import lru_cache

from agent.safety import mask_obj


def enabled() -> bool:
    return bool(os.getenv("LANGSMITH_API_KEY")) and os.getenv("GIGBID_TRACING", "1") == "1"


@lru_cache(1)
def client():
    from langsmith import Client
    return Client(hide_inputs=mask_obj, hide_outputs=mask_obj)


def callbacks() -> list:
    if not enabled():
        return []
    from langchain_core.tracers.langchain import LangChainTracer
    return [LangChainTracer(project_name=os.getenv("LANGSMITH_PROJECT", "gigbid"), client=client())]


def llm_span(fn):
    """Decorator for agent.llm.chat: records an LLM run (model, messages, usage) under the current trace."""
    if not enabled():
        return fn
    from langsmith import traceable

    def outputs(out):
        u = (out or {}).get("usage", {}) if isinstance(out, dict) else {}
        return {"content": (out or {}).get("content", "") if isinstance(out, dict) else str(out),
                "usage_metadata": {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0),
                                   "total_tokens": u.get("total_tokens", 0)}}
    return traceable(run_type="llm", name="groq.chat", client=client(), process_outputs=outputs,
                     metadata={"ls_provider": "groq"})(fn)
