import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errText, type Prefs } from "../lib/api/client";

const personas = [
  ["ai_ml", "AI/ML engineer (synthetic persona)"], ["fullstack", "Full-stack web developer (synthetic persona)"],
  ["data_analyst", "Data analyst (synthetic persona)"], ["own", "My own profile (upload portfolio)"],
] as const;

export default function Onboarding() {
  const [persona, setPersona] = useState<(typeof personas)[number][0]>("ai_ml");
  const [prefs, setPrefs] = useState<Prefs>({ rate_floor: 40, connects_weekly_budget: 120, saved_searches: [""], categories: [],
    min_budget: 0, autonomy: "auto_skip_low_fit", marketplace: "gigsim" });
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState("");
  const nav = useNavigate();
  const save = async () => {
    const { error } = await api.POST("/api/auth/onboarding", { body: { persona, prefs } });
    if (error) return setMsg(errText(error));
    if (file) {
      const fd = new FormData();
      fd.append("file", file);
      await fetch("/api/auth/portfolio", { method: "POST", body: fd, headers: { Authorization: `Bearer ${localStorage.getItem("gigbid_token")}` } });
    }
    nav("/inbox");
  };
  return (
    <div className="center">
      <div className="card narrow" data-testid="onboarding">
        <h1>Set up GigBid</h1>
        <fieldset>
          <legend>Profile</legend>
          {personas.map(([id, label]) => (
            <label key={id} className="radio"><input type="radio" name="persona" value={id} checked={persona === id}
              onChange={() => setPersona(id)} /> {label}</label>
          ))}
        </fieldset>
        <label>Marketplace
          <select value={prefs.marketplace} onChange={(e) => setPrefs({ ...prefs, marketplace: e.target.value as Prefs["marketplace"] })}>
            <option value="gigsim">GigSim (simulator)</option>
            <option value="upwork_live">Upwork (OAuth, live mode — drafts only)</option>
          </select>
        </label>
        <label>Upload portfolio (CV PDF, case study .md, code)<input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
        <label>Hourly rate floor (USD)<input type="number" value={prefs.rate_floor} onChange={(e) => setPrefs({ ...prefs, rate_floor: +e.target.value })} /></label>
        <label>Weekly Connects budget<input type="number" value={prefs.connects_weekly_budget} onChange={(e) => setPrefs({ ...prefs, connects_weekly_budget: +e.target.value })} /></label>
        <label>Saved search (keywords, blank = all)<input value={prefs.saved_searches?.[0] ?? ""} onChange={(e) => setPrefs({ ...prefs, saved_searches: [e.target.value] })} /></label>
        <label>Minimum budget filter (USD)<input type="number" value={prefs.min_budget} onChange={(e) => setPrefs({ ...prefs, min_budget: +e.target.value })} /></label>
        {msg && <p className="error">{msg}</p>}
        <button onClick={save} data-testid="finish-onboarding">Start</button>
      </div>
    </div>
  );
}
