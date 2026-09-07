"""JD 解析器：优先 LLM 结构化输出，失败时正则规则兜底。"""
import json
import re

from pydantic import BaseModel

from app.agent.llm import LlmClient, LlmUnavailable

TECH_KEYWORDS: list[str] = [
    "linux", "k8s", "kubernetes", "docker", "java", "python", "go", "golang",
    "nginx", "redis", "mysql", "kafka", "rabbitmq", "elasticsearch", "prometheus",
    "grafana", "jenkins", "gitlab", "ansible", "terraform", "云原生", "微服务",
    "devops", "ci/cd", "vue", "react", "spring", "springboot", "spring boot",
]

_RISK_PATTERNS = ["急招", "大量", "面议"]


class JdParsed(BaseModel):
    responsibilities: list[str] = []
    requirements: list[str] = []
    tech_stack: list[str] = []
    experience_hint: str = ""
    risk_signals: list[str] = []
    fallback: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _extract_tech_stack(text: str) -> list[str]:
    found: list[str] = []
    for kw in TECH_KEYWORDS:
        # 纯 ASCII 单词用"非 ASCII 字母数字"作边界，避免误匹配
        # （如 go→good、java→javascript），同时兼容中文相邻场景；
        # 含斜杠或中文的关键词直接子串匹配。
        if re.fullmatch(r"[A-Za-z0-9]+", kw):
            pattern = r"(?<![A-Za-z0-9])" + re.escape(kw) + r"(?![A-Za-z0-9])"
        else:
            pattern = re.escape(kw)
        if re.search(pattern, text, re.IGNORECASE) and kw not in found:
            found.append(kw)
    return found


def _extract_section(text: str, markers: tuple[str, ...]) -> list[str]:
    """抓取 markers 之后到下一个小标题之前的段落，按行/分号切分。"""
    lines = text.splitlines()
    collecting = False
    buf: list[str] = []
    for line in lines:
        stripped = line.strip().lstrip("•·-*\t ")
        if not stripped:
            continue
        if not collecting:
            matched = next((m for m in markers if m in stripped), None)
            if matched is not None:
                collecting = True
                # 从匹配到的标题之后截取，避免按行内第一个冒号切分导致前一段内容泄漏
                idx = stripped.index(matched) + len(matched)
                after_marker = stripped[idx:].lstrip("：: ")
                if after_marker:
                    buf.append(after_marker)
            continue
        # 遇到下一个小标题停止
        if re.match(r"^(岗位职责|职位描述|工作内容|职责描述|任职要求|任职资格|岗位要求|"
                    r"职位要求|薪资福利|福利待遇|公司介绍)", stripped):
            break
        buf.append(stripped)
    # 进一步按分号、句号切分
    items: list[str] = []
    for b in buf:
        for piece in re.split(r"[;；。]", b):
            piece = piece.strip(" •·-*\t")
            if piece:
                items.append(piece)
    return items


def parse_by_rules(jd_text: str) -> JdParsed:
    """纯正则/关键词兜底解析，不依赖 LLM。"""
    text = jd_text or ""
    responsibilities = _extract_section(text, ("岗位职责", "职位描述", "工作内容", "职责描述"))
    requirements = _extract_section(text, ("任职要求", "任职资格", "岗位要求", "职位要求", "要求"))
    tech_stack = _extract_tech_stack(text)
    risk_signals = [p for p in _RISK_PATTERNS if p in text]
    return JdParsed(
        responsibilities=responsibilities,
        requirements=requirements,
        tech_stack=tech_stack,
        experience_hint="",
        risk_signals=risk_signals,
        fallback=True,
    )


_SYSTEM_PROMPT = (
    "你是职位分析器。请从给定的职位描述（JD）中提取结构化信息，"
    "只输出 JSON 对象，键为 responsibilities、requirements、tech_stack、"
    "experience_hint、risk_signals。其中 responsibilities/requirements/tech_stack/"
    "risk_signals 为字符串数组，experience_hint 为字符串（如'3-5年'，无则为空串）。"
    "不要输出任何 JSON 以外的文字。"
)


class JdParser:
    def __init__(self, llm: LlmClient):
        self.llm = llm

    async def parse(self, jd_text: str) -> JdParsed:
        try:
            result = await self.llm.complete(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": jd_text or ""},
                ],
                json_mode=True,
            )
            data = json.loads(result.content)
            parsed = JdParsed.model_validate(data)
            return parsed.model_copy(update={
                "fallback": False,
                "prompt_tokens": getattr(result, "prompt_tokens", 0),
                "completion_tokens": getattr(result, "completion_tokens", 0),
            })
        except (LlmUnavailable, json.JSONDecodeError, ValueError, TypeError, AttributeError):
            return parse_by_rules(jd_text)
