import pytest
from app.agent.followup import FollowUpAnalyzer, analyze_by_rules, FollowUpResult
from app.agent.llm import LlmUnavailable

def test_rule_detects_interview():
    r = analyze_by_rules("您好，您方便周三来面试吗？")
    assert r.new_status == "interview"

def test_rule_detects_offer():
    r = analyze_by_rules("恭喜您，我们决定录用您！")
    assert r.new_status == "offer"

def test_rule_no_change():
    assert analyze_by_rules("好的知道了").new_status is None

def test_rule_detects_rejected():
    r = analyze_by_rules("很抱歉，您的经历与岗位不合适")
    assert r.new_status == "rejected"

def test_rule_rejected_read_no_reply_boundary():
    # "已读不回" 出现 1 次不触发 rejected
    assert analyze_by_rules("已读不回").new_status is None
    # "已读不回" 出现 2 次触发 rejected
    r = analyze_by_rules("已读不回，已读不回")
    assert r.new_status == "rejected"

def test_rule_detects_responded():
    r = analyze_by_rules("你好，请问还在吗？可以详细介绍一下吗？")
    assert r.new_status == "responded"

class FailLlm:
    async def complete(self, messages, **kw): raise LlmUnavailable("no key")

async def test_fallback_when_llm_down():
    a = FollowUpAnalyzer(llm=FailLlm())
    r = await a.analyze("约个时间面试")
    assert r.new_status == "interview"
