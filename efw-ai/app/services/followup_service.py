"""跟进服务：定时扫描进行中的申请，读取 HR 消息并推进状态。

- run_once 读取所有 status in (applied, responded, interview) 的 Application，
  通过 BossClient.read_messages 取对话，交给 FollowUpAnalyzer 分析，
  有状态变化时更新 Application 并写入 replied / status_changed 事件。
- page（浏览器页面对象）通过构造函数注入；不可用时记录日志并跳过。
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlmodel import Session, select

from app.agent.followup import VALID_TRANSITIONS, FollowUpResult
from app.models import Application, ApplicationEvent

logger = logging.getLogger(__name__)

_TRACKED_STATUSES = ("applied", "responded", "interview")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _messages_to_conversation(messages: list[dict]) -> str:
    """将 BossClient.read_messages 返回的消息列表转为纯文本对话。"""
    if not messages:
        return ""
    parts: list[str] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        content = m.get("content") or m.get("text") or m.get("message") or ""
        if content:
            parts.append(str(content))
    return "\n".join(parts)


class FollowupService:
    """跟进循环服务：扫描进行中申请 → 读消息 → 分析 → 推进状态。"""

    def __init__(self, analyzer, boss_client, risk, session_factory, page=None):
        self.analyzer = analyzer
        self.boss_client = boss_client
        self.risk = risk
        self.session_factory = session_factory
        self.page = page  # 浏览器页面对象，可外部注入；None 时跳过

    async def run_once(self) -> int:
        """执行一次跟进扫描，返回扫描处理的申请条数（无论状态是否变化）。

        - page 不可用或风控要求暂停时，记录日志并返回 0。
        - 每条申请：读消息 → 分析 → 有合法状态变化则更新 + 写事件。
        - 状态推进条数单独通过日志记录，不影响返回值。
        """
        # 1. 浏览器页面不可用 → 跳过
        if self.page is None:
            logger.warning("FollowupService: 浏览器页面不可用，跳过本次跟进")
            return 0

        # 2. 风控检查（掉线 / 验证码 / 限额）
        should_pause, reason = self.risk.should_pause()
        if should_pause:
            logger.warning("FollowupService: 风控暂停（%s），跳过本次跟进", reason)
            return 0

        # 3. 读取所有进行中的申请
        with self.session_factory() as session:
            applications = session.exec(
                select(Application).where(Application.status.in_(_TRACKED_STATUSES))
            ).all()
            # 脱离 session 使用，避免长事务
            app_ids = [a.id for a in applications]

        processed = 0
        changed_count = 0

        for app_id in app_ids:
            try:
                changed = await self._process_one(app_id)
                processed += 1  # 每条扫描到的申请都计入"处理条数"
                if changed:
                    changed_count += 1
            except Exception as e:
                logger.exception("FollowupService: 处理申请 %s 失败: %s", app_id, e)

        if changed_count:
            logger.info("FollowupService: 本次扫描 %d 条，状态推进 %d 条", processed, changed_count)
        return processed

    # ---------- 内部 ----------

    async def _process_one(self, application_id: int) -> bool:
        """处理单条申请，返回是否发生了状态变化。"""
        # 1. 读取当前申请
        with self.session_factory() as session:
            app = session.get(Application, application_id)
            if app is None:
                return False
            current_status = app.status

        # 2. 读取 HR 消息
        try:
            messages = await self.boss_client.read_messages(self.page)
        except Exception as e:
            logger.warning("FollowupService: 读取消息失败 (app=%s): %s", application_id, e)
            return False

        conversation = _messages_to_conversation(messages)
        if not conversation:
            return False  # 无消息不分析

        # 3. 分析对话
        result: FollowUpResult = await self.analyzer.analyze(conversation)

        # 4. 状态变化校验
        if result.new_status is None:
            return False
        if result.new_status not in VALID_TRANSITIONS:
            return False
        if result.new_status == current_status:
            return False  # 状态未变，不重复写入

        # 5. 更新状态 + 写事件
        # 二次读取做 TOCTOU 校验：分析期间状态可能已被其他流程改变，
        # 重新读取确保基于最新状态写入，避免覆盖并发更新。
        with self.session_factory() as session:
            app = session.get(Application, application_id)
            if app is None:
                return False
            old_status = app.status
            app.status = result.new_status
            app.updated_at = _now()

            session.add(ApplicationEvent(
                application_id=application_id,
                event_type="replied",
                detail=result.suggested_reply or "",
            ))
            session.add(ApplicationEvent(
                application_id=application_id,
                event_type="status_changed",
                detail=f"{old_status} → {result.new_status}",
            ))
            session.commit()

        logger.info(
            "FollowupService: 申请 %s 状态 %s → %s",
            application_id, old_status, result.new_status,
        )
        return True
