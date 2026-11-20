import json

from app import tools


def test_counts():
    assert len(tools.load("darglobal_projects")) == 38
    assert len(tools.load("wasalt_villas")) == 245
    assert len(tools.load("wasalt_city_summary")) == 9


def test_parse_bedrooms_and_sizes():
    assert tools.parse_bedrooms("Studio, 1, 2, 3") == (0, 3)
    assert tools.parse_bedrooms("1-4 (apartments); 3-4 (penthouses)") == (1, 4)
    assert tools.parse_bedrooms(None) == (None, None)
    assert tools.parse_sizes("109 to 722 sqm (764 - 7,720 sqft)")[:2] == (109, 722)
    assert tools.parse_sizes("2,091 - 4,048 sqft")[:2] == (194, 376)
    assert tools.parse_sizes("Plot area 2,035 - 4,623 sqm; built-up area 2,192 - 4,406 sqm")[:2] == (2192, 4406)
    assert tools.parse_sizes("452 - 2,476 (no unit shown)")[:2] == (None, None)


def test_project_filters():
    oman = tools.search_darglobal_projects(country="Oman")
    assert oman["count"] >= 10 and all(p["country"] == "Oman" for p in oman["projects"])
    assert tools.search_darglobal_projects(country="UAE")["count"] >= 5
    trump = tools.search_darglobal_projects(brand="Trump")
    assert trump["count"] >= 5
    soon = tools.search_darglobal_projects(completion_by_year=2027)
    assert soon["count"] >= 2 and all("2026" in p["completion"] or "2027" in p["completion"] for p in soon["projects"])
    big = tools.search_darglobal_projects(min_bedrooms=5)
    assert big["count"] >= 3
    sold = tools.search_darglobal_projects(status="sold out")
    assert sold["count"] >= 3 and all("sold out" in p["status"].lower() for p in sold["projects"])


def test_get_project_and_ambiguity():
    assert "neptune" in tools.get_darglobal_project("Neptune")["project"]["url"]
    trump = tools.get_darglobal_project("Trump")
    assert "project" in trump
    assert "error" in tools.get_darglobal_project("Burj Khalifa Imaginary")


def test_villa_search():
    r = tools.search_wasalt_villas(city="riyadh", max_price=2_000_000, min_bedrooms=5, sort_by="price_desc")
    prices = [v["price_sar"] for v in r["listings"]]
    assert prices == sorted(prices, reverse=True) and all(p <= 2_000_000 for p in prices)
    assert tools.search_wasalt_villas(city="الخبر")["listings"][0]["city"] == "Khobar"
    assert tools.search_wasalt_villas(district="الرمال")["matches_in_sample"] >= 1
    assert tools.search_wasalt_villas(district="Al Rimal")["matches_in_sample"] >= 1
    none = tools.search_wasalt_villas(city="Tabuk")
    assert none["matches_in_sample"] == 0 and "note" in none


def test_listing_and_stats():
    assert tools.get_wasalt_listing("5971799")["listing"]["city"] == "Riyadh"
    assert "error" in tools.get_wasalt_listing("1")
    s = tools.wasalt_market_stats("Jeddah")
    assert s["rows_collected"] == 27 and s["price_sar"]["min"] <= s["price_sar"]["median"] <= s["price_sar"]["max"]
    allc = tools.wasalt_market_stats()["cities"]
    assert len(allc) == 9 and allc[0]["median_price_sar"] >= allc[-1]["median_price_sar"]


def test_contacts_and_no_personal_data():
    assert tools.get_contact_info("darglobal")["darglobal"]["whatsapp"]["number"] == "+971 800 40409"
    assert tools.get_contact_info("wasalt")["wasalt"]["customer_service"]["number"] == "8001233227"
    listings = json.dumps([tools.load(n) for n in ("darglobal_projects", "wasalt_villas", "wasalt_projects")], ensure_ascii=False)
    assert "whatsapp" not in listings.lower() and "+966" not in listings and "phone" not in listings.lower()
