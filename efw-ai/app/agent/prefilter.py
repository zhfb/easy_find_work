"""规则预筛：零成本硬过滤，在调用 LLM 之前剔除明显不符合条件的职位。"""

from dataclasses import dataclass


@dataclass
class PreFilterResult:
    allowed: bool = True
    reason: str = ""


class PreFilter:
    """纯同步规则预筛，按优先级依次判定，命中即返回 skip。"""

    def evaluate(
        self,
        job: dict,
        profile=None,
        rules: dict | None = None,
        blacklist_companies: set[str] | None = None,
    ) -> PreFilterResult:
        rules = rules or {}
        blacklist_companies = blacklist_companies or set()

        # 1. 标题黑名单词（如"销售""地推"等用户明确排斥的岗位关键词）
        for kw in rules.get("exclude_title_keywords", []):
            if kw and kw in job.get("title", ""):
                return PreFilterResult(allowed=False, reason=f"标题含黑名单词：{kw}")

        # 2. 公司黑名单
        if job.get("company") in blacklist_companies:
            return PreFilterResult(allowed=False, reason=f"公司在黑名单：{job.get('company')}")

        # 3. 薪资下限：仅当职位有明确薪资上限时才比较；面议（salary_max 为 None）放行
        floor = rules.get("salary_min")
        salary_max = job.get("salary_max")
        if floor is not None and salary_max is not None and salary_max < floor:
            return PreFilterResult(
                allowed=False,
                reason=f"薪资上限 {salary_max}K 低于下限 {floor}K",
            )

        # 4. 城市规则：用户指定了目标城市且职位城市不匹配
        target_city = rules.get("city")
        if target_city and job.get("city") != target_city:
            return PreFilterResult(
                allowed=False,
                reason=f"城市不匹配：职位 {job.get('city')} ≠ 目标 {target_city}",
            )

        return PreFilterResult(allowed=True, reason="")
