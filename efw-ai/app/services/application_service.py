"""投递记录服务：列表/详情/状态更新/文案重新生成。"""
import logging
from datetime import datetime

from sqlmodel import Session, select

from app.models import Application, ApplicationEvent, Job, Profile

logger = logging.getLogger(__name__)

# 8 种合法状态（与 Application.status 注释一致）
VALID_STATUSES = frozenset({
    "skip", "pending_manual", "applied", "responded",
    "interview", "offer", "rejected", "withdrawn",
})


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------- 查询 ----------

def list_applications(
    session: Session,
    task_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[Application]:
    """按 task_id / status 过滤投递记录，按 id 倒序返回。"""
    stmt = select(Application)
    if task_id is not None:
        stmt = stmt.where(Application.task_id == task_id)
    if status is not None:
        stmt = stmt.where(Application.status == status)
    stmt = stmt.order_by(Application.id.desc()).limit(limit)
    return session.exec(stmt).all()


def get_application(session: Session, app_id: int) -> Application | None:
    return session.get(Application, app_id)


# ---------- 状态更新 ----------

def update_status(
    session: Session,
    app_id: int,
    new_status: str,
    detail: str = "",
) -> bool:
    """更新投递状态并写 status_changed 事件。

    - new_status 不在 8 种合法状态内 → 返回 False（不写库）
    - application 不存在 → 返回 False
    - 成功 → 更新 status + applied_at（若置为 applied）+ event，返回 True
    """
    if new_status not in VALID_STATUSES:
        logger.warning("update_status: invalid status '%s'", new_status)
        return False

    app = session.get(Application, app_id)
    if app is None:
        return False

    old_status = app.status
    app.status = new_status
    app.updated_at = _now()
    if new_status == "applied" and app.applied_at is None:
        app.applied_at = _now()

    event = ApplicationEvent(
        application_id=app_id,
        event_type="status_changed",
        detail=detail or f"{old_status} -> {new_status}",
    )
    session.add(event)
    session.commit()
    return True


# ---------- 文案重新生成 ----------

async def regenerate_message(
    session: Session,
    app_id: int,
    writer,
) -> list[str]:
    """重读 job + profile，重新调用 writer 生成打招呼文案。

    成功时将第一条候选写回 application.message，并记录 message_regenerated 事件。
    不存在或无 profile 时返回空列表。
    """
    app = session.get(Application, app_id)
    if app is None:
        return []

    job = session.get(Job, app.job_id)
    if job is None:
        logger.warning("regenerate_message: job %s not found", app.job_id)
        return []

    profile = session.exec(select(Profile)).first()
    if profile is None:
        logger.warning("regenerate_message: no profile configured")
        return []

    # 用规则兜底解析 JD（不依赖 LLM，保证服务层可单测）
    from app.agent.jd_parser import parse_by_rules
    jd_parsed = parse_by_rules(job.jd_text or "")

    job_dict = {
        "boss_job_id": job.boss_job_id,
        "title": job.title,
        "company": job.company,
        "salary_text": job.salary_text,
        "city": job.city,
        "jd_text": job.jd_text,
        "job_url": job.job_url,
    }

    msgs = await writer.write(profile, job_dict, jd_parsed)
    if msgs:
        app.message = msgs[0]
        app.updated_at = _now()
        session.add(ApplicationEvent(
            application_id=app_id,
            event_type="message_regenerated",
            detail=f"candidates={len(msgs)}",
        ))
        session.commit()
    return msgs
