import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type JobRow } from "../lib/api/client";

const COLS = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"] as const;

function column(j: JobRow): (typeof COLS)[number] | null {
  if (j.status === "awaiting_approval" || j.status === "resuming") return "drafted";
  if (j.status === "rejected") return "lost";
  if (j.status !== "submitted") return null;
  const m = j.marketplace_status;
  if (m === "ignored") return "lost";
  if (m && (COLS as readonly string[]).includes(m)) return m as (typeof COLS)[number];
  return "submitted";
}

export default function Pipeline() {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  useEffect(() => {
    const load = () => api.GET("/api/jobs").then(({ data }) => setJobs(data ?? []));
    load();
    const t = setInterval(load, 5000); // cards update as marketplace events are synced by the worker
    return () => clearInterval(t);
  }, []);
  return (
    <section>
      <h2>Pipeline</h2>
      <div className="kanban" data-testid="kanban">
        {COLS.map((c) => (
          <div key={c} className="col">
            <h4>{c} <span className="muted">{jobs.filter((j) => column(j) === c).length}</span></h4>
            {jobs.filter((j) => column(j) === c).map((j) => (
              <Link key={j.job_id} to={`/jobs/${j.job_id}`} className="kcard">{j.title}<small>{j.price ? `$${j.price}` : ""}</small></Link>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
