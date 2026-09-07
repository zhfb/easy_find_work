"""跟进分析器：根据 HR 回复对话推断申请状态变化，并生成建议回复。

- analyze_by_rules 是纯函数，基于关键词规则，可单测、无外部依赖。
- FollowUpAnalyzer 优先调用 LLM（json_mode），失败时回退到规则引擎。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

VALID_TRANSITIONS = {"applied", "responded", "interview", "offer", "rejected", "withdrawn"}

# 各状态对应的模板回复（规则引擎回退时使用）
_TEMPLATE_REPLIES = {
    "interview": "好的，请问具体时间和地点？我会准时参加。",
    "offer": "感谢录用！请问入职时间和薪资细节可以确认一下吗？",
    "rejected": "好的，感谢告知，祝贵司招聘顺利。",
    "responded": "您好，我对这个岗位很感兴趣，请问可以详细聊聊吗？",
}


@dataclass
class FollowUpResult:
    """单次跟进分析结果。

    Attributes:
        new_status: 推断的新状态，取值见 VALID_TRANSITIONS；无变化时为 None。
        suggested_reply: 建议回复给 HR 的消息文本。
    """

    new_status: str | None
    suggested_reply: str = ""


def analyze_by_rules(conversation: str) -> FollowUpResult:
    """基于关键词规则分析对话，返回 FollowUpResult（纯函数，无外部依赖）。

    规则优先级（先匹配先返回）：
      1. "面试|约个时间|面谈" → interview
      2. "offer|录用|入职" → offer
      3. "不合适|暂时不|已读不回(2次以上)" → rejected
      4. "你好|还在吗|详细" → responded
      5. 默认 → None（无变化）
    """
    text = conversation or ""

    # 1. 面试邀约
    if re.search(r"面试|约个时间|面谈", text):
        return FollowUpResult(new_status="interview", suggested_reply=_TEMPLATE_REPLIES["interview"])

    # 2. 录用 / offer
    if re.search(r"offer|录用|入职", text, re.IGNORECASE):
        return FollowUpResult(new_status="offer", suggested_reply=_TEMPLATE_REPLIES["offer"])

    # 3. 拒绝 / 不合适 / 已读不回（2 次以上）
    if re.search(r"不合适|暂时不", text) or text.count("已读不回") >= 2:
        return FollowUpResult(new_status="rejected", suggested_reply=_TEMPLATE_REPLIES["rejected"])

    # 4. HR 主动打招呼 / 询问详情
    if re.search(r"你好|还在吗|详细", text):
        return FollowUpResult(new_status="responded", suggested_reply=_TEMPLATE_REPLIES["responded"])

    # 5. 默认：无变化
    return FollowUpResult(new_status=None, suggested_reply="")


class FollowUpAnalyzer:
    """LLM 优先的跟进分析器，失败时回退到关键词规则。

    LLM 输出 JSON：{"new_status": "...", "suggested_reply": "..."}
    new_status 必须在 VALID_TRANSITIONS 中，否则视为无效并回退。
    """

    def __init__(self, llm):
        self.llm = llm

    async def analyze(self, conversation: str) -> FollowUpResult:
        """分析对话，返回 FollowUpResult。LLM 不可用或输出异常时回退规则引擎。"""
        system = (
            "你是 Boss 直聘求职助手。根据求职者与 HR 的对话记录，判断申请状态变化并生成建议回复。"
            "状态只能取以下之一：applied、responded、interview、offer、rejected、withdrawn；"
            "如果状态没有变化，new_status 设为 null。"
            "只输出 JSON：{\"new_status\": \"...\" 或 null, \"suggested_reply\": \"...\"}"
        )
        user = f"对话记录：\n{conversation}"

        try:
            result = await self.llm.complete(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
                json_mode=True,
            )
            data = json.loads(result.content)
            new_status = data.get("new_status")
            suggested_reply = str(data.get("suggested_reply", "") or "").strip()

            # 校验：new_status 必须合法（None 或在 VALID_TRANSITIONS 中）
            if new_status is not None and new_status not in VALID_TRANSITIONS:
                raise ValueError(f"invalid new_status: {new_status}")

            return FollowUpResult(new_status=new_status, suggested_reply=suggested_reply)
        except Exception as e:
            logger.warning("FollowUpAnalyzer LLM 失败，回退规则引擎: %s", e)
            return analyze_by_rules(conversation)
