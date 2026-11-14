import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import EvidenceHover from "../components/EvidenceHover";
import { api, errText } from "../lib/api/client";

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function Studio() {
  const { id = "" } = useParams();
  const [p, setP] = useState<Any | null>(null);
  const [text, setText] = useState("");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  useEffect(() => {
    api.GET("/api/jobs/{job_id}", { params: { path: { job_id: id } } }).then(({ data }) => {
      const pa = data?.pending_approval as Any | null;
      setP(pa ?? null);
      if (pa) setText(pa.draft.cover_letter);
    });
  }, [id]);
  if (p === null) return <p className="muted empty">No proposal waiting for approval on this job (it may already be submitted or rejected).</p>;
  const edited = text !== p.draft.cover_letter;
  const decide = async (action: "approve" | "edit" | "reject") => {
    if (action === "reject" && !reason.trim()) return setMsg("Give a reason to reject.");
    setBusy(true);
    const { error } = await api.POST("/api/proposals/{job_id}/decision", {
      params: { path: { job_id: id } },
      body: { action, edited_text: action === "edit" ? text : null, reason: reason || null },
    });
    setBusy(false);
    if (error) return setMsg(errText(error));
    setMsg(action === "approve" ? "Approved — submitting exactly once…" : action === "edit" ? "Edit saved — re-checking compliance…" : "Rejected.");
    setTimeout(() => nav(`/jobs/${id}`), 1200);
  };
  const regen = async (i: number) => {
    setBusy(true);
    const { data, error } = await api.POST("/api/proposals/{job_id}/regenerate", { params: { path: { job_id: id } }, body: { paragraph_index: i, instruction: "" } });
    setBusy(false);
    if (error) return setMsg(errText(error));
    setText((data as Any).cover_letter);
  };
  const crit = (p.critiques || []).slice(-1)[0] || {};
  const comp = p.compliance || {};
  const dry = p.dry_run || {};
  const checks: Any[] = p.claim_checks || [];
  return (
    <section className="studio">
      <h2>Proposal studio — {p.title}</h2>
      <div className="grid2">
        <div className="card">
          <h3>Draft <small className="muted">(hover E# to see the evidence)</small></h3>
          <EvidenceHover text={text} evidenceMap={p.draft.evidence_map || {}} evidence={p.evidence || []} />
          <label>Edit the cover letter
            <textarea data-testid="draft-editor" rows={12} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <div className="row wrap">
            {text.split("\n\n").map((_, i) => <button key={i} className="ghost small" disabled={busy} onClick={() => regen(i)}>Regenerate ¶{i + 1}</button>)}
          </div>
          {(p.draft.screening_answers || []).length > 0 && <>
            <h3>Screening answers</h3>
            {p.draft.screening_answers.map((a: string, i: number) => <p key={i} className="pre">{a}</p>)}
          </>}
        </div>
        <div>
          <div className="card">
            <h3>Dry-run preview (what will be sent)</h3>
            <p>Bid <b>${p.price?.amount}</b> · costs <b>{dry.connects_cost}</b> Connects · balance after <b>{dry.connects_balance_after}</b></p>
            <p className="muted small">{p.price?.rationale}</p>
          </div>
          <div className="card">
            <h3>Critic</h3>
            <p>{crit.approve ? "✔ approved" : "revisions requested"} · grounding {crit.grounding}/5 · personalisation {crit.personalisation}/5</p>
            <ul>{(crit.issues || []).map((x: string) => <li key={x}>{x}</li>)}</ul>
            <h3>Compliance</h3>
            <ul>{(comp.violations || []).map((v: Any, i: number) => <li key={i}><b>{v.rule_id}</b>: {v.text}</li>)}</ul>
            {(comp.violations || []).length === 0 && <p>✔ no policy issues</p>}
            <h3>Claim verification</h3>
            <ul className="claims">{checks.map((c, i) => <li key={i} className={c.label}>{c.label}: {c.claim}</li>)}</ul>
          </div>
          <div className="card">
            <h3>Risk</h3>
            <p>risk {p.risk_report?.score} · {(p.risk_report?.flags || []).join(", ") || "no flags"}</p>
          </div>
          <div className="card actions">
            {msg && <p role="status" data-testid="decision-msg">{msg}</p>}
            <button disabled={busy} data-testid="approve" onClick={() => decide(edited ? "edit" : "approve")}>
              {edited ? "Save edit & re-check" : "Approve & submit"}</button>
            <label>Reject reason<input data-testid="reject-reason" value={reason} onChange={(e) => setReason(e.target.value)} /></label>
            <button disabled={busy} className="danger" data-testid="reject" onClick={() => decide("reject")}>Reject</button>
          </div>
        </div>
      </div>
    </section>
  );
}
