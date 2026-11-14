import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, setToken, type Health, type UserOut } from "../lib/api/client";

const links = [
  ["/inbox", "Inbox"], ["/pipeline", "Pipeline"], ["/messages", "Messages"], ["/runs", "Agent runs"],
  ["/analytics", "Analytics"], ["/settings", "Settings"],
];

export default function Layout() {
  const [health, setHealth] = useState<Health | null>(null);
  const [me, setMe] = useState<UserOut | null>(null);
  const [menu, setMenu] = useState(false);
  const nav = useNavigate();

  useEffect(() => {
    api.GET("/api/auth/me").then(({ data }) => {
      if (data) { setMe(data); if (!data.owner) nav("/onboarding"); }
    });
    const tick = () => api.GET("/api/health").then(({ data }) => setHealth(data ?? null)).catch(() => setHealth(null));
    tick();
    const id = setInterval(tick, 10000);
    return () => clearInterval(id);
  }, [nav]);

  return (
    <div className="shell">
      <header className="top">
        <strong className="brand">GigBid</strong>
        <button className="menu-btn" aria-label="Menu" onClick={() => setMenu(!menu)}>☰</button>
        <nav className={menu ? "open" : ""} onClick={() => setMenu(false)}>
          {links.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
        </nav>
        <span className="who">{me?.username} · {me?.owner}</span>
        <button className="ghost" onClick={() => { setToken(""); nav("/login"); }}>Sign out</button>
      </header>
      {health && health.degraded && (
        <div className="banner" role="alert" data-testid="degraded-banner">
          Marketplace unavailable — {!health.marketplace ? "the marketplace server is down" : "a tool server is down"}.
          New jobs are queued and will be processed when it recovers; nothing is lost.
        </div>
      )}
      <main><Outlet /></main>
    </div>
  );
}
