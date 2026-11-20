"""Deterministic data functions over the bundled snapshot. The agent's tools call these.

Numbers (prices, counts, medians) are always computed here in Python, never by the model.
The snapshot (collected 18-19 Nov 2026) holds:
- DarGlobal: 38 projects from darglobal.co.uk, a company profile and official contacts.
- Wasalt: the first results page of villas for sale in nine Saudi cities (245 listings), the result
  count Wasalt shows per city, 4 Riyadh projects and Wasalt's customer-service contact.
"""
from __future__ import annotations

import json
import re
import statistics
from functools import lru_cache
from typing import Any

from .config import settings

MAX_ROWS = 15
SQFT_PER_SQM = 10.7639


# --------------------------------------------------------------------------- text normalisation
_AR_DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")


def norm(s: Any) -> str:
    """Lower-case, strip punctuation, and fold Arabic letter variants so matching is forgiving."""
    s = _AR_DIACRITICS.sub("", str(s or "")).lower()
    s = s.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ـ": ""}))
    return " ".join(re.sub(r"[^\w\s]", " ", s).split())


def words(s: Any) -> list[str]:
    return [w for w in norm(s).split() if len(w) > 1]


def _nums(s: str) -> list[float]:
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", s)]


# --------------------------------------------------------------------------- loading + enrichment
@lru_cache(maxsize=None)
def load(name: str) -> Any:
    data = json.loads((settings.data_dir / f"{name}.json").read_text(encoding="utf-8"))
    if name == "darglobal_projects":
        for p in data:
            enrich_project(p)
    return data


def parse_bedrooms(s: str | None) -> tuple[int | None, int | None]:
    if not s:
        return None, None
    found = [int(x) for x in re.findall(r"\d+", s)]
    if re.search(r"studio", s, re.I):
        found.append(0)
    return (min(found), max(found)) if found else (None, None)


def parse_sizes(s: str | None) -> tuple[float | None, float | None, str | None]:
    """Return (min_sqm, max_sqm, how) from DarGlobal's free-text unit sizes."""
    if not s:
        return None, None, None
    segs = [x.strip() for x in s.split(";")]
    built = [x for x in segs if "built-up" in x.lower()]
    segs = built or segs
    for seg in segs:
        if "sqm" in seg.lower():
            vals = _nums(seg.split("(")[0])
            if vals:
                return min(vals), max(vals), "sqm as shown"
    for seg in segs:
        if "sqft" in seg.lower():
            vals = _nums(seg)
            if vals:
                return round(min(vals) / SQFT_PER_SQM), round(max(vals) / SQFT_PER_SQM), "converted from sqft"
    return None, None, "unit not shown on the page"


def enrich_project(p: dict) -> None:
    p["bedrooms_min"], p["bedrooms_max"] = parse_bedrooms(p.get("bedrooms"))
    p["size_sqm_min"], p["size_sqm_max"], p["size_basis"] = parse_sizes(p.get("unit_sizes"))
    m = re.search(r"(20\d\d)", p.get("completion") or "")
    p["completion_year"] = int(m.group(1)) if m else None
    st = (p.get("status") or "").lower()
    p["is_completed"] = "completed" in st
    p["is_sold_out"] = "sold out" in st


CITY_ALIASES = {
    "riyadh": "Riyadh", "الرياض": "Riyadh", "رياض": "Riyadh",
    "jeddah": "Jeddah", "jidda": "Jeddah", "jedda": "Jeddah", "جده": "Jeddah",
    "khobar": "Khobar", "al khobar": "Khobar", "alkhobar": "Khobar", "الخبر": "Khobar",
    "dammam": "Dammam", "الدمام": "Dammam",
    "mecca": "Mecca", "makkah": "Mecca", "makka": "Mecca", "مكه": "Mecca", "مكه المكرمه": "Mecca",
    "medina": "Medina", "madinah": "Medina", "madina": "Medina", "المدينه": "Medina", "المدينه المنوره": "Medina",
    "khamis mushait": "Khamis Mushait", "khamis": "Khamis Mushait", "خميس مشيط": "Khamis Mushait",
    "buraidah": "Buraidah", "buraydah": "Buraidah", "buraida": "Buraidah", "بريده": "Buraidah",
    "jazan": "Jazan", "jizan": "Jazan", "gizan": "Jazan", "جازان": "Jazan",
}
COUNTRY_ALIASES = {"uae": "united arab emirates", "emirates": "united arab emirates", "ksa": "saudi arabia",
                   "saudi": "saudi arabia", "uk": "united kingdom", "england": "united kingdom",
                   "britain": "united kingdom", "ras al khaimah": "rak"}


def canon_city(city: str | None) -> str | None:
    if not city:
        return None
    key = norm(city)
    return CITY_ALIASES.get(key) or str(city).strip().title()


def covered_cities() -> list[str]:
    return [s["city"] for s in load("wasalt_city_summary")]


# --------------------------------------------------------------------------- DarGlobal
def _dg_brief(p: dict) -> dict:
    keep = ("name", "country", "location", "property_types", "completion", "bedrooms", "unit_sizes", "status",
            "brand", "url")
    return {k: p[k] for k in keep if p.get(k) is not None}


def search_darglobal_projects(query: str | None = None, country: str | None = None, status: str | None = None,
                              brand: str | None = None, min_bedrooms: int | None = None,
                              completion_by_year: int | None = None, limit: int = MAX_ROWS) -> dict:
    out = []
    for p in load("darglobal_projects"):
        if country:
            want = COUNTRY_ALIASES.get(norm(country), norm(country))
            if want not in norm(p["country"]) + " " + norm(p["location"]):
                continue
        if status:
            s = norm(status)
            if "sold" in s:
                if not p["is_sold_out"]:
                    continue
            elif "complet" in s or "ready" in s:
                if not p["is_completed"]:
                    continue
            elif s not in norm(p["status"]):
                continue
        if brand and norm(brand) not in norm(p["brand"]) + " " + norm(p["name"]):
            continue
        if min_bedrooms is not None and (p["bedrooms_max"] is None or p["bedrooms_max"] < min_bedrooms):
            continue
        if completion_by_year is not None and (p["completion_year"] is None or p["completion_year"] > completion_by_year):
            continue
        score = 0
        if query:
            hay = " ".join(norm(p.get(k)) for k in ("name", "location", "property_types", "notes", "brand", "country"))
            hay_words = set(hay.split())
            score = sum(1 for w in words(query) if w in hay_words or (len(w) > 3 and w in hay))
            if score == 0:
                continue
        out.append((score, p))
    out.sort(key=lambda t: -t[0])
    limit = max(1, min(int(limit), MAX_ROWS))
    return {"count": len(out), "projects": [_dg_brief(p) for _, p in out[:limit]],
            "note": "DarGlobal's pages show no prices or payment plans."}


def get_darglobal_project(name: str) -> dict:
    rows = load("darglobal_projects")
    want = set(words(name))
    scored = []
    for p in rows:
        have = set(words(p["name"]) + words(p["url"].rsplit("/", 1)[-1].replace("-", " ")))
        score = len(want & have) + (100 if norm(name) == norm(p["name"]) else 0)
        if score:
            scored.append((score, p))
    if not scored:
        return {"error": f"No DarGlobal project matches '{name}'.", "project_names": [p["name"] for p in rows]}
    scored.sort(key=lambda t: -t[0])
    best = scored[0][1]
    hidden = {"bedrooms_min", "bedrooms_max", "size_sqm_min", "size_sqm_max", "is_completed", "is_sold_out"}
    res = {"project": {k: v for k, v in best.items() if v is not None and k not in hidden}}
    ties = [p["name"] for s, p in scored[1:6] if s == scored[0][0]]
    if ties:
        res["other_matches"] = ties
    return res


def darglobal_overview() -> dict:
    rows = load("darglobal_projects")
    by_country: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for p in rows:
        by_country[p["country"]] = by_country.get(p["country"], 0) + 1
        s = p["status"] or "not shown"
        by_status[s] = by_status.get(s, 0) + 1
    return {"total_projects": len(rows), "by_country": by_country, "by_status": by_status,
            "branded_partners": sorted({p["brand"] for p in rows if p["brand"]})}


def darglobal_company_info() -> dict:
    return load("darglobal_company")


def get_contact_info(company: str | None = None) -> dict:
    c = load("contacts")
    key = norm(company)
    if "dar" in key:
        return {"darglobal": c["darglobal"], "checked": c["checked"]}
    if "wasalt" in key or "وصلت" in key:
        return {"wasalt": c["wasalt"], "checked": c["checked"]}
    return c


# --------------------------------------------------------------------------- Wasalt
SORTS = {"price_asc": ("price_sar", False), "price_desc": ("price_sar", True), "area_desc": ("area_sqm", True),
         "area_asc": ("area_sqm", False), "sar_per_sqm_asc": ("sar_per_sqm", False),
         "sar_per_sqm_desc": ("sar_per_sqm", True)}
WASALT_NOTE = "Sample of the first results page per city, collected 18-19 Nov 2026. Check the live listing."


def _villa_brief(v: dict) -> dict:
    keep = ("id", "city", "price_sar", "area_sqm", "sar_per_sqm", "bedrooms", "bathrooms", "district_en",
            "district_ar", "facing", "street_width_m", "note", "url")
    return {k: v[k] for k in keep if v.get(k) is not None}


def search_wasalt_villas(city: str | None = None, district: str | None = None, min_price: float | None = None,
                         max_price: float | None = None, min_area: float | None = None, max_area: float | None = None,
                         min_bedrooms: int | None = None, facing: str | None = None, sort_by: str = "price_asc",
                         limit: int = 8) -> dict:
    c = canon_city(city)
    out = []
    for v in load("wasalt_villas"):
        if c and v["city"] != c:
            continue
        if district:
            d = norm(district)
            hay = " ".join(norm(v.get(k)) for k in ("district_ar", "district_en", "sector_en", "sector_ar"))
            if d not in hay:
                continue
        if min_price is not None and v["price_sar"] < min_price:
            continue
        if max_price is not None and v["price_sar"] > max_price:
            continue
        if min_area is not None and (v["area_sqm"] or 0) < min_area:
            continue
        if max_area is not None and (v["area_sqm"] or 0) > max_area:
            continue
        if min_bedrooms is not None and (v["bedrooms"] or 0) < min_bedrooms:
            continue
        if facing and norm(facing) not in norm(v.get("facing")):
            continue
        out.append(v)
    key, rev = SORTS.get(sort_by, SORTS["price_asc"])
    present = sorted((v for v in out if v.get(key) is not None), key=lambda v: v[key], reverse=rev)
    out = present + [v for v in out if v.get(key) is None]
    limit = max(1, min(int(limit), MAX_ROWS))
    res = {"matches_in_sample": len(out), "listings": [_villa_brief(v) for v in out[:limit]],
           "source": "Source: Wasalt.sa", "caveat": WASALT_NOTE}
    if c and c not in covered_cities():
        res["note"] = f"No data was collected for {c}. Cities covered: " + ", ".join(covered_cities())
    return res


def get_wasalt_listing(listing_id: str) -> dict:
    lid = re.sub(r"\D", "", str(listing_id))
    for v in load("wasalt_villas"):
        if v["id"] == lid:
            return {"listing": {k: x for k, x in v.items() if x is not None}, "source": "Source: Wasalt.sa",
                    "how_to_contact": load("contacts")["wasalt"]["listing_contact"], "caveat": WASALT_NOTE}
    return {"error": f"Listing {listing_id} is not in the sampled data.",
            "hint": "Only the first results page per city was collected; check wasalt.sa directly."}


def wasalt_market_stats(city: str | None = None) -> dict:
    summary = load("wasalt_city_summary")
    c = canon_city(city)
    if not c:
        ranked = sorted(summary, key=lambda s: -s["median_price_sar"])
        return {"cities": ranked, "source": "Source: Wasalt.sa",
                "caveat": "results_on_wasalt is the site's own count; medians describe only the rows collected."}
    rows = [v for v in load("wasalt_villas") if v["city"] == c]
    if not rows:
        return {"error": f"No data for {c}.", "cities_covered": covered_cities()}
    s = next(x for x in summary if x["city"] == c)
    prices = [v["price_sar"] for v in rows]
    ppsqm = [v["sar_per_sqm"] for v in rows if v["sar_per_sqm"]]
    districts: dict[str, int] = {}
    for v in rows:
        name = v.get("district_en") or v["district_ar"]
        districts[name] = districts.get(name, 0) + 1
    return {"city": c, "results_on_wasalt": s["results_on_wasalt"], "rows_collected": len(rows),
            "price_sar": {"min": min(prices), "median": statistics.median(prices), "max": max(prices)},
            "sar_per_sqm": {"min": min(ppsqm), "median": statistics.median(ppsqm), "max": max(ppsqm)},
            "top_districts": sorted(districts.items(), key=lambda t: -t[1])[:6],
            "source": "Source: Wasalt.sa", "caveat": "Medians describe this sample only, not the whole market."}


def list_wasalt_projects() -> dict:
    return {"projects": load("wasalt_projects"), "source": "Source: Wasalt.sa",
            "note": "Neptune is a DarGlobal project; Wasalt lists Dar Global as its developer."}


def dataset_info() -> dict:
    return load("meta")


def all_known_urls() -> set[str]:
    """Every URL in the bundled data, used to verify links in answers."""
    urls: set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            urls.update(re.findall(r"https?://[^\s\"'<>)]+", x))
    for name in ("darglobal_projects", "wasalt_villas", "wasalt_projects", "contacts", "darglobal_company", "meta"):
        walk(load(name))
    return urls
