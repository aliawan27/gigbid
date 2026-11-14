"""Indexes: dense (fastembed BGE-small, numpy flat inner-product store cached on disk) and BM25.
Open models only, CPU friendly. Incremental: new chunks are embedded and appended, old ones reused."""
from __future__ import annotations

import hashlib
import os
import re
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from rag.ingest.loaders import Chunk

CACHE = Path(os.getenv("GIGBID_CACHE", Path(__file__).resolve().parents[2] / "data" / "processed"))
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
RERANK_MODEL = os.getenv("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
_lock = threading.Lock()


def _lean_onnx() -> None:
    """Disable onnxruntime's CPU memory arena: otherwise one large embedding batch keeps GBs reserved."""
    import onnxruntime as ort
    if getattr(ort.InferenceSession, "_gigbid_patched", False):
        return
    orig = ort.InferenceSession.__init__

    def init(self, path, sess_options=None, *a, **k):
        so = sess_options or ort.SessionOptions()
        so.enable_cpu_mem_arena = False
        orig(self, path, so, *a, **k)
    ort.InferenceSession.__init__ = init
    ort.InferenceSession._gigbid_patched = True


@lru_cache(1)
def embedder():
    _lean_onnx()
    from fastembed import TextEmbedding
    return TextEmbedding(EMBED_MODEL, cache_dir=str(CACHE / "models"))


@lru_cache(1)
def reranker():
    _lean_onnx()
    from fastembed.rerank.cross_encoder import TextCrossEncoder
    return TextCrossEncoder(RERANK_MODEL, cache_dir=str(CACHE / "models"))


def embed(texts: list[str]) -> np.ndarray:
    with _lock:
        v = np.array(list(embedder().embed(texts, batch_size=16)), dtype=np.float32)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


_emb_cache: dict[str, np.ndarray] = {}


def _cache_path():
    CACHE.mkdir(parents=True, exist_ok=True)
    return CACHE / f"emb_{EMBED_MODEL.replace('/', '_')}.npz"


def _load_cache():
    if not _emb_cache and _cache_path().exists():
        d = np.load(_cache_path())
        _emb_cache.update({k: d[k] for k in d.files})


def embed_cached(texts: list[str]) -> np.ndarray:
    """Content-hash cache so re-indexing only embeds new/changed chunks (incremental re-indexing)."""
    _load_cache()
    keys = [hashlib.sha1(t.encode()).hexdigest() for t in texts]
    missing = [i for i, k in enumerate(keys) if k not in _emb_cache]
    if missing:
        vecs = embed([texts[i] for i in missing])
        for i, v in zip(missing, vecs):
            _emb_cache[keys[i]] = v
        try:
            np.savez(_cache_path(), **_emb_cache)
        except OSError:
            pass
    return np.stack([_emb_cache[k] for k in keys]) if keys else np.zeros((0, 384), np.float32)


TOKEN = re.compile(r"[a-z0-9.+#/-]+")


def tokenize(t: str) -> list[str]:
    return TOKEN.findall(t.lower())


class Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        texts = [(c.context + " " if c.context else "") + c.text for c in chunks]
        self.vecs = embed_cached(texts)
        self.bm25 = BM25Okapi([tokenize(t) for t in texts]) if texts else None

    def dense(self, query: str, k: int = 20, qvec: np.ndarray | None = None) -> list[tuple[int, float]]:
        q = qvec if qvec is not None else embed([query])[0]
        s = self.vecs @ q
        top = np.argsort(-s)[:k]
        return [(int(i), float(s[i])) for i in top]

    def sparse(self, query: str, k: int = 20) -> list[tuple[int, float]]:
        s = self.bm25.get_scores(tokenize(query))
        top = np.argsort(-s)[:k]
        return [(int(i), float(s[i])) for i in top if s[i] > 0]


def rrf(*rankings: list[tuple[int, float]], k: int = 60) -> list[tuple[int, float]]:
    agg: dict[int, float] = {}
    for r in rankings:
        for rank, (i, _) in enumerate(r):
            agg[i] = agg.get(i, 0) + 1 / (k + rank + 1)
    return sorted(agg.items(), key=lambda x: -x[1])
