from app import guards

EV = guards.build_evidence(['{"price_sar": 2150000, "median": 1550000.0, "url": "https://wasalt.sa/property/sale/5971799"}',
                            "median 2075000; SAR 6,503 per sqm; from 4280000; SAR 1 billion"])


def test_supported_figures_and_rounding():
    for text in ["SAR 2,150,000", "about SAR 2.15M", "SAR 2.2 million", "SAR 1.55 million", "6,500 SAR per sqm",
                 "valued at SAR 1 billion", "from SAR 4.28M"]:
        assert guards.verify(text, EV).unsupported == [], text


def test_unsupported_and_derived():
    assert guards.verify("It costs SAR 3,100,000.", EV).unsupported == ["3,100,000"]
    ok = guards.verify("Riyadh SAR 2,075,000 vs Jeddah SAR 1,550,000: SAR 525,000 more.", EV)
    assert ok.unsupported == []


def test_ignores_years_ids_small_numbers_and_metres():
    r = guards.verify("Completion 2028, 5 bedrooms on a 15m street. Listing 5971799.", EV)
    assert r.unsupported == []


def test_links():
    r = guards.verify("See [this](https://fake.example.com/p), https://darglobal.co.uk/neptune and https://wasalt.sa/x/y.", EV)
    assert "fake.example.com" not in r.answer and "https://darglobal.co.uk/neptune" in r.answer
    assert "wasalt.sa/x/y" not in r.answer and len(r.links_removed) == 2


def test_phones():
    r = guards.verify("WhatsApp +971 800 40409, Wasalt 8001233227, agent 0551234567, or +966 55 123 4567.", EV)
    assert "+971 800 40409" in r.answer and "8001233227" in r.answer
    assert "0551234567" not in r.answer and "+966 55 123 4567" not in r.answer and len(r.phones_removed) == 2
    assert r.unsupported == []
