"""LangChain tools for the agent. Arguments are validated by Pydantic before any code runs;
bad arguments come back to the model as an error message instead of crashing the request."""
from __future__ import annotations

import json
from typing import Literal

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from . import retrieval, tools, websearch

MAX_TOOL_CHARS = 12000

Str60 = Field(default=None, max_length=60)


def _json(x) -> str:
    s = json.dumps(x, ensure_ascii=False, default=str)
    return s if len(s) <= MAX_TOOL_CHARS else s[:MAX_TOOL_CHARS] + ' …"(truncated)"'


class ProjectSearch(BaseModel):
    query: str | None = Field(None, max_length=200, description="Words to match, e.g. 'golf villas', 'beach', 'penthouse'")
    country: str | None = Field(None, max_length=60, description="Country or city: 'Oman', 'UAE', 'Dubai', 'Saudi Arabia'")
    status: str | None = Field(None, max_length=40, description="'under development', 'completed' or 'sold out'")
    brand: str | None = Field(None, max_length=60, description="Brand partner: 'Trump', 'Missoni', 'Aston Martin'")
    min_bedrooms: int | None = Field(None, ge=0, le=20, description="Projects offering at least this many bedrooms")
    completion_by_year: int | None = Field(None, ge=2020, le=2045, description="Completion in or before this year")
    limit: int = Field(10, ge=1, le=15)


class ProjectName(BaseModel):
    name: str = Field(max_length=120, description="Project name, e.g. 'Neptune' or 'The Astera'")


class Company(BaseModel):
    company: Literal["darglobal", "wasalt", "both"] = "both"


class VillaSearch(BaseModel):
    city: str | None = Field(None, max_length=40, description="Riyadh, Jeddah, Khobar, Dammam, Mecca, Medina, Khamis Mushait, Buraidah or Jazan")
    district: str | None = Field(None, max_length=60, description="District name (English or Arabic) or sector such as 'North Riyadh'")
    min_price: float | None = Field(None, ge=0, le=1e9, description="SAR")
    max_price: float | None = Field(None, ge=0, le=1e9, description="SAR")
    min_area: float | None = Field(None, ge=0, le=1e5, description="sqm")
    max_area: float | None = Field(None, ge=0, le=1e5, description="sqm")
    min_bedrooms: int | None = Field(None, ge=0, le=30)
    facing: str | None = Field(None, max_length=20, description="North, South, East or West")
    sort_by: Literal["price_asc", "price_desc", "area_asc", "area_desc", "sar_per_sqm_asc", "sar_per_sqm_desc"] = "price_asc"
    limit: int = Field(8, ge=1, le=15)


class ListingId(BaseModel):
    listing_id: str = Field(max_length=20, description="Wasalt listing number, e.g. '5971799'")


class CityStats(BaseModel):
    city: str | None = Field(None, max_length=40, description="One city, or omit to compare all nine cities")


class KnowledgeSearch(BaseModel):
    query: str = Field(min_length=2, max_length=300, description="What to look for, ideally in English")
    scope: Literal["any", "darglobal", "wasalt", "contacts", "company"] = "any"
    k: int = Field(6, ge=1, le=8)


class WebSearch(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    site: str | None = Field(None, max_length=60, pattern=r"^[a-z0-9.-]+\.[a-z]{2,}$",
                             description="Optional domain to search within, e.g. 'darglobal.co.uk'")


SCOPES = {
    "darglobal": {"darglobal_project", "darglobal_company", "darglobal_press"},
    "wasalt": {"wasalt_villa", "wasalt_city", "wasalt_project"},
    "contacts": {"contacts"},
    "company": {"darglobal_company", "darglobal_press", "contacts"},
}


def search_knowledge(query: str, scope: str = "any", k: int = 6) -> str:
    hits = retrieval.get_retriever().search(query, k=k, kinds=SCOPES.get(scope))
    return _json({"results": [{
        "id": h.doc.id, "kind": h.doc.metadata.get("kind"), "title": h.doc.metadata.get("title"),
        "url": h.doc.metadata.get("url"), "text": h.doc.page_content[:700],
        "matched_by": "+".join(x for x, r in (("meaning", h.dense_rank), ("keywords", h.bm25_rank)) if r)}
        for h in hits]})


def _plain(fn):
    def run(**kw):
        return _json(fn(**kw))
    run.__name__ = fn.__name__
    return run


def _tool(fn, name: str, schema: type[BaseModel], description: str, coroutine=None) -> BaseTool:
    t = StructuredTool.from_function(func=fn, coroutine=coroutine, name=name, description=description, args_schema=schema)
    t.handle_tool_error = lambda e: f"Tool error: {str(e)[:300]}"
    t.handle_validation_error = lambda e: f"Invalid arguments, fix them and retry: {str(e)[:400]}"
    return t


class _NoArgs(BaseModel):
    pass


def make_tools(web: bool, http_client=None) -> list[BaseTool]:
    async def _web(query: str, site: str | None = None) -> str:
        return _json(await websearch.search(query, site, client=http_client))

    ts = [
        _tool(_plain(tools.search_darglobal_projects), "search_darglobal_projects", ProjectSearch,
              "Filter DarGlobal's 38 projects (UAE, Oman, Qatar, Saudi Arabia, Spain, UK) by country, status, brand, "
              "bedrooms or completion year. Use for lists and filters."),
        _tool(_plain(tools.get_darglobal_project), "get_darglobal_project", ProjectName,
              "Full details of one DarGlobal project by name."),
        _tool(_plain(tools.darglobal_overview), "darglobal_overview", _NoArgs,
              "Counts of DarGlobal projects by country and status, and the brand partners."),
        _tool(_plain(tools.darglobal_company_info), "darglobal_company_info", _NoArgs,
              "DarGlobal company profile: what it does, London Stock Exchange listing, brand partners, recent press links."),
        _tool(_plain(lambda company="both": tools.get_contact_info(None if company == "both" else company)),
              "get_contact_info", Company,
              "Official contacts for DarGlobal (WhatsApp, phone, register-interest form) and Wasalt (customer service), "
              "and how to reach the advertiser of a Wasalt listing."),
        _tool(_plain(tools.search_wasalt_villas), "search_wasalt_villas", VillaSearch,
              "Filter and sort the sampled villa-for-sale listings from Wasalt.sa by city, district, price (SAR), area, "
              "bedrooms or facing. Use for any question about specific villas, prices or cheapest/largest."),
        _tool(_plain(tools.get_wasalt_listing), "get_wasalt_listing", ListingId, "One Wasalt listing by its number."),
        _tool(_plain(tools.wasalt_market_stats), "wasalt_market_stats", CityStats,
              "Villa market snapshot from Wasalt: result counts and medians for all nine cities, or one city in detail."),
        _tool(_plain(tools.list_wasalt_projects), "list_wasalt_projects", _NoArgs,
              "New-build projects Wasalt shows on its Riyadh villas page, with 'from' prices."),
        _tool(search_knowledge, "search_knowledge", KnowledgeSearch,
              "Semantic + keyword search over all the data (projects, listings, company, press, contacts). Use for "
              "open or descriptive questions, e.g. 'homes by the sea', 'family resort', 'who is DarGlobal'. "
              "Write the query in English."),
        _tool(_plain(tools.dataset_info), "dataset_info", _NoArgs,
              "How and when the data was collected, and its limits."),
    ]
    if web:
        ts.append(_tool(None, "web_search", WebSearch,
                        "Search the internet. Use ONLY when the other tools cannot answer (news, company results, "
                        "prices or payment plans not in the data, places or developers not covered).", coroutine=_web))
    return ts
