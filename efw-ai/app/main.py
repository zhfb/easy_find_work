import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .db import init_db, get_session
from . import db
from .api import config as config_api, profile as profile_api, tasks as tasks_api, applications as applications_api, chat as chat_api
from .services.stats_service import get_today_stats
from .services.application_service import list_applications
from .services.chat_service import ChatService
from .state import AppState

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


@app.get("/chat")
def chat_page(request: Request):
    """对话式助手页面。"""
    return templates.TemplateResponse(request, "chat.html", {})
