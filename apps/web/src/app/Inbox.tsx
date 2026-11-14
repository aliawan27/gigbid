import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type JobRow } from "../lib/api/client";

export function RiskBadge({ j }: { j: Pick<JobRow, "risk" | "scam" | "flags"> }) {
  if (j.risk == null) return <span className="badge">…</span>;
  const cls = j.scam ? "bad" : j.risk > 0.5 ? "warn" : "good";
  return <span className={`badge ${cls}`} title={(j.flags || []).join(", ")}>{j.scam ? "SCAM" : `risk ${j.risk}`}</span>;
}

export default function Inbox() {
  const [jobs, setJobs] = useState<JobRow[] | null>(null);
  const [filter, setFilter] = useState("all");
  const [err, setErr] = useState("");
  const load = useCallback(() => api.GET("/api/jobs").then(({ data, error }) => {
    if (error) setErr("Could not load jobs"); else setJobs(data ?? []);
  }), []);
  useEffect(() => { load(); const id = setInterval(load, 5000); return () => clearInterval(id); }, [load]);
  const scout = async () => { await api.POST("/api/jobs/scout"); load(); };
  const shown = (jobs || []).filter((j) => filter === "all" || j.action === filter || j.status === filter);
  return (
    <section>
      <div className="row between">
        <h2>Job inbox</h2>
        <div className="row">
          <select aria-label="Filter" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All</option><option value="awaiting_approval">Awaiting approval</option>
            <option value="bid">Bid</option><option value="watch">Watch</option><option value="skip">Skip</option>
          </select>
          <button onClick={scout}>Scout now</button>
        </div>
      </div>
      {err && <p className="error">{err}</p>}
      {jobs === null && <p className="muted">Loading…</p>}
      {jobs?.length === 0 && <p className="muted empty">No jobs yet. GigBid scouts your saved searches on a schedule — or press “Scout now”.</p>}
      <div className="table" role="table">
        {shown.map((j) => (
          <Link key={j.job_id} to={`/jobs/${j.job_id}`} className="tr" data-testid="job-row">
            <span className="title">{j.title}</span>
            <span className="badge">{j.fit != null ? `fit ${j.fit}` : "fit …"}</span>
            <RiskBadge j={j} />
            <span className={`badge act-${j.action}`}>{j.status === "awaiting_approval" ? "APPROVE" : ["submitted", "rejected", "queued", "analysing", "resuming", "parked", "dead_letter", "needs_attention"].includes(j.status) ? j.status : j.action ?? j.status}</span>
            <span className="num">{j.price ? `$${j.price}` : j.budget ? `budget $${j.budget}` : ""}</span>
            <span className="num">{j.connects_cost ?? "?"} Connects</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
