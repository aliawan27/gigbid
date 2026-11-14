import { useEffect, useState } from "react";
import { api } from "../lib/api/client";

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function Analytics() {
  const [a, setA] = useState<Any | null>(null);
  useEffect(() => { api.GET("/api/analytics").then(({ data }) => setA(data as Any)); }, []);
  if (!a) return <p className="muted">Loading…</p>;
  const pct = (x: number | null) => (x == null ? "—" : `${Math.round(x * 100)}%`);
  return (
    <section>
      <h2>Analytics</h2>
      <div className="tiles">
        <div className="tile"><span>Jobs analysed</span><b>{a.n_jobs}</b></div>
        <div className="tile"><span>Connects spent</span><b>{a.connects_spent}</b></div>
        <div className="tile"><span>Cost / job (p50)</span><b>${(a.cost_per_job_usd ?? 0).toFixed(4)}</b></div>
        <div className="tile"><span>Cost / proposal (p50)</span><b>${(a.cost_per_proposal_usd ?? 0).toFixed(4)}</b></div>
        <div className="tile"><span>Latency p50 / p95</span><b>{a.latency_p50_s ?? "—"}s / {a.latency_p95_s ?? "—"}s</b></div>
      </div>
      <div className="card">
        <h3>Reply and hire rate by category</h3>
        <table className="matrix">
          <thead><tr><th>Category</th><th>Analysed</th><th>Submitted</th><th>Reply rate</th><th>Hire rate</th></tr></thead>
          <tbody>{Object.entries(a.by_category as Any).map(([k, v]: [string, Any]) => (
            <tr key={k}><td>{k}</td><td>{v.analysed}</td><td>{v.submitted}</td><td>{pct(v.reply_rate)}</td><td>{pct(v.hire_rate)}</td></tr>))}</tbody>
        </table>
        <p className="muted">Outcomes: {Object.entries(a.outcomes).map(([k, v]) => `${k} ${v}`).join(" · ")}</p>
      </div>
      <div className="grid2">
        <div className="card"><h3>Top rejection reasons</h3><ul>{a.top_rejection_reasons.map(([r, n]: [string, number]) => <li key={r}>{r} ({n})</li>)}</ul>
          {a.top_rejection_reasons.length === 0 && <p className="muted">none yet</p>}</div>
        <div className="card"><h3>Top skip reasons</h3><ul>{a.top_skip_reasons.map(([r, n]: [string, number]) => <li key={r}>{r} ({n})</li>)}</ul></div>
      </div>
    </section>
  );
}
