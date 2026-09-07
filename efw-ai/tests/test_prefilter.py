from app.agent.prefilter import PreFilter, PreFilterResult

pf = PreFilter()
BASE = {"boss_job_id": "1", "title": "运维工程师", "company": "某云", "salary_text": "15-25K",
        "salary_min": 15, "salary_max": 25, "city": "武汉"}

def test_allowed_when_no_rule_hit():
    r = pf.evaluate(BASE, rules={}, blacklist_companies=set())
    assert r.allowed and r.reason == ""

def test_blacklisted_company_skipped():
    r = pf.evaluate(BASE, rules={}, blacklist_companies={"某云"})
    assert not r.allowed and "黑名单" in r.reason

def test_salary_below_floor_skipped():
    r = pf.evaluate(BASE, rules={"salary_min": 30}, blacklist_companies=set())
    assert not r.allowed and "薪资" in r.reason

def test_salary_missing_passes_to_llm():
    job = dict(BASE, salary_min=None, salary_max=None)
    r = pf.evaluate(job, rules={"salary_min": 30}, blacklist_companies=set())
    assert r.allowed  # 面议放行

def test_title_blacklist_skipped():
    job = dict(BASE, title="销售工程师")
    r = pf.evaluate(job, rules={"exclude_title_keywords": ["销售"]}, blacklist_companies=set())
    assert not r.allowed and "黑名单" in r.reason

def test_city_mismatch_skipped():
    r = pf.evaluate(BASE, rules={"city": "北京"}, blacklist_companies=set())
    assert not r.allowed and "城市" in r.reason

def test_city_match_allowed():
    r = pf.evaluate(BASE, rules={"city": "武汉"}, blacklist_companies=set())
    assert r.allowed
