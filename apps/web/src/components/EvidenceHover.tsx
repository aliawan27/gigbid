// Renders a draft where every [E#] citation shows the evidence behind the claim on hover / focus.
type Ev = { id: string; title?: string | null; type?: string; snippet?: string; source?: string };

export default function EvidenceHover({ text, evidenceMap, evidence }: {
  text: string; evidenceMap: Record<string, string>; evidence: Ev[];
}) {
  const byId = Object.fromEntries((evidence || []).map((e) => [e.id, e]));
  const parts = text.split(/(\[E\d+\])/g);
  return (
    <div className="letter" data-testid="draft-preview">
      {parts.map((p, i) => {
        const m = p.match(/^\[(E\d+)\]$/);
        if (!m) return <span key={i}>{p}</span>;
        const ev = byId[evidenceMap?.[m[1]]];
        return (
          <span key={i} className="cite" tabIndex={0} data-testid="citation">
            {m[1]}
            <span className="tip" role="tooltip">
              <b>{ev?.title || evidenceMap?.[m[1]] || "missing evidence"}</b>
              <em>{ev?.type} · {ev?.source}</em>
              <span>{(ev?.snippet || "").slice(0, 260)}</span>
            </span>
          </span>
        );
      })}
    </div>
  );
}
