"""Turn the bundled data into LangChain Documents for the vector index.

One document per DarGlobal project, Wasalt listing, Wasalt project and city summary, plus the
company profile, each press headline, both contact records and the dataset notes. Text is written
as plain sentences (good for embeddings and BM25); metadata keeps ids, kinds and URLs.
"""
from __future__ import annotations

from langchain_core.documents import Document

from . import tools

CITY_AR = {"Riyadh": "الرياض", "Jeddah": "جدة", "Khobar": "الخبر", "Dammam": "الدمام", "Mecca": "مكة المكرمة",
           "Medina": "المدينة المنورة", "Khamis Mushait": "خميس مشيط", "Buraidah": "بريدة", "Jazan": "جازان"}

KINDS = ("darglobal_project", "darglobal_company", "darglobal_press", "contacts", "wasalt_villa", "wasalt_city",
         "wasalt_project", "dataset")


def _join(parts: list[str | None]) -> str:
    return " ".join(p for p in parts if p)


def _sar(x) -> str:
    return f"SAR {x:,.0f}"


def build_documents() -> list[Document]:
    docs: list[Document] = []

    for p in tools.load("darglobal_projects"):
        slug = p["url"].split("darglobal.co.uk/", 1)[-1]
        text = _join([
            f"DarGlobal project: {p['name']}.",
            f"Country: {p['country']}. Location: {p['location']}.",
            p.get("property_types") and f"Property types: {p['property_types']}.",
            p.get("bedrooms") and f"Bedrooms: {p['bedrooms']}.",
            p.get("unit_sizes") and f"Unit sizes: {p['unit_sizes']}.",
            p.get("completion") and f"Completion: {p['completion']}.",
            p.get("status") and f"Status: {p['status']}.",
            p.get("brand") and f"Brand partner: {p['brand']} (branded residence).",
            p.get("notes"),
        ])
        docs.append(Document(id=f"dg:{slug}", page_content=text,
                             metadata={"kind": "darglobal_project", "title": p["name"], "url": p["url"],
                                       "country": p["country"]}))

    co = tools.load("darglobal_company")
    docs.append(Document(id="dg:company", page_content=_join([
        f"About DarGlobal (company profile, who they are): {co['description']}",
        f"Stock listing: {co['stock_listing']}; DarGlobal is a publicly listed company.",
        "Projects in: " + ", ".join(co["countries_with_projects"]) + ".",
        "Brand partners: " + ", ".join(b["name"] for b in co["brand_partners"]) + "."]),
        metadata={"kind": "darglobal_company", "title": "DarGlobal company profile", "url": "https://darglobal.co.uk/about"}))
    for i, item in enumerate(co["recent_press"]["items"]):
        docs.append(Document(id=f"dg:press:{i}", page_content=f"DarGlobal press release: {item['title']}.",
                             metadata={"kind": "darglobal_press", "title": item["title"], "url": item["url"]}))

    c = tools.load("contacts")
    dg, ws = c["darglobal"], c["wasalt"]
    docs.append(Document(id="contacts:darglobal", page_content=_join([
        "How to contact DarGlobal: call, phone number, WhatsApp, enquiries, sales team, get in touch, reach.",
        f"WhatsApp {dg['whatsapp']['number']} ({dg['whatsapp']['link']}).",
        f"Phone {dg['phone']['number']}: {dg['phone']['note']}", dg["register_interest"], dg["not_found"],
        "التواصل مع دار جلوبال: رقم الهاتف، واتساب، الاستفسارات والمبيعات."]),
        metadata={"kind": "contacts", "title": "DarGlobal contacts", "url": dg["website"]}))
    docs.append(Document(id="contacts:wasalt", page_content=_join([
        "How to contact Wasalt: customer service phone number, support, call; how to reach the seller, agent or advertiser of a listing.",
        f"Customer service {ws['customer_service']['number']}.", ws["listing_contact"], ws["why_no_agent_numbers"],
        "التواصل مع وصلت: رقم خدمة العملاء، الاتصال، والتواصل مع المعلن أو صاحب الإعلان."]),
        metadata={"kind": "contacts", "title": "Wasalt contacts", "url": ws["website"]}))

    for s in tools.load("wasalt_city_summary"):
        docs.append(Document(id=f"wasalt:city:{s['city']}", page_content=_join([
            f"Villa market snapshot for {s['city']} ({CITY_AR.get(s['city'], '')}), Saudi Arabia, from Wasalt: prices and statistics.",
            f"Wasalt shows {s['results_on_wasalt']:,} villas for sale in {s['city']}.",
            f"Sample of {s['rows_collected']} listings: median price {_sar(s['median_price_sar'])},",
            f"median {_sar(s['median_sar_per_sqm'])} per sqm, median area {s['median_area_sqm']} sqm.",
            f"أسعار الفلل للبيع في {CITY_AR.get(s['city'], s['city'])}: متوسط الأسعار وإحصاءات السوق."]),
            metadata={"kind": "wasalt_city", "title": f"Wasalt villas in {s['city']}", "city": s["city"]}))

    for pr in tools.load("wasalt_projects"):
        docs.append(Document(id=f"wasalt:project:{pr['id']}", page_content=_join([
            f"Wasalt new-build project: {pr['name_en']} ({pr['name_ar']}).",
            f"Location: {pr['location_ar']}, {pr['city']}. Property types: {pr['types_ar']}.",
            pr.get("price_from_sar") and f"Prices from {_sar(pr['price_from_sar'])}."]),
            metadata={"kind": "wasalt_project", "title": pr["name_en"], "url": pr["url"], "city": pr["city"]}))

    for v in tools.load("wasalt_villas"):
        district = _join([v.get("district_en"), f"({v['district_ar']})" if v.get("district_en") else v["district_ar"]])
        sector = v.get("sector_en") or v.get("sector_ar")
        docs.append(Document(id=f"wasalt:villa:{v['id']}", page_content=_join([
            f"Villa for sale in {district}, {sector + ', ' if sector else ''}{v['city']}.",
            f"Price {_sar(v['price_sar'])}.", f"Area {v['area_sqm']:g} sqm ({_sar(v['sar_per_sqm'])} per sqm).",
            v.get("bedrooms") and f"{v['bedrooms']} bedrooms.", v.get("bathrooms") and f"{v['bathrooms']} bathrooms.",
            v.get("facing") and f"Facing {v['facing']}.",
            v.get("street_width_m") and f"Street width {v['street_width_m']} m.",
            "Marked new." if v.get("marked_new") else None, f"Listing {v['id']}.",
            f"فيلا للبيع في حي {v['district_ar']}، {CITY_AR.get(v['city'], v['city'])}."]),
            metadata={"kind": "wasalt_villa", "title": f"Villa {v['id']}", "url": v["url"], "city": v["city"]}))

    meta = tools.load("meta")
    docs.append(Document(id="dataset", page_content=_join([
        f"About this data: collected {meta['collected']} by {meta['method']}."] + meta["notes"]),
        metadata={"kind": "dataset", "title": "Dataset notes"}))
    return docs
