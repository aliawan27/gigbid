"""Loaders + chunkers for a freelancer portfolio corpus.

Every chunk carries metadata: owner (persona/user), item_id, type, project, skills, date, industry, outcome.
Supported sources: Markdown (CV, case studies, READMEs), code files, PDF CVs, reviews.json, proposals.json,
and repos fetched through the GitHub MCP server (rag/ingest/github_mcp.py).
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

PERSONA_ROOT = Path(__file__).resolve().parents[2] / "data" / "personas"
if not PERSONA_ROOT.exists():  # installed as a package (uvx): data shipped as gigbid_data
    import importlib.util
    spec = importlib.util.find_spec("gigbid_data")
    if spec and spec.submodule_search_locations:
        PERSONA_ROOT = Path(list(spec.submodule_search_locations)[0]) / "personas"


@dataclass
class Chunk:
    chunk_id: str
    item_id: str
    owner: str
    type: str
    text: str
    project: str | None = None
    title: str = ""
    skills: list[str] = field(default_factory=list)
    date: str | None = None
    industry: str | None = None
    outcome: str | None = None
    view: str = "body"  # for multi-vector items: summary/readme/code/body
    context: str = ""   # contextual-retrieval prefix (V6)

    def dict(self):
        return asdict(self)


def _fixed_chunks(text: str, size: int = 400, overlap: int = 50) -> list[str]:
    out, i = [], 0
    while i < len(text):
        out.append(text[i: i + size])
        i += size - overlap
    return out or [text]


def _sections(md: str) -> list[str]:
    parts = re.split(r"\n(?=#{1,3} )", md)
    return [p.strip() for p in parts if p.strip()]


def load_item_texts(owner: str, root: Path | None = None) -> list[dict]:
    """Returns item-level records: {meta..., text, title}."""
    import os
    own_dir = os.getenv("GIGBID_PORTFOLIO_DIR")
    if own_dir and owner == "me":  # an outside freelancer pointing the MCP server at their own folder
        return [load_file(f, owner) for f in sorted(Path(own_dir).rglob("*"))
                if f.is_file() and f.suffix.lower() in (".md", ".txt", ".pdf", ".py", ".js", ".ts")]
    base = (root or PERSONA_ROOT) / owner
    index = json.loads((PERSONA_ROOT / "index.json").read_text()).get(owner, []) if (root is None and (PERSONA_ROOT / "index.json").exists()) else []
    meta = {m["id"]: m for m in index}
    items = []
    reviews = {r["id"]: r for r in json.loads((base / "reviews.json").read_text())} if (base / "reviews.json").exists() else {}
    props = {p["id"]: p for p in json.loads((base / "proposals.json").read_text())} if (base / "proposals.json").exists() else {}
    for mid, m in meta.items():
        if m["type"] == "review":
            text = reviews[mid]["text"]
        elif m["type"] == "proposal":
            text = props[mid]["text"]
        else:
            text = (base / m["path"]).read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip() if m["type"] in ("case_study", "readme", "cv") else f"{m['type']} {m.get('project')}"
        items.append({**m, "text": text, "title": title, "owner": owner})
    # user uploads (incremental, see apps/api): data/uploads/<owner>/*.md|*.pdf|*.py
    up = PERSONA_ROOT.parent / "uploads" / owner
    if up.exists():
        for f in sorted(up.iterdir()):
            items.append(load_file(f, owner))
    return items


def load_file(f: Path, owner: str) -> dict:
    if f.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        text = "\n".join(p.extract_text() or "" for p in PdfReader(str(f)).pages)
        typ = "cv"
    else:
        text = f.read_text(encoding="utf-8", errors="ignore")
        typ = "code" if f.suffix in (".py", ".js", ".ts", ".go") else "case_study"
    return {"id": f"{owner}:upload:{f.stem}", "type": typ, "project": f.stem, "skills": [], "industry": None,
            "date": None, "text": text, "title": f.stem, "owner": owner}


def chunk_items(items: list[dict], strategy: str = "structural") -> list[Chunk]:
    chunks = []
    for it in items:
        if strategy == "fixed":
            pieces = [(p, "body") for p in _fixed_chunks(it["text"])]
        elif strategy == "multivector" and it["type"] in ("readme", "code", "case_study"):
            # V5: each view indexed separately, grouped back to one project at query time
            summary = f"{it['title']}. Skills: {', '.join(it.get('skills') or [])}. Industry: {it.get('industry')}"
            pieces = [(summary, "summary")] + [(s, it["type"]) for s in _sections(it["text"])]
        else:
            pieces = [(s, "body") for s in (_sections(it["text"]) if it["type"] in ("case_study", "readme", "cv") else [it["text"]])]
        for k, (p, view) in enumerate(pieces):
            chunks.append(Chunk(chunk_id=f"{it['id']}#{k}", item_id=it["id"], owner=it["owner"], type=it["type"], text=p,
                                project=it.get("project"), title=it.get("title", ""), skills=it.get("skills") or [],
                                date=it.get("date"), industry=it.get("industry"), outcome=it.get("outcome"), view=view))
    return chunks
