import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errText, setToken } from "../lib/api/client";

export default function Login() {
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const go = async (mode: "login" | "register") => {
    setBusy(true); setErr("");
    const { data, error } = await api.POST(mode === "login" ? "/api/auth/login" : "/api/auth/register",
      { body: { username: u, password: p } });
    setBusy(false);
    if (error || !data) return setErr(errText(error) || "failed");
    setToken(data.token);
    nav(data.user.owner ? "/inbox" : "/onboarding");
  };
  return (
    <div className="center">
      <form className="card narrow" onSubmit={(e) => { e.preventDefault(); go("login"); }}>
        <h1>GigBid</h1>
        <p className="muted">Your freelance copilot. Agents find, judge and draft; you decide.</p>
        <label>Username<input name="username" value={u} onChange={(e) => setU(e.target.value)} autoComplete="username" /></label>
        <label>Password<input name="password" type="password" value={p} onChange={(e) => setP(e.target.value)} autoComplete="current-password" /></label>
        {err && <p className="error" role="alert">{err}</p>}
        <div className="row">
          <button type="submit" disabled={busy}>Sign in</button>
          <button type="button" className="ghost" disabled={busy} onClick={() => go("register")}>Create account</button>
        </div>
      </form>
    </div>
  );
}
