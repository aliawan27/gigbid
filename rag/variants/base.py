"""Composable retrieval pipeline. Each variant file (v0_naive.py, v1_decompose.py, ...) is just a config of
this pipeline, so one command (evals/runners/rag_eval.py) re-runs the full comparison and the ablation."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field

from rag.index.store import Index, embed, reranker, rrf
from rag.ingest.loaders import chunk_items, load_item_texts

GOLD_TYPES = ("case_study", "readme", "code", "review", "cv")  # proposals are searched separately (phrasing)


@dataclass
class RAGConfig:
    name: str
    chunking: str = "structural"      # fixed | structural | multivector
    decompose: bool = False           # V1: one retrieval per requirement, merged with RRF
    hybrid: bool = False              # V2: BM25 + dense with RRF
    rerank: bool = False              # V3: cross-encoder rerank of top candidates
    outcome_boost: float = 0.0        # V4: boost evidence from projects whose proposals won / got replies
    corrective: bool = False          # V8: grade -> re-query -> refuse (LangGraph sub-graph)
    candidates: int = 30
    types: tuple[str, ...] = field(default=GOLD_TYPES)


_index_cache: dict[tuple, tuple[Index, dict]] = {}


def _uploads_version(owner: str) -> float:
    from rag.ingest.loaders import PERSONA_ROOT
    up = PERSONA_ROOT.parent / "uploads" / owner
    return max([f.stat().st_mtime for f in up.iterdir()], default=0.0) if up.exists() else 0.0


def get_index(owner: str, chunking: str) -> tuple[Index, dict]:
    """Cached per owner; a new upload changes the version so only new chunks are embedded (incremental)."""
    key = (owner, chunking, _uploads_version(owner))
    if key not in _index_cache:
        items = load_item_texts(owner)
        _index_cache[key] = (Index(chunk_items(items, chunking)), {it["id"]: it for it in items})
    return _index_cache[key]


def invalidate(owner: str) -> None:
    for k in [k for k in _index_cache if k[0] == owner]:
        del _index_cache[k]


def _project_win_rates(items: dict) -> dict[str, float]:
    stats = defaultdict(lambda: [0, 0])
    for it in items.values():
        if it["type"] == "proposal":
            s = stats[it["project"]]
            s[0] += {"won": 1.0, "replied": 0.6}.get(it.get("outcome"), 0.0)
            s[1] += 1
    return {p: a / n for p, (a, n) in stats.items() if n}


def query_text(job: dict) -> str:
    return f"{job.get('title', '')}\n{job.get('description', '')}"


def requirements_of(job: dict) -> list[str]:
    reqs = list(job.get("requirements") or job.get("skills") or [])
    return reqs or [query_text(job)]


class Pipeline:
    def __init__(self, cfg: RAGConfig):
        self.cfg = cfg

    def _one(self, idx: Index, q: str, n: int) -> list[tuple[int, float]]:
        d = idx.dense(q, n)
        return rrf(d, idx.sparse(q, n)) if self.cfg.hybrid else d

    def search(self, owner: str, job: dict | None = None, query: str | None = None, k: int = 10,
               filters: dict | None = None) -> list[dict]:
        cfg = self.cfg
        idx, items = get_index(owner, cfg.chunking)
        n = cfg.candidates
        if query is not None:
            queries = [query]
            full = query
        elif cfg.decompose:
            queries = [f"{r} — {job.get('title', '')}" for r in requirements_of(job)]
            full = query_text(job)
        else:
            queries = [query_text(job)]
            full = queries[0]
        ranked = rrf(*[self._one(idx, q, n) for q in queries]) if len(queries) > 1 else self._one(idx, queries[0], n)
        ranked = ranked[: n * 2]
        types = set((filters or {}).get("types") or cfg.types)
        ranked = [(i, s) for i, s in ranked if idx.chunks[i].type in types]
        if cfg.rerank and ranked:
            cand = ranked[:n]
            texts = [f"{idx.chunks[i].title}. {idx.chunks[i].text}" for i, _ in cand]
            scores = list(reranker().rerank(full[:1000], texts))
            ranked = sorted(zip([i for i, _ in cand], scores), key=lambda x: -x[1]) + ranked[n:]
            # normalise to rank-based score so the outcome boost is scale-free
            ranked = [(i, 1.0 / (r + 1)) for r, (i, _) in enumerate(ranked)]
        # aggregate chunk -> item (multi-vector items return as one project item)
        best: dict[str, tuple[float, int]] = {}
        for i, s in ranked:
            iid = idx.chunks[i].item_id
            if iid not in best or s > best[iid][0]:
                best[iid] = (s, i)
        if cfg.outcome_boost:
            wr = _project_win_rates(items)
            mean = sum(wr.values()) / max(1, len(wr))
            for iid, (s, i) in list(best.items()):
                it = items[iid]
                adj = wr.get(it.get("project"), mean) - mean
                if it["type"] == "proposal":
                    adj += {"won": 0.3, "replied": 0.15, "ignored": -0.3}.get(it.get("outcome"), 0)
                best[iid] = (s * (1 + cfg.outcome_boost * adj), i)
        since = (filters or {}).get("since")
        out = []
        for iid, (s, i) in sorted(best.items(), key=lambda x: -x[1][0]):
            it = items[iid]
            if since and it.get("date") and it["date"] < since:
                continue
            out.append({"id": iid, "type": it["type"], "title": it.get("title"), "project": it.get("project"),
                        "source": it.get("path") or "upload", "date": it.get("date"), "outcome": it.get("outcome"),
                        "skills": it.get("skills"), "snippet": idx.chunks[i].text[:500], "score": round(float(s), 4)})
            if len(out) >= k:
                break
        if cfg.corrective and job is not None:
            from rag.variants.corrective import corrective_filter
            out = corrective_filter(self, owner, job, out, k)
        return out


def load_variant(name: str) -> Pipeline:
    import importlib
    mod = importlib.import_module(f"rag.variants.{name}")
    return Pipeline(mod.CONFIG)


def dumps(results: list[dict]) -> str:
    return json.dumps(results, indent=1)
