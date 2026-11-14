import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import RunTimeline from "../components/RunTimeline";
import { api, type RunRow } from "../lib/api/client";

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export function RunList() {
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [q] = useSearchParams();
  const job = q.get("job");
  useEffect(() => {
    const load = () => api.GET("/api/runs").then(({ data }) => setRuns((data ?? []).filter((r) => !job || r.ref_id === job)));
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [job]);
  return (
    <section>
      <h2>Agent runs {job && <small className="muted">for {job}</small>}</h2>
      <div className="table">
        {runs.map((r) => (
          <Link key={r.id} to={`/runs/${r.id}`} className="tr">
            <span className="title">{r.kind} · {r.ref_id}</span>
            <span className={`badge ${r.status === "running" ? "warn" : ""}`}>{r.status}</span>
            <span className="num">{r.latency_s ?? "…"}s</span>
            <span className="num">{r.tokens ?? 0} tok</span>
            <span className="num">${(r.cost_usd ?? 0).toFixed(5)}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}

export function RunView() {
  const { id = "" } = useParams();
  const [d, setD] = useState<Any | null>(null);
  const [trace, setTrace] = useState<Any | null>(null);
  useEffect(() => {
    api.GET("/api/runs/{run_id}", { params: { path: { run_id: id } } }).then(({ data }) => {
      setD(data as Any);
      const ref = (data as Any)?.run?.ref_id;
      if (ref && String((data as Any).run.kind).startsWith("bid"))
        api.GET("/api/jobs/{job_id}/trace", { params: { path: { job_id: ref } } }).then(({ data: t }) => setTrace(t as Any));
    });
  }, [id]);
  if (!d) return <p className="muted">Loading…</p>;
  return (
    <section>
      <h2>Run {id} <small className="muted">{d.run?.kind} · {d.run?.ref_id} · {d.run?.status}</small></h2>
      <p>Trace id <code>{d.run?.trace_id}</code> {d.trace_url && <a href={d.trace_url} target="_blank" rel="noreferrer">open full trace (LangSmith)</a>}</p>
      <div className="card"><h3>Live node-by-node progress</h3><RunTimeline runId={id} /></div>
      {trace && (
        <div className="card">
          <h3>Execution trace (every node, tool call, tokens, cost)</h3>
          <table className="matrix">
            <thead><tr><th>Node</th><th>Latency</th><th>Tokens</th><th>USD</th><th>Tools</th><th>Summary</th></tr></thead>
            <tbody>{trace.trace.map((t: Any, i: number) => (
              <tr key={i}><td>{t.node}</td><td>{t.latency_s}s</td><td>{t.tokens}</td><td>{t.usd}</td>
                <td>{(t.tools || []).map((x: Any) => x.tool).join(", ")}</td><td>{t.summary}</td></tr>))}</tbody>
          </table>
          <p className="muted">{trace.checkpoints.length} checkpoints stored (replayable from any node).</p>
        </div>
      )}
    </section>
  );
}
