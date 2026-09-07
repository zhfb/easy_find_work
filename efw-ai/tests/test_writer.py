from dataclasses import dataclass, field

from app.agent.writer import Writer, build_by_template
from app.agent.llm import LlmUnavailable
from app.models import Profile


@dataclass
class JdParsed:
    responsibilities: list = field(default_factory=list)
    requirements: list = field(default_factory=list)
    tech_stack: list = field(default_factory=list)
    experience_hint: str = ""
    risk_signals: list = field(default_factory=list)
    fallback: bool = False


PROFILE = Profile(skills="linux,k8s", experience_years=3, resume_summary="负责过生产集群")
JD = JdParsed(tech_stack=["linux", "k8s"])


def test_template_uses_skill_overlap():
    msgs = build_by_template(PROFILE, JD)
    assert len(msgs) == 3
    assert any("linux" in m.lower() for m in msgs)
    assert all(len(m) <= 200 for m in msgs)


def test_template_single_skill_no_duplication():
    single_jd = JdParsed(tech_stack=["linux"])
    msgs = build_by_template(PROFILE, single_jd)
    assert len(msgs) == 3
    for m in msgs:
        assert "linux、linux" not in m
        assert "linux和linux" not in m
    assert any("linux" in m.lower() for m in msgs)


def test_template_no_overlap_generic_greeting():
    no_jd = JdParsed(tech_stack=["java", "spring"])
    msgs = build_by_template(PROFILE, no_jd)
    assert len(msgs) == 3
    assert all(len(m) <= 200 for m in msgs)
    # 无交集时不应出现候选人技能词
    assert not any("linux" in m.lower() for m in msgs)
    assert not any("k8s" in m.lower() for m in msgs)


class FailLlm:
    async def complete(self, messages, **kw):
        raise LlmUnavailable("no key")


async def test_writer_fallback_when_llm_down():
    w = Writer(llm=FailLlm())
    msgs = await w.write(PROFILE, {"title": "运维工程师"}, JD)
    assert len(msgs) >= 1


class _LLMResult:
    def __init__(self, content):
        self.content = content


class TwoMsgLlm:
    async def complete(self, messages, **kw):
        return _LLMResult('{"messages": ["第一条", "第二条"]}')


async def test_writer_pads_to_three_when_llm_returns_two():
    w = Writer(llm=TwoMsgLlm())
    msgs = await w.write(PROFILE, {"title": "运维工程师"}, JD)
    assert len(msgs) == 3
