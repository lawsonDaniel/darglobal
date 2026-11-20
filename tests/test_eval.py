from eval import run_qa


def test_judge_rules():
    case = {"include": ["Riyadh"], "include_any": ["2,075,000", "2.08"], "exclude": ["def "], "exclude_phones": True,
            "no_unverified": True}
    assert run_qa.judge(case, "Riyadh median SAR 2,075,000. Call +971 800 40409.", {"figures_unverified": []}) == []
    bad = run_qa.judge(case, "Jeddah. def f(): call 0551234567", {"figures_unverified": ["9,999"]})
    assert len(bad) == 5
