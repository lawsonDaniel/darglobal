"""Hybrid retrieval: dense vectors (LangChain InMemoryVectorStore) + BM25 keywords, fused by RRF.

Dense search catches meaning ("homes by the sea" -> "beachfront villas"); BM25 catches exact names,
numbers and Arabic district names that a small embedding model handles poorly. Reciprocal Rank
Fusion combines the two rankings without needing comparable scores.

The vector index is built at Docker build time (python -m app.build_index) and loaded at startup.
A manifest stores a hash of the data and the embedding id, so a stale index is rebuilt in memory.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from rank_bm25 import BM25Okapi

from . import knowledge, tools
from .config import settings
from .embeddings import EMBEDDING_ID, WordLlamaEmbeddings

log = logging.getLogger("retrieval")
RRF_K = 60
ARABIC = re.compile(r"[\u0600-\u06ff]")
STOP = set("a an the of in on at for to and or with by from is are was be this that what which who how does do "
           "me my i you your it its as there their about any some all show list find give tell".split())


def bm25_tokens(text: str) -> list[str]:
    out = []
    for w in tools.norm(text).split():
        if w in STOP or len(w) < 2:
            continue
        if re.fullmatch(r"[a-z]+", w) and len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]  # crude plural folding: villas -> villa
        out.append(w)
    return out


def fingerprint(docs: list[Document]) -> str:
    """Hash of every document's id and text: any change to the data or to how documents are written."""
    h = hashlib.sha256()
    for d in docs:
        h.update(f"{d.id}\x00{d.page_content}\x00".encode())
    return h.hexdigest()[:16]


@dataclass
class Hit:
    doc: Document
    score: float
    dense_rank: int | None
    bm25_rank: int | None


class HybridRetriever:
    def __init__(self, docs: list[Document], store: InMemoryVectorStore, source: str):
        self.docs = docs
        self.by_id = {d.id: d for d in docs}
        self.store = store
        self.source = source
        self.bm25 = BM25Okapi([bm25_tokens(d.page_content + " " + d.metadata.get("title", "")) for d in docs])

    def dense(self, query: str, n: int, kinds: set[str] | None) -> list[tuple[Document, float]]:
        flt = (lambda d: d.metadata.get("kind") in kinds) if kinds else None
        return self.store.similarity_search_with_score(query, k=n, filter=flt)

    def keyword(self, query: str, n: int, kinds: set[str] | None) -> list[tuple[Document, float]]:
        scores = self.bm25.get_scores(bm25_tokens(query))
        ranked = sorted(range(len(self.docs)), key=lambda i: -scores[i])
        out = []
        for i in ranked:
            if scores[i] <= 0:
                break
            if kinds and self.docs[i].metadata.get("kind") not in kinds:
                continue
            out.append((self.docs[i], float(scores[i])))
            if len(out) >= n:
                break
        return out

    def search(self, query: str, k: int = 6, kinds: set[str] | None = None, mode: str = "hybrid") -> list[Hit]:
        n = max(k * 4, 20)
        # The embedding model is English-centric: lean on keywords for Arabic queries.
        w_dense = 0.0 if ARABIC.search(query) else 1.0
        dense = self.dense(query, n, kinds) if mode in ("hybrid", "dense") else []
        kw = self.keyword(query, n, kinds) if mode in ("hybrid", "bm25") else []
        fused: dict[str, Hit] = {}
        for rank, (d, _) in enumerate(dense):
            h = fused.setdefault(d.id, Hit(self.by_id.get(d.id, d), 0.0, None, None))
            h.score += w_dense / (RRF_K + rank + 1)
            h.dense_rank = rank + 1
        for rank, (d, _) in enumerate(kw):
            h = fused.setdefault(d.id, Hit(d, 0.0, None, None))
            h.score += 1 / (RRF_K + rank + 1)
            h.bm25_rank = rank + 1
        return sorted(fused.values(), key=lambda h: -h.score)[:k]


def build_store(docs: list[Document]) -> InMemoryVectorStore:
    store = InMemoryVectorStore(WordLlamaEmbeddings())
    store.add_documents(docs, ids=[d.id for d in docs])
    return store


def save_index(retriever_docs: list[Document], store: InMemoryVectorStore) -> dict:
    settings.index_dir.mkdir(parents=True, exist_ok=True)
    store.dump(str(settings.index_dir / "vectors.json"))
    manifest = {"embedding": EMBEDDING_ID, "fingerprint": fingerprint(retriever_docs), "documents": len(retriever_docs),
                "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (settings.index_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


_retriever: HybridRetriever | None = None


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is not None:
        return _retriever
    docs = knowledge.build_documents()
    manifest_path, vec_path = settings.index_dir / "manifest.json", settings.index_dir / "vectors.json"
    store, source = None, "built at startup"
    try:
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("embedding") == EMBEDDING_ID and manifest.get("fingerprint") == fingerprint(docs):
            store = InMemoryVectorStore.load(str(vec_path), WordLlamaEmbeddings())
            source = f"prebuilt index ({manifest.get('built_at')})"
        else:
            log.warning("vector index is stale; rebuilding in memory")
    except FileNotFoundError:
        log.info("no prebuilt vector index; building in memory")
    except (ValueError, KeyError, OSError) as e:
        log.warning("could not load vector index (%s); rebuilding in memory", e)
    if store is None:
        store = build_store(docs)
    _retriever = HybridRetriever(docs, store, source)
    return _retriever


def index_info() -> dict:
    r = get_retriever()
    return {"documents": len(r.docs), "embedding": EMBEDDING_ID, "source": r.source}
