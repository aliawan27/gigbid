// Public blind pairwise panel: which proposal would you reply to? (no login; configuration names never shown)
import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api/client";

type Pair = { pair_ref: number; swap: boolean; job_title: string; job_description: string; left: string; right: string; done: number; total: number };

function raterId(): string {
  let id = "";
  try { id = localStorage.getItem("gigbid_rater") || ""; } catch { /* storage blocked */ }
  if (!id) {
    id = "r" + Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
    try { localStorage.setItem("gigbid_rater", id); } catch { /* ignore */ }
  }
  return id;
}

export default function Panel() {
  const [rater] = useState(raterId);
  const [pair, setPair] = useState<Pair | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.GET("/api/panel/pair", { params: { query: { rater } } }).then(({ data }) => setPair((data as Pair | null) ?? null));
  }, [rater]);
  useEffect(load, [load]);
  const vote = async (choice: "left" | "right" | "tie") => {
    if (!pair) return;
    setBusy(true);
    await api.POST("/api/panel/vote", { body: { rater, pair_ref: pair.pair_ref, swap: pair.swap, choice } });
    setBusy(false);
    window.scrollTo(0, 0);
    load();
  };
  return (
    <main className="panel">
      <h1>Which proposal would you reply to?</h1>
      <p className="muted">You are the client who posted the job below. Read both proposals and pick the one you would answer.
        Proposals are anonymised and shown in random order. About 30 seconds per pair; stop whenever you like.</p>
      {pair === undefined && <p className="muted">Loading…</p>}
      {pair === null && <div className="card empty" data-testid="panel-done">Thank you — you have rated every pair!</div>}
      {pair && (
        <>
          <p className="muted">Pair {pair.done + 1} of {pair.total}</p>
          <div className="card">
            <h3>Job: {pair.job_title}</h3>
            <p className="pre small">{pair.job_description}</p>
          </div>
          <div className="grid2">
            <div className="card"><h3>Proposal 1</h3><p className="pre">{pair.left}</p>
              <button disabled={busy} onClick={() => vote("left")} data-testid="pick-left">I'd reply to Proposal 1</button></div>
            <div className="card"><h3>Proposal 2</h3><p className="pre">{pair.right}</p>
              <button disabled={busy} onClick={() => vote("right")} data-testid="pick-right">I'd reply to Proposal 2</button></div>
          </div>
          <p><button className="ghost" disabled={busy} onClick={() => vote("tie")}>Can't decide / equally good</button></p>
        </>
      )}
    </main>
  );
}
