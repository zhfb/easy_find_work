import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlmodel import Session, select

from .db import init_db
from . import db
from .api import config as config_api, profile as profile_api, tasks as tasks_api, applications as applications_api, chat as chat_api, dashboard as dashboard_api, auth as auth_api
from .services.browser_session import BrowserSessionManager
from .services.chat_service import ChatService
from .services.config_service import get_config
from .state import AppState
from .models import Task

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

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


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
    # 初始化浏览器登录会话管理器
    app.state.browser_session = BrowserSessionManager()
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
        await app.state.browser_session.shutdown()


app = FastAPI(lifespan=lifespan)
app.include_router(config_api.router, prefix="/api")
app.include_router(profile_api.router, prefix="/api")
app.include_router(tasks_api.router, prefix="/api")
app.include_router(applications_api.router, prefix="/api")
app.include_router(chat_api.router, prefix="/api")
app.include_router(dashboard_api.router, prefix="/api")
app.include_router(auth_api.router, prefix="/api")


# ---------- 健康检查 ----------

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------- 静态托管 + SPA fallback ----------

@app.get("/{path:path}")
def spa_fallback(path: str):
    """SPA fallback：非 /api/ 路径统一返回 index.html；带扩展名的静态文件缺失返回 404。"""
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    dist = Path(FRONTEND_DIST)

    # 带文件扩展名的路径：尝试从 dist 托管静态文件，缺失则 404
    if "." in Path(path).name:
        dist_resolved = dist.resolve()
        static_file = (dist / path).resolve()
        try:
            static_file.relative_to(dist_resolved)
        except ValueError:
            raise HTTPException(status_code=404, detail="Not found")
        if static_file.is_file():
            return FileResponse(static_file)
        raise HTTPException(status_code=404, detail="Not found")

    # SPA 路由：返回 index.html，由前端 router 处理
    index = dist / "index.html"
    if not index.exists():
        return JSONResponse(
            status_code=503,
            content={"detail": "前端未构建，请先运行: cd efw-ai/frontend && npm install && npm run build"},
        )
    return FileResponse(index)
