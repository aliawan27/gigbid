// Live node-by-node progress streamed from LangGraph (SSE).
import { useEffect, useState } from "react";
import { getToken } from "../lib/api/client";

type Ev = { node?: string; phase?: string; latency_s?: number; tokens?: number; summary?: string; status?: string };

export default function RunTimeline({ runId, onEnd }: { runId: string; onEnd?: () => void }) {
  const [events, setEvents] = useState<Ev[]>([]);
  const [done, setDone] = useState(false);
  useEffect(() => {
    setEvents([]); setDone(false);
    const es = new EventSource(`/api/runs/${runId}/events?token=${encodeURIComponent(getToken())}`);
    es.onmessage = (m) => {
      const ev: Ev = JSON.parse(m.data);
      setEvents((x) => [...x, ev]);
      if (ev.phase === "run_end") { setDone(true); es.close(); onEnd?.(); }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [runId, onEnd]);
  const started = events.filter((e) => e.phase === "start").map((e) => e.node);
  const ended = new Map(events.filter((e) => e.phase === "end").map((e) => [e.node, e]));
  return (
    <ol className="timeline" data-testid="run-timeline">
      {started.map((n, i) => {
        const e = ended.get(n);
        return (
          <li key={i} className={e ? "ok" : "busy"}>
            <span className="node">{n}</span>
            {e ? <span className="meta">{e.latency_s}s · {e.tokens} tok</span> : <span className="spinner" aria-label="running" />}
            {e?.summary && <div className="sum">{e.summary}</div>}
          </li>
        );
      })}
      {!done && started.length === 0 && <li className="busy">waiting for the worker…</li>}
      {done && <li className="ok"><b>run finished</b></li>}
    </ol>
  );
}
