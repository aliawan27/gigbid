import { useCallback, useEffect, useState } from "react";
import { api, errText } from "../lib/api/client";

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

function Thread({ t, reload }: { t: Any; reload: () => void }) {
  const p = t.pending;
  const [text, setText] = useState(p?.reply?.text ?? "");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState("");
  useEffect(() => setText(p?.reply?.text ?? ""), [p?.reply?.text]);
  const decide = async (action: "approve" | "edit" | "reject") => {
    const edited = text !== p.reply.text;
    const { error } = await api.POST("/api/messages/{thread_id}/decision", {
      params: { path: { thread_id: t.thread_id }, query: { graph_thread: t.graph_thread } },
      body: { action: action === "approve" && edited ? "edit" : action, edited_text: edited ? text : null, reason: reason || null },
    });
    setMsg(error ? errText(error) : action === "reject" ? "Rejected" : edited ? "Edit saved; re-checking" : "Approved; sending once");
    setTimeout(reload, 1500);
  };
  const draft = async () => {
    await api.POST("/api/messages/{thread_id}/draft", { params: { path: { thread_id: t.thread_id }, query: { n: t.messages.length } } });
    setMsg("Drafting a reply…");
  };
  return (
    <div className="card" data-testid="thread">
      <h3>{t.job_title || t.job_id} <small className="muted">{t.thread_id} · agent: {t.agent_status ?? "idle"}</small></h3>
      <div className="msgs">
        {t.messages.map((m: Any, i: number) => <p key={i} className={`msg ${m.from}`}><b>{m.from}:</b> {m.text}</p>)}
      </div>
      {p ? (
        <div className="suggest">
          <p className="muted">Suggested reply · intent <b>{p.intent?.intent}</b>
            {p.reply?.proposed_slots?.length ? ` · slots: ${p.reply.proposed_slots.map((s: string) => s.slice(0, 16)).join(", ")}` : ""}</p>
          <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} data-testid="reply-editor" />
          <div className="row wrap">
            <button onClick={() => decide("approve")} data-testid="approve-reply">Approve & send</button>
            <input placeholder="reject reason" value={reason} onChange={(e) => setReason(e.target.value)} />
            <button className="danger" onClick={() => decide("reject")}>Reject</button>
          </div>
        </div>
      ) : t.messages[t.messages.length - 1]?.from === "client" && t.agent_status !== "running" ? (
        <button className="ghost" onClick={draft}>Draft reply now</button>
      ) : null}
      {msg && <p role="status">{msg}</p>}
    </div>
  );
}

export default function Messages() {
  const [threads, setThreads] = useState<Any[] | null>(null);
  const [err, setErr] = useState("");
  const load = useCallback(() => api.GET("/api/messages").then(({ data, error }) => {
    if (error) setErr("Marketplace unavailable — messages cannot be loaded right now."); else { setErr(""); setThreads(data as Any[]); }
  }), []);
  useEffect(() => { load(); const t = setInterval(load, 6000); return () => clearInterval(t); }, [load]);
  return (
    <section>
      <h2>Messages</h2>
      {err && <p className="error">{err}</p>}
      {threads?.length === 0 && <p className="muted empty">No client conversations yet. Replies to submitted proposals appear here.</p>}
      {(threads || []).map((t) => <Thread key={t.thread_id} t={t} reload={load} />)}
    </section>
  );
}
