"""投递记录 API：列表/详情/状态更新/文案重生成。"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import Session

from ..db import get_session
from ..models import Job
from ..services.application_service import (
    VALID_STATUSES,
    get_application,
    list_applications,
    regenerate_message,
    update_status,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class StatusUpdate(BaseModel):
    status: str
    detail: str = ""


# ---------- 序列化 ----------

def _app_to_dict(app, session: Session) -> dict:
    d = {
        "id": app.id,
        "job_id": app.job_id,
        "task_id": app.task_id,
        "mode": app.mode,
        "decision": app.decision,
        "match_score": app.match_score,
        "llm_reason": app.llm_reason,
        "message": app.message,
        "status": app.status,
        "applied_at": app.applied_at,
        "updated_at": app.updated_at,
    }
    job = session.get(Job, app.job_id)
    if job is not None:
        d["job_title"] = job.title
        d["company"] = job.company
        d["salary_text"] = job.salary_text
        d["city"] = job.city
        d["job_url"] = job.job_url
    return d


# ---------- 端点 ----------

@router.get("/applications")
def list_apps(
    task_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
    session: Session = Depends(get_session),
) -> dict:
    apps = list_applications(session, task_id=task_id, status=status, limit=limit)
    return {"applications": [_app_to_dict(a, session) for a in apps]}


@router.get("/applications/{app_id}")
def get_app(app_id: int, session: Session = Depends(get_session)) -> dict:
    app = get_application(session, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return _app_to_dict(app, session)


@router.post("/applications/{app_id}/status")
def update_app_status(
    app_id: int,
    body: StatusUpdate,
    session: Session = Depends(get_session),
) -> dict:
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{body.status}'. Must be one of {sorted(VALID_STATUSES)}",
        )
    ok = update_status(session, app_id, body.status, body.detail)
    if not ok:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"ok": True, "status": body.status}


@router.post("/applications/{app_id}/regenerate-message")
async def regenerate_app_message(
    app_id: int,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    app = get_application(session, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    writer = request.app.state.orchestrator.writer
    msgs = await regenerate_message(session, app_id, writer)
    return {"messages": msgs}
