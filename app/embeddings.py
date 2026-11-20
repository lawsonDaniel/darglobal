"""Local text embeddings for LangChain, with no network calls and no GPU.

WordLlama (l2_supercat, 256 dimensions) ships its 16 MB weights inside the pip package, so the
index builds offline at Docker build time and the app fits a 512 MB free-tier host.
"""
from __future__ import annotations

import threading
from pathlib import Path

from langchain_core.embeddings import Embeddings

EMBEDDING_ID = "wordllama-l2_supercat-256"


class WordLlamaEmbeddings(Embeddings):
    _lock = threading.Lock()
    _model = None

    @classmethod
    def _get(cls):
        if cls._model is None:
            with cls._lock:
                if cls._model is None:
                    import wordllama
                    from wordllama import WordLlama
                    # The package bundles weights and tokenizer; point the "cache" at the package so
                    # nothing is downloaded (WordLlama otherwise looks for the tokenizer online).
                    cls._model = WordLlama.load(cache_dir=Path(wordllama.__file__).parent, disable_download=True)
        return cls._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._get().embed(list(texts), norm=True).astype(float).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
