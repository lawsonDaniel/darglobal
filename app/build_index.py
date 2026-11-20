"""Build the vector index: python -m app.build_index  (run at Docker build time)."""
from __future__ import annotations

import json

from . import knowledge, retrieval


def main() -> None:
    docs = knowledge.build_documents()
    store = retrieval.build_store(docs)
    manifest = retrieval.save_index(docs, store)
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
