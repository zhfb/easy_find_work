"""Orchestrator 全链路测试：用 Fake 组件替换 LLM 依赖，验证决策链编排。"""
import json

import pytest
from sqlmodel import Session, select

from app.agent.orchestrator import Orchestrator
from app.agent.prefilter import PreFilterResult
from app.agent.jd_parser import JdParsed
from app.agent.matcher import MatchResult
from app.agent.decider import Decision
from app.models import Task, Job, Application, ApplicationEvent, Profile


# ---------- Fake 组件 ----------

class FakePre:
    def __init__(self, allowed=True, reason=""):
        self._allowed = allowed
        self._reason = reason

    def evaluate(self, job, profile=None, rules=None, blacklist_companies=None):
        return PreFilterResult(allowed=self._allowed, reason=self._reason)


class FakeJd:
    async def parse(self, text):
        return JdParsed(
            responsibilities=[], requirements=[], tech_stack=["linux"],
            experience_hint="", risk_signals=[], fallback=True,
        )


class FakeMatcher:
    def __init__(self, score=8.5, reason="技能匹配"):
        self._score = score
        self._reason = reason

    async def score(self, profile, jd, job):
        return MatchResult(score=self._score, reason=self._reason, fallback=True)


class FakeDecider:
    def __init__(self, decision="deliver", reason="ok"):
        self._decision = decision
        self._reason = reason

    def decide(self, score, threshold, rules, hit, used, limit):
        return Decision(self._decision, self._reason)


class FakeWriter:
    async def write(self, profile, job, jd):
        return ["您好，我熟悉linux，方便聊聊吗？"]


# ---------- 辅助 ----------

def _make_session_factory(engine):
    def sf():
        return Session(engine)
    return sf


def _seed_task_job_profile(engine, **task_kwargs):
    defaults = dict(name="t", keywords='["k8s"]', city="武汉", mode="auto", rules="{}")
    defaults.update(task_kwargs)
    with Session(engine) as s:
        task = Task(**defaults)
        s.add(task)
        profile = Profile(skills="linux,k8s", experience_years=3)
        s.add(profile)
        job = Job(boss_job_id="E1", title="运维", company="云",
                  jd_text="职责：k8s", city="武汉")
        s.add(job)
        s.commit()
        return task.id, job.id, profile.id


JOB_DICT = {
    "boss_job_id": "E1", "title": "运维", "company": "云",
    "jd_text": "职责：k8s", "salary_min": 15, "salary_max": 25,
}


# ---------- 测试 ----------

async def test_orchestrator_creates_deliver_application(engine):
    sf = _make_session_factory(engine)
    orch = Orchestrator(FakePre(), FakeJd(), FakeMatcher(), FakeDecider(), FakeWriter(), sf)
    task_id, job_id, profile_id = _seed_task_job_profile(engine)

    with Session(engine) as s:
        task = s.get(Task, task_id)
        profile = s.get(Profile, profile_id)
        app = await orch.process_job(task, JOB_DICT, profile, set(), 0)

    assert app.decision == "deliver"
    assert app.status == "applied"
    assert app.match_score == 8.5
    assert app.message.startswith("您好")

    with Session(engine) as s:
        rows = s.exec(select(Application)).all()
        assert len(rows) == 1
        events = s.exec(select(ApplicationEvent)).all()
        assert len(events) == 1
        assert events[0].event_type == "evaluated"


async def test_orchestrator_prefilter_skip(engine):
    sf = _make_session_factory(engine)
    orch = Orchestrator(
        FakePre(allowed=False, reason="公司在黑名单"),
        FakeJd(), FakeMatcher(), FakeDecider(), FakeWriter(), sf,
    )
    task_id, job_id, profile_id = _seed_task_job_profile(engine)

    with Session(engine) as s:
        task = s.get(Task, task_id)
        profile = s.get(Profile, profile_id)
        app = await orch.process_job(task, JOB_DICT, profile, set(), 0)

    assert app.decision == "skip"
    assert app.status == "skip"
    assert "黑名单" in app.llm_reason


async def test_orchestrator_dedup_returns_existing(engine):
    sf = _make_session_factory(engine)
    orch = Orchestrator(FakePre(), FakeJd(), FakeMatcher(), FakeDecider(), FakeWriter(), sf)
    task_id, job_id, profile_id = _seed_task_job_profile(engine)

    with Session(engine) as s:
        task = s.get(Task, task_id)
        profile = s.get(Profile, profile_id)
        first = await orch.process_job(task, JOB_DICT, profile, set(), 0)
        # 第二次调用应返回已有记录，不重复创建
        second = await orch.process_job(task, JOB_DICT, profile, set(), 0)

    assert first.id == second.id
    with Session(engine) as s:
        assert len(s.exec(select(Application)).all()) == 1


async def test_orchestrator_semi_mode_pending_manual(engine):
    sf = _make_session_factory(engine)
    orch = Orchestrator(FakePre(), FakeJd(), FakeMatcher(), FakeDecider(), FakeWriter(), sf)
    task_id, job_id, profile_id = _seed_task_job_profile(engine, mode="semi")

    with Session(engine) as s:
        task = s.get(Task, task_id)
        profile = s.get(Profile, profile_id)
        app = await orch.process_job(task, JOB_DICT, profile, set(), 0)

    assert app.decision == "deliver"
    assert app.status == "pending_manual"


async def test_orchestrator_decision_skip(engine):
    sf = _make_session_factory(engine)
    orch = Orchestrator(
        FakePre(), FakeJd(), FakeMatcher(score=3.0),
        FakeDecider(decision="skip", reason="评分不足"), FakeWriter(), sf,
    )
    task_id, job_id, profile_id = _seed_task_job_profile(engine)

    with Session(engine) as s:
        task = s.get(Task, task_id)
        profile = s.get(Profile, profile_id)
        app = await orch.process_job(task, JOB_DICT, profile, set(), 0)

    assert app.decision == "skip"
    assert app.status == "skip"
    assert app.match_score == 3.0


async def test_orchestrator_decision_pending(engine):
    sf = _make_session_factory(engine)
    orch = Orchestrator(
        FakePre(), FakeJd(), FakeMatcher(score=6.5),
        FakeDecider(decision="pending", reason="存疑区间"), FakeWriter(), sf,
    )
    task_id, job_id, profile_id = _seed_task_job_profile(engine)

    with Session(engine) as s:
        task = s.get(Task, task_id)
        profile = s.get(Profile, profile_id)
        app = await orch.process_job(task, JOB_DICT, profile, set(), 0)

    assert app.decision == "pending"
    assert app.status == "pending_manual"


async def test_orchestrator_token_accumulation(engine):
    """验证 LLM token 用量累计写入 config 表 ai_tokens_{task_id}。"""

    class FakeJdWithTokens:
        async def parse(self, text):
            return JdParsed(tech_stack=["linux"], fallback=False,
                            prompt_tokens=100, completion_tokens=50)

    class FakeMatcherWithTokens:
        async def score(self, profile, jd, job):
            return MatchResult(score=8.0, reason="ok", fallback=False,
                               prompt_tokens=200, completion_tokens=80)

    sf = _make_session_factory(engine)
    orch = Orchestrator(FakePre(), FakeJdWithTokens(), FakeMatcherWithTokens(),
                         FakeDecider(), FakeWriter(), sf)
    task_id, job_id, profile_id = _seed_task_job_profile(engine)

    with Session(engine) as s:
        task = s.get(Task, task_id)
        profile = s.get(Profile, profile_id)
        await orch.process_job(task, JOB_DICT, profile, set(), 0)

    from app.models import ConfigItem
    with Session(engine) as s:
        item = s.get(ConfigItem, f"ai_tokens_{task_id}")
        assert item is not None
        data = json.loads(item.value)
        assert data["prompt_tokens"] == 300   # 100 + 200
        assert data["completion_tokens"] == 130  # 50 + 80
