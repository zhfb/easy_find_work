"""投递决策器：纯规则引擎。

硬规则优先（黑名单 / 当日限额），软规则基于匹配评分阈值三段式判定。
"""

from dataclasses import dataclass


@dataclass
class Decision:
    """单次投递决策结果。

    Attributes:
        decision: 决策动作，取值 deliver | skip | pending。
        reason: 人类可读的决策原因。
    """

    decision: str
    reason: str


class Decider:
    """纯规则投递决策器。

    规则优先级：
      1. 硬规则：黑名单命中 → skip；当日投递已达限额 → skip。
      2. 软规则：
         - match_score >= threshold → deliver
         - match_score < threshold - 1 → skip（评分不足）
         - 其余（存疑区间 [threshold-1, threshold)）→ pending
    """

    def decide(
        self,
        match_score: float,
        threshold: float,
        rules: dict,
        blacklist_hit: bool,
        daily_used: int,
        daily_limit: int,
    ) -> Decision:
        # 硬规则 1：黑名单
        if blacklist_hit:
            return Decision(decision="skip", reason="黑名单")

        # 硬规则 2：当日限额
        if daily_used >= daily_limit:
            return Decision(decision="skip", reason="当日限额用尽")

        # 软规则：阈值三段式
        if match_score >= threshold:
            return Decision(decision="deliver", reason="评分达标")
        if match_score < threshold - 1:
            return Decision(decision="skip", reason="评分不足")
        return Decision(decision="pending", reason="存疑区间")
