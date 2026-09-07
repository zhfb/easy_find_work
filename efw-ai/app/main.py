import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .db import init_db, get_session
from . import db
from .api import config as config_api, profile as profile_api, tasks as tasks_api, applications as applications_api, chat as chat_api, dashboard as dashboard_api
from .services.stats_service import get_today_stats
from .services.application_service import list_applications
from .services.chat_service import ChatService
from .services.config_service import get_config, get_bool
from .state import AppState
from .models import Task, Application, ApplicationEvent, Job, ConfigItem

# Agent 组件
from .agent.prefilter import PreFilter
from .agent.jd_parser import JdParser
from .agent.matcher import Matcher
from .agent.decider import Decider
from .agent.writer import Writer
from .agent.llm import LlmClient
from .agent.orchestrator import Orchestrator
from .agent.followup import FollowUpAnalyzer
from .services.task_service import TaskService
from .services.followup_service import FollowupService
from .services.risk_controller import RiskController
from .worker.boss_client import BossClient

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _build_llm() -> LlmClient:
    """从 config 表读取 LLM 配置，构造 LlmClient（无配置时返回不可用实例，Agent 自动回退规则）。"""
    from .services.config_service import get_config
    with Session(db.engine) as session:
        base_url = get_config(session, "base_url") or ""
        api_key = get_config(session, "api_key") or ""
        model = get_config(session, "model") or ""
    return LlmClient(base_url=base_url, api_key=api_key, model=model)


def _build_orchestrator() -> Orchestrator:
    llm = _build_llm()
    return Orchestrator(
        prefilter=PreFilter(),
        jd_parser=JdParser(llm),
        matcher=Matcher(llm),
        decider=Decider(),
        writer=Writer(llm),
        session_factory=lambda: Session(db.engine),
    )


def _build_followup_service() -> FollowupService:
    """构造跟进服务（骨架阶段浏览器 page 为 None，run_once 会自动跳过）。"""
    llm = _build_llm()
    analyzer = FollowUpAnalyzer(llm=llm)
    boss_client = BossClient()
    risk = RiskController(session=None)  # 骨架阶段无浏览器会话
    return FollowupService(
        analyzer=analyzer,
        boss_client=boss_client,
        risk=risk,
        session_factory=lambda: Session(db.engine),
        page=None,
    )


def _get_follow_up_minutes() -> int:
    """从 config 表读取跟进间隔（分钟），默认 10 分钟。"""
    from .services.config_service import get_config
    with Session(db.engine) as session:
        raw = get_config(session, "follow_up_minutes")
    try:
        val = int(raw) if raw is not None else 10
        return max(1, val)  # 最小 1 分钟，避免配置错误导致忙等
    except (ValueError, TypeError):
        return 10


def _mark_running_as_interrupted() -> int:
    """启动时将所有 status="running" 的任务置为 "interrupted"，返回处理数量。

    崩溃续跑：进程异常退出后任务状态残留为 running，重启时统一标记为 interrupted，
    后续可通过 POST /api/tasks/{id}/resume-after-crash 从 last_job_id 续跑。
    """
    count = 0
    with Session(db.engine) as session:
        running = session.exec(select(Task).where(Task.status == "running")).all()
        for t in running:
            t.status = "interrupted"
            count += 1
        if count:
            session.commit()
    if count:
        logger.warning("崩溃恢复：检测到 %d 个 running 任务，已置为 interrupted", count)
    return count


async def _followup_loop(service: FollowupService) -> None:
    """后台跟进循环：每隔 follow_up_minutes 执行一次 run_once。"""
    while True:
        try:
            count = await service.run_once()
            if count:
                logger.info("跟进循环完成，本次推进 %d 条申请", count)
        except asyncio.CancelledError:
            logger.info("跟进循环已取消")
            raise
        except Exception as e:
            logger.exception("跟进循环异常: %s", e)
        interval = _get_follow_up_minutes() * 60
        await asyncio.sleep(interval)


def _compute_cost_stats(session: Session) -> dict:
    """汇总所有 ai_tokens_{task_id} 的 token 用量并按 price_per_1k 估算成本。"""
    total_prompt = 0
    total_completion = 0
    per_task = []
    items = session.exec(
        select(ConfigItem).where(ConfigItem.key.like("ai_tokens_%"))
    ).all()
    for item in items:
        try:
            data = json.loads(item.value) if item.value else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        pt = data.get("prompt_tokens", 0)
        ct = data.get("completion_tokens", 0)
        total_prompt += pt
        total_completion += ct
        # 从 key 中提取 task_id
        try:
            tid = int(item.key.replace("ai_tokens_", ""))
        except ValueError:
            tid = None
        per_task.append({"task_id": tid, "prompt_tokens": pt, "completion_tokens": ct})

    total_tokens = total_prompt + total_completion
    price_raw = get_config(session, "price_per_1k")
    try:
        price_per_1k = float(price_raw) if price_raw is not None else 0.0
    except (ValueError, TypeError):
        price_per_1k = 0.0
    estimated_cost = round(total_tokens / 1000 * price_per_1k, 6)

    return {
        "total_prompt_tokens": total_prompt,
        "total_completion_tokens": total_completion,
        "total_tokens": total_tokens,
        "price_per_1k": price_per_1k,
        "estimated_cost": estimated_cost,
        "per_task": per_task,
    }


def _get_task_application_counts(session: Session, task_ids: list[int]) -> dict[int, dict]:
    """批量查询每个任务的 application 数量与状态分布。"""
    result = {tid: {"total": 0, "deliver": 0, "skip": 0, "pending": 0} for tid in task_ids}
    if not task_ids:
        return result
    apps = session.exec(
        select(Application).where(Application.task_id.in_(task_ids))
    ).all()
    for a in apps:
        d = result.get(a.task_id)
        if d is not None:
            d["total"] += 1
            if a.decision in d:
                d[a.decision] += 1
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 崩溃恢复：将残留 running 任务置为 interrupted（在启动跟进循环之前）
    _mark_running_as_interrupted()
    # 初始化应用状态
    app_state = AppState()
    app.state.sse_broker = app_state.sse_broker
    app.state.task_flags = app_state.task_flags
    app.state.running_tasks = app_state.running_tasks
    # 构造 Orchestrator + TaskService
    orchestrator = _build_orchestrator()
    app.state.orchestrator = orchestrator
    app.state.task_service = TaskService(
        orchestrator=orchestrator,
        session_factory=lambda: Session(db.engine),
        app_state=app_state,
    )
    # 构造对话式助手
    chat_llm = _build_llm()
    app.state.chat_service = ChatService(
        llm=chat_llm,
        task_service=app.state.task_service,
        session_factory=lambda: Session(db.engine),
        app_state=app_state,
    )
    # 构造跟进服务并启动后台循环
    followup_service = _build_followup_service()
    app.state.followup_service = followup_service
    followup_task = asyncio.create_task(_followup_loop(followup_service))
    app.state.followup_task = followup_task
    try:
        yield
    finally:
        followup_task.cancel()
        try:
            await followup_task
        except (asyncio.CancelledError, Exception):
            pass


app = FastAPI(lifespan=lifespan)
app.include_router(config_api.router, prefix="/api")
app.include_router(profile_api.router, prefix="/api")
app.include_router(tasks_api.router, prefix="/api")
app.include_router(applications_api.router, prefix="/api")
app.include_router(chat_api.router, prefix="/api")
app.include_router(dashboard_api.router, prefix="/api")


# ---------- 健康检查 ----------

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------- 页面 ----------

@app.get("/")
def dashboard(request: Request, session: Session = Depends(get_session)):
    stats = get_today_stats(session)
    total = sum(stats.values())
    today = date.today().isoformat()
    # 任务列表
    tasks = session.exec(select(Task).order_by(Task.id.desc())).all()
    task_ids = [t.id for t in tasks if t.id is not None]
    app_counts = _get_task_application_counts(session, task_ids)
    task_list = []
    for t in tasks:
        ac = app_counts.get(t.id, {"total": 0, "deliver": 0, "skip": 0, "pending": 0})
        task_list.append({
            "id": t.id,
            "name": t.name,
            "status": t.status,
            "mode": t.mode,
            "last_job_id": t.last_job_id,
            "created_at": t.created_at,
            "app_total": ac["total"],
            "app_deliver": ac["deliver"],
            "app_skip": ac["skip"],
        })
    # 成本统计
    cost = _compute_cost_stats(session)
    # chat_enabled
    chat_enabled = get_bool(session, "chat_enabled", default=True)
    return templates.TemplateResponse(
        request, "dashboard.html",
        {
            "stats": stats, "total": total, "today": today,
            "tasks": task_list, "cost": cost, "chat_enabled": chat_enabled,
        },
    )


@app.get("/tasks/{task_id}")
def task_detail(task_id: int, request: Request, session: Session = Depends(get_session)):
    """任务详情页：SSE 进度流 + 岗位评估列表 + 控制按钮。"""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    apps = session.exec(
        select(Application).where(Application.task_id == task_id)
        .order_by(Application.id.desc()).limit(100)
    ).all()
    # 批量查 Job
    job_ids = {a.job_id for a in apps}
    jobs = {}
    if job_ids:
        for j in session.exec(select(Job).where(Job.id.in_(job_ids))).all():
            jobs[j.id] = j
    enriched = []
    for a in apps:
        job = jobs.get(a.job_id)
        enriched.append({
            "id": a.id,
            "job_title": job.title if job else "",
            "company": job.company if job else "",
            "salary_text": job.salary_text if job else "",
            "decision": a.decision,
            "match_score": a.match_score,
            "status": a.status,
            "llm_reason": a.llm_reason,
            "message": a.message,
        })
    chat_enabled = get_bool(session, "chat_enabled", default=True)
    return templates.TemplateResponse(
        request, "task_detail.html",
        {"task": task, "applications": enriched, "chat_enabled": chat_enabled},
    )


@app.get("/applications")
def applications_page(
    request: Request,
    status: str | None = None,
    task_id: int | None = None,
    session: Session = Depends(get_session),
):
    """投递记录列表页：筛选（状态/任务）+ 状态分布。"""
    apps = list_applications(session, task_id=task_id, status=status, limit=200)
    job_ids = {a.job_id for a in apps}
    jobs = {}
    if job_ids:
        for j in session.exec(select(Job).where(Job.id.in_(job_ids))).all():
            jobs[j.id] = j
    enriched = []
    for a in apps:
        job = jobs.get(a.job_id)
        enriched.append({
            "id": a.id,
            "job_title": job.title if job else "",
            "company": job.company if job else "",
            "salary_text": job.salary_text if job else "",
            "city": job.city if job else "",
            "decision": a.decision,
            "match_score": a.match_score,
            "status": a.status,
            "applied_at": a.applied_at,
            "task_id": a.task_id,
        })
    # 状态分布
    all_apps = session.exec(select(Application)).all()
    status_dist = {}
    for a in all_apps:
        status_dist[a.status] = status_dist.get(a.status, 0) + 1
    # 任务列表（筛选下拉）
    tasks = session.exec(select(Task).order_by(Task.id.desc())).all()
    chat_enabled = get_bool(session, "chat_enabled", default=True)
    return templates.TemplateResponse(
        request, "applications.html",
        {
            "applications": enriched,
            "status_dist": status_dist,
            "tasks": tasks,
            "current_status": status or "",
            "current_task": task_id,
            "chat_enabled": chat_enabled,
        },
    )


@app.get("/applications/{app_id}")
def application_detail(app_id: int, request: Request, session: Session = Depends(get_session)):
    """投递详情页：llm_reason、文案、事件时间线、状态推进。"""
    app = session.get(Application, app_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    job = session.get(Job, app.job_id)
    events = session.exec(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == app_id)
        .order_by(ApplicationEvent.id)
    ).all()
    task = session.get(Task, app.task_id)
    chat_enabled = get_bool(session, "chat_enabled", default=True)
    return templates.TemplateResponse(
        request, "application_detail.html",
        {
            "app": app,
            "job": job,
            "events": events,
            "task": task,
            "chat_enabled": chat_enabled,
        },
    )


@app.get("/semi-queue")
def semi_queue(request: Request, session: Session = Depends(get_session)):
    """半自动投递清单页：渲染 status=pending_manual 的 application 列表。"""
    apps = list_applications(session, status="pending_manual", limit=200)
    # 批量查询关联 Job，避免 N+1
    job_ids = {a.job_id for a in apps}
    jobs = {}
    if job_ids:
        for j in session.exec(select(Job).where(Job.id.in_(job_ids))).all():
            jobs[j.id] = j
    enriched = []
    for a in apps:
        job = jobs.get(a.job_id)
        enriched.append({
            "id": a.id,
            "job_title": job.title if job else "",
            "company": job.company if job else "",
            "salary_text": job.salary_text if job else "",
            "city": job.city if job else "",
            "match_score": a.match_score,
            "message": a.message,
            "job_url": job.job_url if job else "",
        })
    chat_enabled = get_bool(session, "chat_enabled", default=True)
    return templates.TemplateResponse(
        request, "semi_queue.html",
        {"applications": enriched, "chat_enabled": chat_enabled},
    )


@app.get("/chat")
def chat_page(request: Request, session: Session = Depends(get_session)):
    """对话式助手页面。"""
    chat_enabled = get_bool(session, "chat_enabled", default=True)
    return templates.TemplateResponse(request, "chat.html", {"chat_enabled": chat_enabled})


@app.get("/config")
def config_page(request: Request, session: Session = Depends(get_session)):
    """配置页面。"""
    from .services.config_service import get_all_config
    config = get_all_config(session)
    chat_enabled = get_bool(session, "chat_enabled", default=True)
    return templates.TemplateResponse(
        request, "config.html",
        {"config": config, "chat_enabled": chat_enabled},
    )
