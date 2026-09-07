import pytest
from app.services.risk_controller import RiskController


def test_quota_pause():
    rc = RiskController(None, daily_limit=2)
    rc.record_delivery()
    rc.record_delivery()
    paused, reason = rc.should_pause()
    assert paused and "限额" in reason


def test_captcha_pause():
    rc = RiskController(None)
    rc.set_captcha_detected(True)
    assert rc.should_pause()[0]


def test_delay_in_range():
    rc = RiskController(None)
    assert 8 <= rc.next_delay_seconds() <= 25


def test_cool_off_after_five():
    rc = RiskController(None)
    for _ in range(5):
        rc.record_delivery()
    assert 120 <= rc.cool_off_seconds() <= 300
