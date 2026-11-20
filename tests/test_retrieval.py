from app import knowledge, retrieval
from eval import run_retrieval


def test_documents():
    docs = knowledge.build_documents()
    assert len(docs) == 306 and len({d.id for d in docs}) == 306
    assert all(d.metadata["kind"] in knowledge.KINDS for d in docs)


def test_hybrid_quality_floor():
    report = run_retrieval.evaluate()
    # Measured 0.90 / 1.00 when written; fail loudly if a change makes retrieval worse.
    assert report["hybrid"]["hit@1"] >= 0.85 and report["hybrid"]["hit@3"] >= 0.95
    assert report["hybrid"]["hit@3"] >= report["dense"]["hit@3"]


def test_scope_filter_and_arabic():
    r = retrieval.get_retriever()
    hits = r.search("contact", k=3, kinds={"contacts"})
    assert hits and all(h.doc.metadata["kind"] == "contacts" for h in hits)
    ar = r.search("فلل حي المنار الدمام", k=3)
    assert any("المنار" in h.doc.page_content for h in ar)


def test_index_roundtrip(tmp_path, monkeypatch):
    docs = knowledge.build_documents()[:5]
    store = retrieval.build_store(docs)
    store.dump(str(tmp_path / "v.json"))
    loaded = retrieval.InMemoryVectorStore.load(str(tmp_path / "v.json"), retrieval.WordLlamaEmbeddings())
    assert loaded.similarity_search(docs[0].page_content, k=1)[0].id == docs[0].id
    assert retrieval.fingerprint(docs) != retrieval.fingerprint(docs[:4])
