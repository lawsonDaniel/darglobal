"""Rule-based context for the fallback mode, used when no available model can call tools.

It runs the same deterministic functions the tools use, picked by keywords in the question,
plus hybrid retrieval, so even a model without tool calling answers from the data.
"""
from __future__ import annotations

import re

from . import retrieval, tools

CITY_RE = re.compile("|".join(sorted((re.escape(k) for k in tools.CITY_ALIASES), key=len, reverse=True)), re.I)
CONTACT_WORDS = ("contact", "phone", "whatsapp", "call", "email", "reach", "تواصل", "اتصال", "رقم", "واتساب")
COMPANY_WORDS = ("company", "listed", "stock", "press", "partner", "about darglobal", "who is darglobal", "news")
WASALT_WORDS = ("villa", "wasalt", "sar", "riyal", "price", "cheap", "listing", "فيلا", "فلل", "سعر", "وصلت")
DG_WORDS = ("darglobal", "dar global", "project", "trump", "branded", "oman", "dubai", "qatar", "spain", "london",
            "completion", "penthouse")
WEB_WORDS = ("news", "latest", "today", "ceo", "chairman", "share price", "revenue", "profit", "payment plan",
             "starting price", "launch", "أخبار", "سعر السهم")


def context_for(question: str) -> list[dict]:
    q = tools.norm(question)
    picks: list[tuple[str, dict]] = []
    city = CITY_RE.search(q)
    if city or any(w in q for w in WASALT_WORDS):
        c = city.group(0) if city else None
        args: dict = {"city": c, "limit": 8}
        mil = re.search(r"(\d+(?:\.\d+)?)\s*(m|million|mn|مليون)\b", question.lower())
        nums = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", question)]
        if mil:
            args["max_price"] = float(mil.group(1)) * 1_000_000
        elif nums and max(nums) > 10000:
            args["max_price"] = max(nums)
        picks += [("search_wasalt_villas", args), ("wasalt_market_stats", {"city": c})]
    if any(w in q for w in CONTACT_WORDS):
        picks.append(("get_contact_info", {}))
    if any(w in q for w in COMPANY_WORDS):
        picks.append(("darglobal_company_info", {}))
    if any(w in q for w in DG_WORDS):
        picks.append(("search_darglobal_projects", {"query": question}))
    fns = {"search_wasalt_villas": tools.search_wasalt_villas, "wasalt_market_stats": tools.wasalt_market_stats,
           "get_contact_info": tools.get_contact_info, "darglobal_company_info": tools.darglobal_company_info,
           "search_darglobal_projects": tools.search_darglobal_projects}
    out = [{"tool": n, "args": a, "result": fns[n](**a)} for n, a in picks]
    hits = retrieval.get_retriever().search(question, k=6)
    out.append({"tool": "search_knowledge", "args": {"query": question},
                "result": [{"id": h.doc.id, "title": h.doc.metadata.get("title"), "url": h.doc.metadata.get("url"),
                            "text": h.doc.page_content[:600]} for h in hits]})
    return out


def needs_web(question: str, ctx: list[dict]) -> bool:
    if any(w in question.lower() for w in WEB_WORDS):
        return True
    structured = [c for c in ctx if c["tool"] != "search_knowledge"]
    if not structured:
        return True
    for c in structured:
        r = c["result"]
        if r.get("matches_in_sample") or r.get("count") or c["tool"] in ("get_contact_info", "darglobal_company_info"):
            return False
    return True
