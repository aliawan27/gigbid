"""Node wrapper: budgets (C4), per-node retries + dead-letter (C7), degraded mode, execution trace and
custom stream events (live progress in the UI)."""
from __future__ import annotations

import asyncio
import functools
import inspect
import time

from langgraph.config import get_stream_writer
from langgraph.errors import GraphInterrupt

from agent.config import CONFIG
from agent.llm import LLMUnavailable, start_ledger, structured
from agent.marketplace_port import MarketplaceUnavailable
from agent.safety import mask_pii

TERMINAL = {"skipped", "watch", "rejected", "needs_attention", "dead_letter", "parked", "submitted", "sent"}


def node(name: str, retries: int = 1):
    def deco(fn):
        async def wrapper(state: dict, *, store=None):
            if state.get("status") in TERMINAL:
                return {}
            b = CONFIG["budgets"]
            if state.get("steps", 0) >= b["max_graph_steps"] or state.get("tokens", 0) >= b["max_tokens_per_job"]:
                msg = f"budget exceeded before '{name}' (steps={state.get('steps', 0)}, tokens={state.get('tokens', 0)})"
                return {"status": "needs_attention", "errors": [msg],
                        "trace": [{"node": name, "event": "budget_exceeded", "detail": msg}]}
            _emit({"node": name, "phase": "start"})
            led = start_ledger()
            t0 = time.time()
            out: dict = {}
            for attempt in range(retries + 1):
                try:
                    out = (await fn(state, store)) or {}
                    break
                except GraphInterrupt:
                    raise
                except MarketplaceUnavailable as e:
                    out = {"status": "parked", "errors": [f"{name}: marketplace unavailable — job parked for retry ({e})"]}
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt >= retries:
                        out = {"status": "dead_letter", "errors": [f"{name}: {type(e).__name__}: {str(e)[:300]}"]}
                    else:
                        await asyncio.sleep(1.0)
            toks = sum(x["in"] + x["out"] for x in led)
            usd = sum(x["usd"] for x in led)
            rec = {"node": name, "latency_s": round(time.time() - t0, 3), "tokens": toks, "usd": round(usd, 6),
                   "llm_calls": [{k: x[k] for k in ("model", "in", "out", "latency")} for x in led],
                   "tools": out.pop("_tools", []), "summary": mask_pii(str(out.pop("_summary", ""))[:300]),
                   "status": out.get("status")}
            out["trace"] = out.get("trace", []) + [rec]
            out["steps"] = 1
            out["tokens"] = toks
            out["cost_usd"] = usd
            _emit({"node": name, "phase": "end", "latency_s": rec["latency_s"], "tokens": toks,
                   "summary": rec["summary"], "status": out.get("status")})
            return out
        functools.update_wrapper(wrapper, fn)
        wrapper.__signature__ = inspect.Signature([
            inspect.Parameter("state", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter("store", inspect.Parameter.KEYWORD_ONLY, default=None)])
        return wrapper
    return deco


def _emit(ev: dict) -> None:
    try:
        get_stream_writer()(ev)
    except Exception:  # noqa: BLE001  (not running inside a streaming graph)
        pass


async def llm_structured(node_name: str, system: str, user: str, schema, max_tokens: int = 1500):
    """Structured LLM call off the event loop (so parallel branches really run in parallel), with the
    fallback model for cheap nodes (C7)."""
    from agent.config import fallback_model, model_for
    try:
        return await asyncio.to_thread(structured, model_for(node_name), system, user, schema, node=node_name,
                                       max_tokens=max_tokens)
    except LLMUnavailable:
        if CONFIG["models"]["nodes"].get(node_name, "small") == "small":
            return await asyncio.to_thread(structured, fallback_model(), system, user, schema, node=node_name,
                                           max_tokens=max_tokens)
        raise


def tool_rec(tool: str, args: dict, result) -> dict:
    return {"tool": tool, "args": {k: mask_pii(str(v))[:120] for k, v in args.items()},
            "result": mask_pii(str(result))[:200]}
