"""任务服务：驱动 Orchestrator 循环处理岗位，管理运行状态与 SSE 事件广播。"""
import asyncio
import logging
from datetime import date, datetime

from sqlmodel import Session, select

from app.models import Task, Job, Application, Profile, Blacklist
from app.services.profile_service import get_profile

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class TaskService:
    """任务运行服务。

    职责：
      - run_task: 按 last_job_id 游标循环读取 Job → process_job → 更新游标
      - start/pause/resume/stop: 更新 task.status 与 app.state.task_flags
      - 通过 SseBroker 广播进度事件
    """

    def __init__(self, orchestrator, session_factory, app_state):
        self.orchestrator = orchestrator
        self.session_factory = session_factory
        if app_state is None:
            raise RuntimeError("TaskService requires app_state to be injected")
        self._state = app_state

    # ---------- 状态控制 ----------

    def _update_status(self, task_id: int, status: str, flag: str | None = None) -> None:
        with self.session_factory() as session:
            task = session.get(Task, task_id)
            if task is not None:
                task.status = status
                if status == "finished":
                    task.finished_at = _now()
                session.commit()
        if flag is not None:
            self._state.task_flags[task_id] = flag

    def start(self, task_id: int) -> None:
        self._update_status(task_id, "running", "running")

    def pause(self, task_id: int) -> None:
        self._update_status(task_id, "paused", "pause")

    def resume(self, task_id: int) -> None:
        self._update_status(task_id, "running", "running")

    def stop(self, task_id: int) -> None:
        self._update_status(task_id, "stopped", "stop")

    def resume_after_crash(self, task_id: int) -> None:
        """崩溃恢复：interrupted → running，并重置 flag。"""
        self._update_status(task_id, "running", "running")

    # ---------- 主循环 ----------

    async def run_task(self, task_id: int) -> None:
        """循环处理岗位，直到无更多岗位、暂停、停止或出错。"""
        state = self._state
        processed = 0

        # 并发防护：标记任务正在运行，退出时（无论正常或异常）移除
        state.running_tasks.add(task_id)
        try:
            while True:
                # 1. 检查暂停/停止标志
                flag = state.task_flags.get(task_id)
                if flag == "pause":
                    state.sse_broker.publish({
                        "type": "paused", "task_id": task_id,
                        "message": "任务已暂停", "current": processed, "total": 0,
                    })
                    return
                if flag == "stop":
                    state.sse_broker.publish({
                        "type": "stopped", "task_id": task_id,
                        "message": "任务已停止", "current": processed, "total": 0,
                    })
                    return

                # 2. 读取任务 + profile + blacklist + daily_used
                with self.session_factory() as session:
                    task = session.get(Task, task_id)
                    if task is None:
                        logger.error("Task %s not found", task_id)
                        return

                    profile = get_profile(session)
                    if profile is None:
                        logger.warning("No profile configured, stopping task %s", task_id)
                        self._update_status(task_id, "failed")
                        state.sse_broker.publish({
                            "type": "error", "task_id": task_id,
                            "message": "未配置个人档案", "current": processed, "total": 0,
                        })
                        return

                    blacklist_companies = {
                        b.value for b in session.exec(
                            select(Blacklist).where(Blacklist.type == "company")
                        ).all()
                    }

                    today = date.today().isoformat()
                    daily_used = len(session.exec(
                        select(Application).where(
                            Application.task_id == task_id,
                            Application.decision == "deliver",
                            Application.applied_at >= today,
                        )
                    ).all())

                    # 日配额检查：达到上限时直接暂停，避免对剩余岗位浪费 LLM 调用
                    if daily_used >= task.daily_limit:
                        self._update_status(task_id, "paused", "pause")
                        state.sse_broker.publish({
                            "type": "daily_limit_reached", "task_id": task_id,
                            "message": f"今日投递已达上限 {task.daily_limit}，任务暂停",
                            "current": processed, "total": 0,
                        })
                        return

                    # 3. 按游标读取下一个岗位
                    last_id = task.last_job_id or 0
                    job = session.exec(
                        select(Job).where(Job.id > last_id).order_by(Job.id).limit(1)
                    ).first()

                    if job is None:
                        self._update_status(task_id, "finished")
                        state.sse_broker.publish({
                            "type": "finished", "task_id": task_id,
                            "message": "所有岗位处理完毕", "current": processed, "total": 0,
                        })
                        return

                    job_dict = {
                        "boss_job_id": job.boss_job_id,
                        "title": job.title,
                        "company": job.company,
                        "company_scale": job.company_scale,
                        "financing_stage": job.financing_stage,
                        "industry": job.industry,
                        "salary_text": job.salary_text,
                        "salary_min": job.salary_min,
                        "salary_max": job.salary_max,
                        "experience_req": job.experience_req,
                        "education_req": job.education_req,
                        "city": job.city,
                        "jd_text": job.jd_text,
                        "job_url": job.job_url,
                    }
                    job_id = job.id
                    job_title = job.title

                # 4. 处理岗位（在 session 外执行，避免长事务阻塞）
                app = await self.orchestrator.process_job(
                    task, job_dict, profile, blacklist_companies, daily_used,
                )

                # 5. 更新游标
                with self.session_factory() as session:
                    t = session.get(Task, task_id)
                    if t is not None:
                        t.last_job_id = job_id
                        session.commit()

                processed += 1

                # 6. 广播 SSE 进度
                state.sse_broker.publish({
                    "type": "job_processed", "task_id": task_id,
                    "message": f"[{app.decision}] {job_title} (score={app.match_score})",
                    "current": processed, "total": 0,
                })

                # 7. 让出事件循环，避免阻塞
                await asyncio.sleep(0)

        except Exception as e:
            logger.exception("Task %s run failed: %s", task_id, e)
            self._update_status(task_id, "failed")
            state.sse_broker.publish({
                "type": "error", "task_id": task_id,
                "message": f"运行出错: {e}", "current": processed, "total": 0,
            })
        finally:
            state.running_tasks.discard(task_id)
