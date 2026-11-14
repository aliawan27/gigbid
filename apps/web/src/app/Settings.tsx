import { useEffect, useState } from "react";
import { api, type MemoryItem, type Prefs } from "../lib/api/client";

type Any = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any

export default function Settings() {
  const [s, setS] = useState<Any | null>(null);
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [mem, setMem] = useState<MemoryItem[]>([]);
  const [msg, setMsg] = useState("");
  const loadMem = () => api.GET("/api/memory").then(({ data }) => setMem(data ?? []));
  useEffect(() => {
    api.GET("/api/settings").then(({ data }) => { setS(data as Any); setPrefs((data as Any)?.prefs); });
    loadMem();
  }, []);
  if (!s || !prefs) return <p className="muted">Loading…</p>;
  const save = async () => { await api.PUT("/api/settings", { body: prefs }); setMsg("Saved"); };
  const forget = async (m: MemoryItem) => {
    await api.DELETE("/api/memory/{namespace}/{key}", { params: { path: { namespace: m.namespace, key: m.key } } });
    loadMem();
  };
  const connectUpwork = async () => {
    const { data } = await api.GET("/api/auth/upwork/connect");
    const d = data as Any;
    if (d?.authorize_url) location.href = d.authorize_url; else setMsg(d?.message ?? "unavailable");
  };
  return (
    <section>
      <h2>Settings</h2>
      <div className="grid2">
        <div className="card">
          <h3>Autonomy and budgets</h3>
          <label>Autonomy
            <select value={prefs.autonomy} onChange={(e) => setPrefs({ ...prefs, autonomy: e.target.value as Prefs["autonomy"] })}>
              <option value="auto_skip_low_fit">Auto-skip low-fit jobs (never auto-send)</option>
              <option value="suggest_only">Suggest only</option>
            </select></label>
          <label>Hourly rate floor<input type="number" value={prefs.rate_floor} onChange={(e) => setPrefs({ ...prefs, rate_floor: +e.target.value })} /></label>
          <label>Weekly Connects budget<input type="number" value={prefs.connects_weekly_budget} onChange={(e) => setPrefs({ ...prefs, connects_weekly_budget: +e.target.value })} /></label>
          <label>Saved searches (comma separated)<input value={(prefs.saved_searches || []).join(",")}
            onChange={(e) => setPrefs({ ...prefs, saved_searches: e.target.value.split(",").map((x) => x.trim()) })} /></label>
          <button onClick={save}>Save</button> {msg && <span role="status">{msg}</span>}
        </div>
        <div className="card">
          <h3>Connected accounts</h3>
          <ul>{s.connected_accounts.map((a: string) => <li key={a}>{a} ✔</li>)}</ul>
          <button className="ghost" onClick={connectUpwork}>Connect Upwork (OAuth)</button>
          <p className="muted small">Live mode only creates drafts you confirm on Upwork. Tokens are stored encrypted.</p>
        </div>
      </div>
      <div className="card" data-testid="memory">
        <h3>What GigBid has learned (long-term memory)</h3>
        <p className="muted small">Style rules are promoted only after the same edit pattern appears in 2+ approved edits; outcome memory only from
          marketplace-confirmed results. Delete anything you disagree with.</p>
        {mem.length === 0 && <p className="muted">Nothing learned yet.</p>}
        <table className="matrix"><tbody>
          {mem.map((m) => (
            <tr key={m.namespace + m.key}><td>{m.namespace}</td><td>{m.key}</td>
              <td className="small">{JSON.stringify(m.value).slice(0, 160)}</td>
              <td><button className="ghost small" onClick={() => forget(m)}>Delete</button></td></tr>
          ))}
        </tbody></table>
      </div>
    </section>
  );
}
