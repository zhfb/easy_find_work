from app.agent.jd_parser import JdParser, parse_by_rules
from app.agent.llm import LlmUnavailable


class FailLlm:
    async def complete(self, messages, **kw):
        raise LlmUnavailable("no key")


def test_rule_fallback_extracts_tech_stack():
    parsed = parse_by_rules("岗位职责：负责k8s集群运维。任职要求：熟悉linux与docker。")
    assert "k8s" in parsed.tech_stack or "docker" in parsed.tech_stack
    assert parsed.fallback is True


async def test_parser_falls_back_when_llm_down():
    parser = JdParser(llm=FailLlm())
    parsed = await parser.parse("职责：维护kubernetes集群。")
    assert parsed.fallback is True
    assert "kubernetes" in parsed.tech_stack
