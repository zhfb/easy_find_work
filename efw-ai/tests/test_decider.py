from app.agent.decider import Decider

d = Decider()

def test_blacklist_always_skip():
    r = d.decide(9.0, 7.0, {}, True, 0, 20)
    assert r.decision == "skip" and "黑名单" in r.reason

def test_daily_limit_skip():
    r = d.decide(9.0, 7.0, {}, False, 20, 20)
    assert r.decision == "skip" and "限额" in r.reason

def test_above_threshold_deliver():
    r = d.decide(8.0, 7.0, {}, False, 0, 20)
    assert r.decision == "deliver"

def test_below_threshold_minus_one_skip():
    r = d.decide(5.5, 7.0, {}, False, 0, 20)
    assert r.decision == "skip"

def test_middle_range_pending():
    r = d.decide(6.5, 7.0, {}, False, 0, 20)
    assert r.decision == "pending"
