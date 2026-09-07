"""崩溃续跑 + 端到端冒烟测试。

覆盖：
  1. lifespan 启动时将 status="running" 的任务置为 "interrupted"
  2. resume-after-crash 端点将 interrupted 置回 running
  3. 端到端冒烟：app 启动、创建任务、dashboard 加载、API 端点响应
  4. 成本统计：ai_tokens_{task_id} 累加 + price_per_1k 估算
"""
import json
import time

import pytest
from sqlmodel import Session, select

from app.models import Task, ConfigItem, Profile


# ---------- 辅助 ----------

def _create_running_task(engine, name="崩溃任务") -> int:
    """直接在 DB 中插入一个 status=running 的任务（绕过 API）。"""
    with Session(engine) as s:
        t = Task(name=name, status="running", last_job_id=5)
        s.add(t)
        s.commit()
        s.refresh(t)
        return t.id


# ---------- 崩溃恢复 ----------

def _make_client_with_running_task(tmp_path, monkeypatch):
    """构造一个在 lifespan 启动前就已存在 running 任务的 TestClient。

    必须在 TestClient 进入 lifespan（触发崩溃恢复）之前插入 running 任务。
    """
    from fastapi.testclient import TestClient
    from sqlmodel import SQLModel, create_engine
    from app import db as db_module

    test_engine = create_engine(
        f"sqlite:///{tmp_path/'crash.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(test_engine)
    # 先插入 running 任务（在 lifespan 之前）
    with Session(test_engine) as s:
        s.add(Task(name="崩溃任务", status="running", last_job_id=5))
        s.add(Task(name="正常任务", status="pending"))
        s.commit()
    monkeypatch.setattr(db_module, "engine", test_engine)
    from app.main import app
    return TestClient(app), test_engine


def test_startup_marks_running_as_interrupted(tmp_path, monkeypatch):
    """lifespan 启动时应将所有 running 任务置为 interrupted。"""
    client, engine = _make_client_with_running_task(tmp_path, monkeypatch)
    with client as c:
        r = c.get("/api/health")
        assert r.status_code == 200
    # lifespan 退出后查库验证
    with Session(engine) as s:
        rows = {t.name: t for t in s.exec(select(Task)).all()}
        assert rows["崩溃任务"].status == "interrupted"
        assert rows["崩溃任务"].last_job_id == 5  # 游标不应被清空
        assert rows["正常任务"].status == "pending"  # 非 running 不受影响


def test_mark_running_as_interrupted_unit(engine):
    """单元测试：_mark_running_as_interrupted 直接调用应只改 running 任务。"""
    from app.main import _mark_running_as_interrupted
    from app import db as db_module
    with Session(engine) as s:
        s.add(Task(name="r1", status="running"))
        s.add(Task(name="r2", status="running"))
        s.add(Task(name="p1", status="pending"))
        s.add(Task(name="f1", status="finished"))
        s.commit()
    original = db_module.engine
    db_module.engine = engine
    try:
        count = _mark_running_as_interrupted()
        assert count == 2
    finally:
        db_module.engine = original
    with Session(engine) as s:
        rows = {t.name: t.status for t in s.exec(select(Task)).all()}
    assert rows["r1"] == "interrupted"
    assert rows["r2"] == "interrupted"
    assert rows["p1"] == "pending"
    assert rows["f1"] == "finished"


def test_resume_after_crash_sets_running(client):
    """resume-after-crash 将 interrupted 置回 running 并触发 run_task。"""
    from app import db as db_module
    # 先插入 profile，避免 run_task 因无 profile 直接 failed
    with Session(db_module.engine) as s:
        s.add(Profile(skills="linux", experience_years=2))
        s.add(Task(name="续跑任务", status="interrupted", last_job_id=3))
        s.commit()
        task_id = s.exec(select(Task).where(Task.name == "续跑任务")).first().id

    r = client.post(f"/api/tasks/{task_id}/resume-after-crash")
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert r.json()["previous_status"] == "interrupted"
    time.sleep(0.3)
    with Session(db_module.engine) as s:
        t = s.get(Task, task_id)
        # 无岗位时 run_task 会快速结束为 finished
        assert t.status in ("running", "finished")


# ---------- 端到端冒烟 ----------

def test_smoke_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


def test_smoke_dashboard_page_loads(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "EFW-AI" in r.text


def test_smoke_create_task_and_list(client):
    r = client.post("/api/tasks", json={
        "name": "冒烟任务", "keywords": '["python"]', "city": "武汉",
    })
    assert r.status_code == 200
    task_id = r.json()["id"]

    r = client.get("/api/tasks")
    assert r.status_code == 200
    names = [t["name"] for t in r.json()["tasks"]]
    assert "冒烟任务" in names

    r = client.get(f"/api/tasks/{task_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "冒烟任务"


def test_smoke_applications_endpoint(client):
    r = client.get("/api/applications")
    assert r.status_code == 200
    assert "applications" in r.json()


def test_smoke_config_endpoint(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_smoke_semi_queue_page(client):
    r = client.get("/semi-queue")
    assert r.status_code == 200


def test_smoke_task_detail_page(client):
    task = client.post("/api/tasks", json={"name": "详情页任务"}).json()
    r = client.get(f"/tasks/{task['id']}")
    assert r.status_code == 200
    assert "详情页任务" in r.text


def test_smoke_applications_page(client):
    r = client.get("/applications")
    assert r.status_code == 200


def test_smoke_application_detail_page_404(client):
    r = client.get("/applications/99999")
    assert r.status_code == 404


# ---------- 成本统计 ----------

def test_cost_stats_accumulated_tokens(client):
    """dashboard 应显示 ai_tokens_{task_id} 的累计 token 与估算成本。"""
    from app import db as db_module
    with Session(db_module.engine) as s:
        s.add(ConfigItem(key="ai_tokens_1", value=json.dumps({
            "prompt_tokens": 1000, "completion_tokens": 500,
        })))
        s.add(ConfigItem(key="price_per_1k", value="0.01"))
        s.commit()

    r = client.get("/")
    assert r.status_code == 200
    # 总成本 = (1000 + 500) / 1000 * 0.01 = 0.015
    assert "0.015" in r.text or "1500" in r.text


def test_cost_stats_default_price_zero(client):
    """未配置 price_per_1k 时成本为 0，但 token 数仍显示。"""
    from app import db as db_module
    with Session(db_module.engine) as s:
        s.add(ConfigItem(key="ai_tokens_2", value=json.dumps({
            "prompt_tokens": 200, "completion_tokens": 100,
        })))
        s.commit()

    r = client.get("/")
    assert r.status_code == 200
    assert "300" in r.text  # total tokens
