from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .db import init_db, get_session
from . import db
from .api import config as config_api, profile as profile_api, tasks as tasks_api, applications as applications_api
from .services.stats_service import get_today_stats
from .services.application_service import list_applications
from .state import AppState

# Agent 组件
from .agent.prefilter import PreFilter
from .agent.jd_parser import JdParser
from .agent.matcher import Matcher
from .agent.decider import Decider
from .agent.writer import Writer
from .agent.llm import LlmClient
from .agent.orchestrator import Orchestrator
from .services.task_service import TaskService

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(config_api.router, prefix="/api")
app.include_router(profile_api.router, prefix="/api")
app.include_router(tasks_api.router, prefix="/api")
app.include_router(applications_api.router, prefix="/api")


@app.get("/")
def dashboard(request: Request, session: Session = Depends(get_session)):
    stats = get_today_stats(session)
    total = sum(stats.values())
    today = date.today().isoformat()
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"stats": stats, "total": total, "today": today},
    )


@app.get("/semi-queue")
def semi_queue(request: Request, session: Session = Depends(get_session)):
    """半自动投递清单页：渲染 status=pending_manual 的 application 列表。"""
    from .models import Job
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
    return templates.TemplateResponse(
        request, "semi_queue.html",
        {"applications": enriched},
    )
