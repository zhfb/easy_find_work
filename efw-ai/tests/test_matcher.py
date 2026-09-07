from app.agent.matcher import Matcher, score_by_rules, MatchResult
from app.agent.jd_parser import JdParsed
from app.models import Profile
from app.agent.llm import LlmUnavailable, LLMResult

PROFILE = Profile(skills="linux,k8s,docker", experience_years=3,
                  expected_salary_min=15, expected_salary_max=25)
JD = JdParsed(responsibilities=[], requirements=[], tech_stack=["linux","k8s"],
              experience_hint="3-5年", risk_signals=[], fallback=False)

def test_rule_score_skill_overlap():
    r = score_by_rules(PROFILE, JD, salary_min=15, salary_max=25)
    assert r.score >= 6.0
    assert r.score <= 10.0
    assert r.fallback is True

class FailLlm:
    async def complete(self, messages, **kw): raise LlmUnavailable("no key")

async def test_matcher_fallback_when_llm_down():
    m = Matcher(llm=FailLlm())
    r = await m.score(PROFILE, JD, {"salary_min": 15, "salary_max": 25})
    assert r.score > 0 and r.score <= 10.0 and r.fallback is True

class FakeLlm:
    async def complete(self, messages, **kw):
        return LLMResult(content='{"score": 8.5, "reason": "技能高度匹配"}',
                         prompt_tokens=120, completion_tokens=30)

async def test_matcher_llm_success_path():
    m = Matcher(llm=FakeLlm())
    r = await m.score(PROFILE, JD, {"salary_min": 15, "salary_max": 25})
    assert r.score == 8.5
    assert r.fallback is False
    assert r.reason == "技能高度匹配"
    assert r.prompt_tokens == 120
    assert r.completion_tokens == 30
