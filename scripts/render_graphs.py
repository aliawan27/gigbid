"""Render both graphs from code (Mermaid + PNG) into docs/images/."""
from pathlib import Path

from agent.graphs.bid_graph import build_bid_graph
from agent.graphs.conversation_graph import build_conversation_graph

out = Path(__file__).resolve().parents[1] / "docs" / "images"
out.mkdir(parents=True, exist_ok=True)
for name, g in (("bid_graph", build_bid_graph()), ("conversation_graph", build_conversation_graph())):
    mm = g.get_graph().draw_mermaid()
    (out / f"{name}.mmd").write_text(mm, encoding="utf-8")
    try:
        (out / f"{name}.png").write_bytes(g.get_graph().draw_mermaid_png())
    except Exception as e:  # noqa: BLE001
        print("png render failed:", e)
    print("rendered", name)
