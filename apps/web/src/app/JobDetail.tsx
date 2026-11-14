import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import RunTimeline from "../components/RunTimeline";
import { api, type JobDetail as JD } from "../lib/api/client";
import { RiskBadge } from "./Inbox";

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function JobDetail() {
  const { id = "" } = useParams();
  const [d, setD] = useState<JD | null>(null);
  const [run, setRun] = useState<string | null>(null);
  const load = useCallback(() => {
    api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } }).then(({ data }) => setD(data ?? null));
    api.GET("/api/stream/latest", { params: { query: { job_id: id } } }).then(({ data }) => {
      const r = data as Any | null;
      if (r && ["running"].includes(r.status)) setRun(r.id);
    });
  }, [id]);
  useEffect(() => { load(); const t = setInterval(load, 6000); return () => clearInterval(t); }, [load]);
  if (!d) return <p className="muted">Loading…</p>;
  const s = d.state as Any;
  const job = d.job as Any;
  const spec = s.job_spec || {}, risk = s.risk_report || {}, fit = s.fit_report || {}, dec = s.decision || {}, price = s.price || {};
  const analyse = async () => { await api.POST("/api/jobs/{job_id}/analyse", { params: { path: { job_id: id } } }); setTimeout(load, 1500); };
  return (
    <section className="detail">
      <div className="row between">
        <h2>{job.title}</h2>
        <div className="row">
          {d.status === "awaiting_approval" && <Link className="button" to={`/studio/${id}`} data-testid="open-studio">Open proposal studio</Link>}
          {["queued", "parked", "dead_letter", "watch", "skipped", "rejected"].includes(d.status) &&
            <button onClick={analyse}>{d.status === "queued" ? "Analyse now" : "Re-analyse"}</button>}
          <Link to={`/runs?job=${id}`} className="ghost button">Trace</Link>
        </div>
      </div>
      <p className="muted">Status: <b>{d.status}</b> · budget ${job.budget} · {job.connects_cost} Connects · client {job.client_id}</p>
      {run && <div className="card"><h3>Live agent progress</h3><RunTimeline runId={run} onEnd={load} /></div>}
      <div className="grid2">
        <div className="card">
          <h3>Decision</h3>
          <p><span className={`badge act-${dec.action}`}>{dec.action || "pending"}</span> {dec.reason}</p>
          {(s.errors || []).length > 0 && <p className="error">{(s.errors || []).join("; ")}</p>}
          <h3>Job post <small className="muted">(untrusted)</small></h3>
          <p className="pre">{job.description}</p>
        </div>
        <div className="card">
          <h3>JobSpec</h3>
          <dl>
            <dt>Requirements</dt><dd>{(spec.requirements || []).join(", ")}</dd>
            <dt>Deliverables</dt><dd>{(spec.deliverables || []).join("; ")}</dd>
            <dt>Hidden needs</dt><dd>{(spec.hidden_needs || []).join("; ") || "—"}</dd>
            <dt>Complexity</dt><dd>{spec.complexity} {spec.vague ? "(vague post)" : ""}</dd>
            <dt>Screening</dt><dd>{(spec.screening_questions || []).join(" | ") || "—"}</dd>
          </dl>
        </div>
        <div className="card">
          <h3>Risk report <RiskBadge j={{ risk: risk.score, scam: risk.scam, flags: risk.flags }} /></h3>
          <p>{risk.explanation}</p>
          <p>Flags: {(risk.flags || []).join(", ") || "none"} · client quality {risk.client_quality}</p>
          {(risk.injection_hits || []).length > 0 && <p className="warn-text" data-testid="injection">Injected instructions detected and ignored: “{risk.injection_hits.join(" / ")}”</p>}
        </div>
        <div className="card">
          <h3>Price</h3>
          <p className="big">{price.amount ? `$${price.amount}` : "—"}</p>
          <p className="muted">{price.rationale}</p>
        </div>
      </div>
      <div className="card">
        <h3>Requirement → evidence matrix (fit {fit.score})</h3>
        <table className="matrix">
          <thead><tr><th>Requirement</th><th>Covered</th><th>Evidence</th></tr></thead>
          <tbody>
            {(fit.matches || []).map((m: Any) => (
              <tr key={m.requirement}><td>{m.requirement}</td><td>{m.covered ? "✔" : "✘"}</td>
                <td>{(m.evidence_ids || []).join(", ") || <span className="muted">{m.note}</span>}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
