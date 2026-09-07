"""任务 API：CRUD + 运行控制（start/pause/resume/stop）+ SSE 事件流。"""
import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from ..db import get_session
from ..models import Task, Application
from ..schemas import TaskIn

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------- 辅助 ----------

def _task_to_dict(t: Task) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "keywords": t.keywords,
        "city": t.city,
        "mode": t.mode,
        "max_deliveries": t.max_deliveries,
        "daily_limit": t.daily_limit,
        "match_threshold": t.match_threshold,
        "rules": t.rules,
        "status": t.status,
        "last_job_id": t.last_job_id,
        "created_at": t.created_at,
        "finished_at": t.finished_at,
    }


def _get_task_or_404(session: Session, task_id: int) -> Task:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


# ---------- CRUD ----------

@router.get("/tasks")
def list_tasks(session: Session = Depends(get_session)) -> dict:
    tasks = session.exec(select(Task).order_by(Task.id.desc())).all()
    return {"tasks": [_task_to_dict(t) for t in tasks]}


@router.post("/tasks")
def create_task(body: TaskIn, session: Session = Depends(get_session)) -> dict:
    task = Task(
        name=body.name,
        keywords=body.keywords,
        city=body.city,
        mode=body.mode,
        max_deliveries=body.max_deliveries,
        daily_limit=body.daily_limit,
        match_threshold=body.match_threshold,
        rules=body.rules,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    return _task_to_dict(task)


@router.get("/tasks/{task_id}")
def get_task(task_id: int, session: Session = Depends(get_session)) -> dict:
    task = _get_task_or_404(session, task_id)
    # 附带该任务的投递统计
    apps = session.exec(
        select(Application).where(Application.task_id == task_id)
    ).all()
    stats = {}
    for a in apps:
        stats[a.decision] = stats.get(a.decision, 0) + 1
    result = _task_to_dict(task)
    result["application_stats"] = stats
    result["application_count"] = len(apps)
    return result


# ---------- 运行控制 ----------

def _check_not_running(app_state, task_id: int) -> None:
    """并发防护：如果任务已有 run_task 循环在运行，拒绝重复启动。"""
    if task_id in app_state.running_tasks:
        raise HTTPException(status_code=409, detail="Task already running")


@router.post("/tasks/{task_id}/start")
async def start_task(task_id: int, request: Request, session: Session = Depends(get_session)) -> dict:
    task = _get_task_or_404(session, task_id)
    if task.status not in ("pending", "paused", "stopped"):
        raise HTTPException(status_code=409, detail=f"Cannot start task in status '{task.status}'")
    ts = request.app.state.task_service
    _check_not_running(request.app.state, task_id)
    ts.start(task_id)
    asyncio.create_task(ts.run_task(task_id))
    return {"ok": True, "status": "running"}


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: int, request: Request, session: Session = Depends(get_session)) -> dict:
    task = _get_task_or_404(session, task_id)
    if task.status != "running":
        raise HTTPException(status_code=409, detail=f"Cannot pause task in status '{task.status}'")
    request.app.state.task_service.pause(task_id)
    return {"ok": True, "status": "paused"}


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: int, request: Request, session: Session = Depends(get_session)) -> dict:
    task = _get_task_or_404(session, task_id)
    if task.status != "paused":
        raise HTTPException(status_code=409, detail=f"Cannot resume task in status '{task.status}'")
    ts = request.app.state.task_service
    _check_not_running(request.app.state, task_id)
    ts.resume(task_id)
    asyncio.create_task(ts.run_task(task_id))
    return {"ok": True, "status": "running"}


@router.post("/tasks/{task_id}/stop")
async def stop_task(task_id: int, request: Request, session: Session = Depends(get_session)) -> dict:
    task = _get_task_or_404(session, task_id)
    if task.status not in ("running", "paused"):
        raise HTTPException(status_code=409, detail=f"Cannot stop task in status '{task.status}'")
    request.app.state.task_service.stop(task_id)
    return {"ok": True, "status": "stopped"}


@router.post("/tasks/{task_id}/resume-after-crash")
async def resume_after_crash(task_id: int, request: Request,
                              session: Session = Depends(get_session)) -> dict:
    """崩溃恢复：仅当状态为 interrupted 时重置为 running 并触发 run_task。"""
    task = _get_task_or_404(session, task_id)
    if task.status != "interrupted":
        raise HTTPException(
            status_code=409,
            detail=f"Task status is '{task.status}', expected 'interrupted'",
        )
    ts = request.app.state.task_service
    _check_not_running(request.app.state, task_id)
    ts.resume_after_crash(task_id)
    asyncio.create_task(ts.run_task(task_id))
    return {"ok": True, "status": "running", "previous_status": task.status}


# ---------- SSE 事件流 ----------

@router.get("/tasks/{task_id}/events")
async def task_events(task_id: int, request: Request):
    """SSE 事件流：订阅该任务的运行进度事件。"""
    broker = request.app.state.sse_broker

    async def event_generator():
        # 先发送一个 connected 事件，确认连接建立
        yield f"data: {json.dumps({'type': 'connected', 'task_id': task_id})}\n\n"
        async for event in broker.subscribe():
            # 只推送该任务的事件
            if event.get("task_id") == task_id:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
