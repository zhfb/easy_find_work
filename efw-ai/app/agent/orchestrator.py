"""决策链编排器：串联 PreFilter → JdParser → Matcher → Decider → Writer，
将单次岗位处理结果落库为 Application + ApplicationEvent。"""
import json
import logging
from datetime import datetime

from sqlmodel import Session, select

from app.models import Task, Job, Application, ApplicationEvent, Profile, ConfigItem

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Orchestrator:
    """全链路决策编排器。

    流程：
      1. PreFilter 规则预筛 → 不通过直接写 skip Application
      2. UNIQUE(job_id, task_id) 防重 → 已存在直接返回
      3. JdParser 解析 JD → Matcher 评分 → Decider 决策
      4. deliver → Writer 生成打招呼文案，落库
      5. skip / pending → 按决策结果落库
      6. 累计 LLM token 用量到 config 表
    """

    def __init__(self, prefilter, jd_parser, matcher, decider, writer, session_factory):
        self.prefilter = prefilter
        self.jd_parser = jd_parser
        self.matcher = matcher
        self.decider = decider
        self.writer = writer
        self.session_factory = session_factory

    # ---------- 内部辅助 ----------

    def _get_or_create_job(self, session: Session, job_dict: dict) -> Job:
        """按 boss_job_id 查找 Job，不存在则创建。"""
        job = session.exec(
            select(Job).where(Job.boss_job_id == job_dict["boss_job_id"])
        ).first()
        if job is not None:
            return job
        job = Job(
            boss_job_id=job_dict["boss_job_id"],
            title=job_dict.get("title", ""),
            company=job_dict.get("company", ""),
            company_scale=job_dict.get("company_scale", ""),
            financing_stage=job_dict.get("financing_stage", ""),
            industry=job_dict.get("industry", ""),
            salary_text=job_dict.get("salary_text", ""),
            salary_min=job_dict.get("salary_min"),
            salary_max=job_dict.get("salary_max"),
            experience_req=job_dict.get("experience_req", ""),
            education_req=job_dict.get("education_req", ""),
            city=job_dict.get("city", ""),
            jd_text=job_dict.get("jd_text", ""),
            job_url=job_dict.get("job_url", ""),
        )
        session.add(job)
        session.commit()
        session.refresh(job)
        return job

    def _accumulate_tokens(self, session: Session, task_id: int,
                           prompt_tokens: int, completion_tokens: int) -> None:
        """将 LLM token 用量累计写入 config 表 ai_tokens_{task_id}。"""
        if prompt_tokens == 0 and completion_tokens == 0:
            return
        key = f"ai_tokens_{task_id}"
        item = session.get(ConfigItem, key)
        try:
            data = json.loads(item.value) if item and item.value else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        data["prompt_tokens"] = data.get("prompt_tokens", 0) + prompt_tokens
        data["completion_tokens"] = data.get("completion_tokens", 0) + completion_tokens
        if item is None:
            item = ConfigItem(key=key, value=json.dumps(data))
            session.add(item)
        else:
            item.value = json.dumps(data)
            item.updated_at = _now()
        session.commit()

    def _save_application(self, session: Session, task: Task, job_id: int,
                          decision: str, status: str, message: str = "",
                          match_score: float | None = None,
                          llm_reason: str = "") -> Application:
        """写 Application + ApplicationEvent("evaluated")，返回带 id 的 Application。"""
        app = Application(
            job_id=job_id,
            task_id=task.id,
            mode=task.mode,
            decision=decision,
            match_score=match_score,
            llm_reason=llm_reason,
            message=message,
            status=status,
            applied_at=_now() if decision == "deliver" else None,
        )
        session.add(app)
        session.flush()  # 获取 app.id，不触发 expire

        event = ApplicationEvent(
            application_id=app.id,
            event_type="evaluated",
            detail=llm_reason or decision,
        )
        session.add(event)
        session.commit()
        session.refresh(app)  # 确保所有列属性已加载，避免 detach 后访问报错
        return app

    # ---------- 主流程 ----------

    async def process_job(
        self,
        task: Task,
        job_dict: dict,
        profile: Profile,
        blacklist_companies: set[str],
        daily_used: int,
    ) -> Application:
        """处理单个岗位，返回落库后的 Application（含 id）。"""
        rules = json.loads(task.rules or "{}")

        # 1. PreFilter 规则预筛
        pre = self.prefilter.evaluate(job_dict, profile, rules, blacklist_companies)
        if not pre.allowed:
            with self.session_factory() as session:
                job = self._get_or_create_job(session, job_dict)
                return self._save_application(
                    session, task, job.id,
                    decision="skip", status="skip", llm_reason=pre.reason,
                )

        # 2. UNIQUE(job_id, task_id) 防重
        with self.session_factory() as session:
            job = self._get_or_create_job(session, job_dict)
            existing = session.exec(
                select(Application).where(
                    Application.job_id == job.id,
                    Application.task_id == task.id,
                )
            ).first()
            if existing is not None:
                return existing
            job_id = job.id

        # 3. JdParser 解析 + Matcher 评分
        jd_parsed = await self.jd_parser.parse(job_dict.get("jd_text", ""))
        match = await self.matcher.score(profile, jd_parsed, job_dict)

        # 4. Decider 决策
        decision = self.decider.decide(
            match.score, task.match_threshold, rules, False, daily_used, task.daily_limit,
        )

        # 5-6. 按决策落库
        if decision.decision == "deliver":
            msgs = await self.writer.write(profile, job_dict, jd_parsed)
            message = msgs[0] if msgs else ""
            status = "pending_manual" if task.mode == "semi" else "applied"
            with self.session_factory() as session:
                app = self._save_application(
                    session, task, job_id,
                    decision="deliver", status=status, message=message,
                    match_score=match.score, llm_reason=match.reason,
                )
        elif decision.decision == "pending":
            with self.session_factory() as session:
                app = self._save_application(
                    session, task, job_id,
                    decision="pending", status="pending_manual",
                    match_score=match.score, llm_reason=decision.reason,
                )
        else:  # skip
            with self.session_factory() as session:
                app = self._save_application(
                    session, task, job_id,
                    decision="skip", status="skip",
                    match_score=match.score, llm_reason=decision.reason,
                )

        # 7. 累计 token 用量
        # 注意：当前仅累计 jd_parser 和 matcher 的 LLM token 用量。
        # Writer.write() 在 deliver 模式下也会发起 LLM 调用，但其返回类型为 list[str]，
        # 不携带 token 元数据，因此无法在此处累计。
        # 已知限制：后续需扩展 Writer.write() 返回结构（如 dataclass 含 messages + token 字段）
        # 以完整追踪 writer 的 token 用量（修改时需同步更新 Task 9 相关测试）。
        total_prompt = getattr(jd_parsed, "prompt_tokens", 0) + getattr(match, "prompt_tokens", 0)
        total_completion = getattr(jd_parsed, "completion_tokens", 0) + getattr(match, "completion_tokens", 0)
        with self.session_factory() as session:
            self._accumulate_tokens(session, task.id, total_prompt, total_completion)

        return app
