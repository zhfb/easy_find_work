"""投递记录 API 测试：列表/详情/状态更新/文案重生成 + 半自动清单页 + 自动投递。"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlmodel import Session, select

from app.models import Task, Job, Application, ApplicationEvent, Profile
from app.state import AppState


# ---------- 辅助 ----------

def _seed(client, *, mode="auto", decision="deliver", status="pending_manual",
          message="你好，我对这个岗位感兴趣", title="测试工程师", company="字节跳动",
          jd_text="岗位职责：负责云原生平台开发。要求：熟悉 Linux、K8s、Docker。"):
    """创建 task + job + application，返回各 id。"""
    from app import db as db_module
    with Session(db_module.engine) as s:
        task = Task(name="投递任务", mode=mode, daily_limit=20)
        s.add(task)
        s.flush()
        job = Job(boss_job_id=f"boss_{task.id}", title=title, company=company,
                  salary_text="20-35K", city="武汉", jd_text=jd_text,
                  job_url=f"https://www.zhipin.com/job_detail/{task.id}.html")
        s.add(job)
        s.flush()
        app = Application(job_id=job.id, task_id=task.id, mode=mode,
                          decision=decision, match_score=8.5, llm_reason="匹配度高",
                          message=message, status=status)
        s.add(app)
        s.commit()
        s.refresh(app)
        return {"task_id": task.id, "job_id": job.id, "app_id": app.id}


def _ensure_profile(client):
    from app import db as db_module
    with Session(db_module.engine) as s:
        if s.exec(select(Profile)).first() is None:
            s.add(Profile(skills="linux,k8s,docker", experience_years=3,
                          resume_summary="云原生工程师"))
            s.commit()


# ---------- GET /api/applications ----------

def test_list_applications(client):
    _seed(client)
    r = client.get("/api/applications")
    assert r.status_code == 200
    data = r.json()
    assert "applications" in data
    assert len(data["applications"]) >= 1
    first = data["applications"][0]
    assert "id" in first
    assert "job_title" in first
    assert "company" in first


def test_list_applications_filter_by_task(client):
    info = _seed(client)
    r = client.get(f"/api/applications?task_id={info['task_id']}")
    assert r.status_code == 200
    for a in r.json()["applications"]:
        assert a["task_id"] == info["task_id"]


def test_list_applications_filter_by_status(client):
    _seed(client, status="pending_manual")
    _seed(client, status="applied")
    r = client.get("/api/applications?status=pending_manual")
    assert r.status_code == 200
    for a in r.json()["applications"]:
        assert a["status"] == "pending_manual"


def test_list_applications_empty(client):
    r = client.get("/api/applications?status=nonexistent_filter")
    assert r.status_code == 200
    assert r.json()["applications"] == []


# ---------- GET /api/applications/{id} ----------

def test_get_application(client):
    info = _seed(client)
    r = client.get(f"/api/applications/{info['app_id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == info["app_id"]
    assert data["job_title"] == "测试工程师"
    assert data["company"] == "字节跳动"
    assert data["message"] == "你好，我对这个岗位感兴趣"
    assert data["status"] == "pending_manual"


def test_get_application_not_found(client):
    r = client.get("/api/applications/99999")
    assert r.status_code == 404


# ---------- POST /api/applications/{id}/status ----------

def test_update_status_valid_and_event(client):
    info = _seed(client, status="pending_manual")
    r = client.post(f"/api/applications/{info['app_id']}/status",
                    json={"status": "applied"})
    assert r.status_code == 200
    assert r.json()["status"] == "applied"
    # 校验 event 落库
    from app import db as db_module
    with Session(db_module.engine) as s:
        events = s.exec(
            select(ApplicationEvent).where(ApplicationEvent.application_id == info["app_id"])
        ).all()
        assert any(e.event_type == "status_changed" for e in events)
        # 校验状态已更新
        app = s.get(Application, info["app_id"])
        assert app.status == "applied"
        assert app.applied_at is not None


def test_update_status_all_valid_statuses(client):
    info = _seed(client)
    for st in ("skip", "pending_manual", "applied", "responded",
               "interview", "offer", "rejected", "withdrawn"):
        r = client.post(f"/api/applications/{info['app_id']}/status",
                        json={"status": st})
        assert r.status_code == 200, f"status {st} should be valid"


def test_update_status_invalid_rejected(client):
    info = _seed(client)
    r = client.post(f"/api/applications/{info['app_id']}/status",
                    json={"status": "hacked"})
    assert r.status_code == 400


def test_update_status_not_found(client):
    r = client.post("/api/applications/99999/status", json={"status": "applied"})
    assert r.status_code == 404


def test_update_status_with_detail(client):
    info = _seed(client)
    r = client.post(f"/api/applications/{info['app_id']}/status",
                    json={"status": "rejected", "detail": "HR 反馈不匹配"})
    assert r.status_code == 200
    from app import db as db_module
    with Session(db_module.engine) as s:
        events = s.exec(
            select(ApplicationEvent).where(
                ApplicationEvent.application_id == info["app_id"],
                ApplicationEvent.event_type == "status_changed",
            )
        ).all()
        assert any("HR 反馈不匹配" in e.detail for e in events)


# ---------- POST /api/applications/{id}/regenerate-message ----------

def test_regenerate_message(client):
    _ensure_profile(client)
    info = _seed(client)
    r = client.post(f"/api/applications/{info['app_id']}/regenerate-message")
    assert r.status_code == 200
    data = r.json()
    assert "messages" in data
    assert isinstance(data["messages"], list)
    assert len(data["messages"]) > 0
    # 第一条应已写回 application.message
    from app import db as db_module
    with Session(db_module.engine) as s:
        app = s.get(Application, info["app_id"])
        assert app.message == data["messages"][0]


def test_regenerate_message_not_found(client):
    r = client.post("/api/applications/99999/regenerate-message")
    assert r.status_code == 404


# ---------- GET /semi-queue 页面 ----------

def test_semi_queue_page_lists_pending_manual(client):
    _seed(client, status="pending_manual", title="待手动投递岗位", company="手动公司")
    r = client.get("/semi-queue")
    assert r.status_code == 200
    assert "待手动投递岗位" in r.text
    assert "手动公司" in r.text


def test_semi_queue_page_excludes_applied(client):
    _seed(client, status="applied", title="已投递岗位", company="已投公司")
    r = client.get("/semi-queue")
    assert r.status_code == 200
    assert "已投递岗位" not in r.text


def test_semi_queue_page_empty(client):
    r = client.get("/semi-queue")
    assert r.status_code == 200
    assert "半自动" in r.text or "待投递" in r.text or "暂无" in r.text


# ---------- TaskService 自动投递单元测试 ----------

class _FakeBrowserManager:
    """模拟 BrowserManager，get_page 返回 mock page。"""
    def __init__(self, page=None):
        self._page = page or MagicMock()

    def get_page(self):
        return self._page


class _FakeBossClient:
    """模拟 BossClient，send_greeting 可配置成功/失败。"""
    def __init__(self, should_fail=False, fail_count=0):
        self.calls = []
        self._should_fail = should_fail
        self._fail_count = fail_count
        self._attempt = 0

    async def send_greeting(self, page, job_id, message):
        self.calls.append({"job_id": job_id, "message": message})
        self._attempt += 1
        if self._should_fail and self._attempt <= self._fail_count:
            raise RuntimeError("simulated delivery failure")


def _make_task_service(orchestrator=None, browser_manager=None, boss_client=None):
    """构造注入了 fake 依赖的 TaskService。"""
    from app.services.task_service import TaskService
    from app import db as db_module

    state = AppState()
    ts = TaskService(
        orchestrator=orchestrator or MagicMock(),
        session_factory=lambda: Session(db_module.engine),
        app_state=state,
        browser_manager=browser_manager,
        boss_client=boss_client,
    )
    return ts, state


def test_auto_mode_deliver_calls_send_greeting(client):
    """auto + deliver → 调用 send_greeting，成功后写 delivered event。"""
    from app import db as db_module
    info = _seed(client, mode="auto", decision="deliver", status="applied")

    boss = _FakeBossClient()
    browser = _FakeBrowserManager()

    # 直接测试 _do_delivery
    ts, _ = _make_task_service(browser_manager=browser, boss_client=boss)
    with Session(db_module.engine) as s:
        app = s.get(Application, info["app_id"])
        job = s.get(Job, info["job_id"])
        job_dict = {"boss_job_id": job.boss_job_id, "title": job.title}

    asyncio.run(ts._do_delivery(app, job_dict))

    assert len(boss.calls) == 1
    assert boss.calls[0]["job_id"] == f"boss_{info['task_id']}"
    assert boss.calls[0]["message"] == "你好，我对这个岗位感兴趣"
    # 校验 delivered event
    with Session(db_module.engine) as s:
        events = s.exec(
            select(ApplicationEvent).where(ApplicationEvent.application_id == info["app_id"])
        ).all()
        assert any(e.event_type == "delivered" for e in events)


def test_auto_mode_deliver_failure_retries_once(client):
    """send_greeting 失败 → 记 deliver_failed，重试 1 次。"""
    from app import db as db_module
    info = _seed(client, mode="auto", decision="deliver", status="applied")

    boss = _FakeBossClient(should_fail=True, fail_count=1)  # 第一次失败，第二次成功
    browser = _FakeBrowserManager()

    ts, _ = _make_task_service(browser_manager=browser, boss_client=boss)
    with Session(db_module.engine) as s:
        app = s.get(Application, info["app_id"])
        job = s.get(Job, info["job_id"])
        job_dict = {"boss_job_id": job.boss_job_id}

    asyncio.run(ts._do_delivery(app, job_dict))

    assert len(boss.calls) == 2  # 重试了 1 次
    with Session(db_module.engine) as s:
        events = s.exec(
            select(ApplicationEvent).where(ApplicationEvent.application_id == info["app_id"])
        ).all()
        event_types = [e.event_type for e in events]
        assert "deliver_failed" in event_types
        assert "delivered" in event_types


def test_auto_mode_deliver_both_fail(client):
    """两次都失败 → 两条 deliver_failed，不崩溃。"""
    from app import db as db_module
    info = _seed(client, mode="auto", decision="deliver", status="applied")

    boss = _FakeBossClient(should_fail=True, fail_count=99)  # 永远失败
    browser = _FakeBrowserManager()

    ts, _ = _make_task_service(browser_manager=browser, boss_client=boss)
    with Session(db_module.engine) as s:
        app = s.get(Application, info["app_id"])
        job = s.get(Job, info["job_id"])
        job_dict = {"boss_job_id": job.boss_job_id}

    asyncio.run(ts._do_delivery(app, job_dict))

    assert len(boss.calls) == 2
    with Session(db_module.engine) as s:
        events = s.exec(
            select(ApplicationEvent).where(ApplicationEvent.application_id == info["app_id"])
        ).all()
        event_types = [e.event_type for e in events]
        assert event_types.count("deliver_failed") == 2
        assert "delivered" not in event_types


def test_semi_mode_run_task_skips_delivery(client):
    """semi 模式任务运行 run_task 时，deliver 决策不调用 send_greeting。"""
    from app import db as db_module
    from app.services.task_service import TaskService
    from app.state import AppState
    from types import SimpleNamespace

    # Seed: profile（run_task 必需）+ semi 任务 + 一个岗位
    with Session(db_module.engine) as s:
        s.add(Profile(skills="linux,k8s", experience_years=3))
        task = Task(name="半自动任务", mode="semi", daily_limit=20)
        s.add(task)
        s.flush()
        job = Job(boss_job_id=f"boss_semi_{task.id}", title="半岗", company="半司")
        s.add(job)
        s.commit()
        task_id = task.id

    # Mock orchestrator：process_job 返回 deliver 决策的 Application
    fake_app = SimpleNamespace(
        id=1, decision="deliver", match_score=8.0,
        mode="semi", status="pending_manual", message="hello",
    )
    orchestrator = MagicMock()
    orchestrator.process_job = AsyncMock(return_value=fake_app)

    boss = _FakeBossClient()
    browser = _FakeBrowserManager()
    state = AppState()
    ts = TaskService(
        orchestrator=orchestrator,
        session_factory=lambda: Session(db_module.engine),
        app_state=state,
        browser_manager=browser,
        boss_client=boss,
    )

    asyncio.run(ts.run_task(task_id))

    # 核心断言：semi 模式下 deliver 决策不调用投递
    assert boss.calls == [], "semi 模式不应调用 send_greeting"
    assert orchestrator.process_job.called, "process_job 应被调用"
    # 任务应正常结束（处理完唯一岗位后 finished）
    with Session(db_module.engine) as s:
        t = s.get(Task, task_id)
        assert t.status == "finished"


def test_no_browser_skips_delivery(client):
    """browser_manager 为 None 时跳过投递，不崩溃。"""
    from app import db as db_module
    info = _seed(client, mode="auto", decision="deliver", status="applied")

    boss = _FakeBossClient()
    ts, _ = _make_task_service(browser_manager=None, boss_client=boss)
    with Session(db_module.engine) as s:
        app = s.get(Application, info["app_id"])
        job_dict = {"boss_job_id": "boss_x"}

    asyncio.run(ts._do_delivery(app, job_dict))
    assert len(boss.calls) == 0  # 未调用


def test_browser_get_page_failure_skips_delivery(client):
    """get_page 抛异常时跳过投递，不崩溃。"""
    from app import db as db_module
    info = _seed(client, mode="auto", decision="deliver", status="applied")

    class _BrokenBrowser:
        def get_page(self):
            raise RuntimeError("browser not started")

    boss = _FakeBossClient()
    ts, _ = _make_task_service(browser_manager=_BrokenBrowser(), boss_client=boss)
    with Session(db_module.engine) as s:
        app = s.get(Application, info["app_id"])
        job_dict = {"boss_job_id": "boss_x"}

    asyncio.run(ts._do_delivery(app, job_dict))
    assert len(boss.calls) == 0
