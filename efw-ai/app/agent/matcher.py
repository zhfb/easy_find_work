"""匹配评分：LLM 打分 + 规则兜底。"""
import json
import re
from dataclasses import dataclass

from app.agent.jd_parser import JdParsed
from app.agent.llm import LlmUnavailable
from app.models import Profile


@dataclass
class MatchResult:
    score: float
    reason: str
    fallback: bool
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _parse_skills(skills_str: str) -> list[str]:
    return [s.strip().lower() for s in re.split(r"[,，、;；\s]+", skills_str or "") if s.strip()]


def _parse_experience_hint(hint: str) -> int:
    """从 experience_hint 中提取最低年限数字，无则返回 0（视为无要求）。"""
    m = re.search(r"(\d+)", hint or "")
    return int(m.group(1)) if m else 0


def _experience_match(jd_years: int, profile_years: int) -> float:
    """经验匹配系数：相差 ≤2 → 1.0；2<差≤3 → 0.75；差 >3 → 0.5。"""
    diff = abs(jd_years - profile_years)
    if diff <= 2:
        return 1.0
    if diff > 3:
        return 0.5
    return 0.75  # diff == 3：spec 仅定义 ≤2 与 >3，此处线性插值


def _salary_overlap(p_min: float, p_max: float, j_min: float, j_max: float) -> float:
    """薪资区间重叠比例（相对于候选人期望区间），0-1。"""
    if p_max <= p_min:
        return 1.0 if j_min <= p_min <= j_max else 0.0
    overlap_low = max(p_min, j_min)
    overlap_high = min(p_max, j_max)
    overlap = max(0.0, overlap_high - overlap_low)
    return min(1.0, overlap / (p_max - p_min))


def score_by_rules(profile: Profile, jd_parsed: JdParsed,
                   salary_min: float, salary_max: float) -> MatchResult:
    """规则兜底打分：skills 重合率×5 + 经验匹配×3 + 薪资重叠×2，归一化 0-10。"""
    profile_skills = _parse_skills(profile.skills)
    jd_skills = [s.lower() for s in (jd_parsed.tech_stack or [])]

    # skills 重合率（Jaccard）
    if profile_skills or jd_skills:
        intersection = len(set(profile_skills) & set(jd_skills))
        union = len(set(profile_skills) | set(jd_skills))
        skill_rate = intersection / union if union else 0.0
    else:
        skill_rate = 0.0

    # 经验匹配
    jd_years = _parse_experience_hint(jd_parsed.experience_hint)
    exp_coef = _experience_match(jd_years, profile.experience_years)

    # 薪资重叠
    salary_rate = _salary_overlap(
        profile.expected_salary_min, profile.expected_salary_max,
        salary_min, salary_max,
    )

    score = skill_rate * 5 + exp_coef * 3 + salary_rate * 2
    score = max(0.0, min(10.0, round(score, 2)))

    reason = (f"规则兜底：技能重合 {skill_rate:.0%}（×5），"
              f"经验匹配系数 {exp_coef}（×3），薪资重叠 {salary_rate:.0%}（×2）")
    return MatchResult(score=score, reason=reason, fallback=True)


_SYSTEM_PROMPT = (
    "你是岗位匹配评分专家。请根据候选人简历与职位描述（JD），评估匹配程度。"
    "只输出 JSON 对象，包含两个键：score（0-10 的浮点数，10 为完全匹配）、"
    "reason（简短中文评分理由，不超过 100 字）。不要输出任何 JSON 以外的文字。"
)


class Matcher:
    def __init__(self, llm):
        self.llm = llm

    def _job_salary(self, job) -> tuple[float, float]:
        if isinstance(job, dict):
            return float(job.get("salary_min", 0) or 0), float(job.get("salary_max", 0) or 0)
        return float(getattr(job, "salary_min", 0) or 0), float(getattr(job, "salary_max", 0) or 0)

    def _job_text(self, job) -> str:
        if isinstance(job, dict):
            return job.get("jd_text", "") or ""
        return getattr(job, "jd_text", "") or ""

    async def score(self, profile: Profile, jd_parsed: JdParsed, job) -> MatchResult:
        salary_min, salary_max = self._job_salary(job)
        try:
            user_content = (
                f"【候选人】\n"
                f"技能：{profile.skills}\n"
                f"工作年限：{profile.experience_years} 年\n"
                f"期望薪资：{profile.expected_salary_min}-{profile.expected_salary_max}K\n"
                f"简历摘要：{profile.resume_summary}\n\n"
                f"【JD 结构化摘要】\n"
                f"技术栈：{', '.join(jd_parsed.tech_stack)}\n"
                f"经验要求：{jd_parsed.experience_hint}\n"
                f"职责：{'; '.join(jd_parsed.responsibilities)}\n"
                f"要求：{'; '.join(jd_parsed.requirements)}\n\n"
                f"【原始 JD】\n{self._job_text(job)}"
            )
            result = await self.llm.complete(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                json_mode=True,
            )
            data = json.loads(result.content)
            score = float(data.get("score", 0))
            score = max(0.0, min(10.0, score))
            reason = str(data.get("reason", "")).strip() or "LLM 评分"
            return MatchResult(
                score=score, reason=reason, fallback=False,
                prompt_tokens=getattr(result, "prompt_tokens", 0),
                completion_tokens=getattr(result, "completion_tokens", 0),
            )
        except (LlmUnavailable, json.JSONDecodeError, ValueError, TypeError, AttributeError):
            return score_by_rules(profile, jd_parsed, salary_min, salary_max)
