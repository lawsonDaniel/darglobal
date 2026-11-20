"""Offline retrieval evaluation: python -m eval.run_retrieval

Scores hit@1, hit@3 and hit@5 for dense-only, BM25-only and hybrid search over eval/retrieval_cases.jsonl.
A case passes when any expected document id (or any document containing the expected text) is retrieved.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from app import retrieval

CASES = Path(__file__).with_name("retrieval_cases.jsonl")


def hit(case: dict, ids: list[str], docs: list) -> bool:
    if "any" in case:
        return any(i in case["any"] for i in ids)
    return any(case["text"] in d.page_content for d in docs)


def evaluate(verbose: bool = False) -> dict:
    r = retrieval.get_retriever()
    cases = [json.loads(line) for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = {}
    for mode in ("dense", "bm25", "hybrid"):
        scores = {1: 0, 3: 0, 5: 0}
        misses = []
        for c in cases:
            hits = r.search(c["q"], k=5, mode=mode)
            for k in scores:
                top = hits[:k]
                if hit(c, [h.doc.id for h in top], [h.doc for h in top]):
                    scores[k] += 1
            if not hit(c, [h.doc.id for h in hits[:3]], [h.doc for h in hits[:3]]):
                misses.append(c["q"])
        report[mode] = {f"hit@{k}": round(v / len(cases), 3) for k, v in scores.items()}
        if verbose:
            report[mode]["missed@3"] = misses
    report["cases"] = len(cases)
    return report


if __name__ == "__main__":
    print(json.dumps(evaluate(verbose="-v" in sys.argv), ensure_ascii=False, indent=1))
