"""任务 API 测试：CRUD + 运行控制 + SSE 事件流。"""
import asyncio
import time

import pytest
from sqlmodel import Session

from app.models import Task, Job, Profile
from app.state import SseBroker


# ---------- 辅助 ----------

def _create_task(client, **overrides) -> dict:
    body = {
        "name": "测试任务", "keywords": '["k8s"]', "city": "武汉",
        "mode": "auto", "daily_limit": 20, "match_threshold": 7.0, "rules": "{}",
    }
    body.update(overrides)
    r = client.post("/api/tasks", json=body)
    assert r.status_code == 200
    return r.json()


# ---------- CRUD ----------

def test_create_task(client):
    task = _create_task(client, name="我的投递任务")
    assert task["id"] is not None
    assert task["name"] == "我的投递任务"
    assert task["status"] == "pending"
    assert task["mode"] == "auto"


def test_list_tasks(client):
    _create_task(client, name="任务A")
    _create_task(client, name="任务B")
    r = client.get("/api/tasks")
    assert r.status_code == 200
    names = [t["name"] for t in r.json()["tasks"]]
    assert "任务A" in names
    assert "任务B" in names


def test_get_task(client):
    task = _create_task(client, name="详情任务")
    r = client.get(f"/api/tasks/{task['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "详情任务"
    assert "application_stats" in data
    assert data["application_count"] == 0


def test_get_task_not_found(client):
    r = client.get("/api/tasks/99999")
    assert r.status_code == 404


# ---------- 运行控制 ----------

def _set_task_status(client, task_id: int, status: str) -> None:
    """直接在 DB 中设置任务状态（用于构造状态机测试前置条件）。"""
    from app import db as db_module
    with Session(db_module.engine) as s:
        t = s.get(Task, task_id)
        t.status = status
        s.commit()


def test_pause_task(client):
    task = _create_task(client)
    _set_task_status(client, task["id"], "running")
    r = client.post(f"/api/tasks/{task['id']}/pause")
    assert r.status_code == 200
    assert r.json()["status"] == "paused"
    from app import db as db_module
    with Session(db_module.engine) as s:
        t = s.get(Task, task["id"])
        assert t.status == "paused"


def test_pause_invalid_status_returns_409(client):
    """pending 状态的任务不能直接 pause。"""
    task = _create_task(client)  # status=pending
    r = client.post(f"/api/tasks/{task['id']}/pause")
    assert r.status_code == 409


def test_stop_task(client):
    task = _create_task(client)
    _set_task_status(client, task["id"], "running")
    r = client.post(f"/api/tasks/{task['id']}/stop")
    assert r.status_code == 200
    assert r.json()["status"] == "stopped"


def test_stop_invalid_status_returns_409(client):
    """pending 状态的任务不能直接 stop。"""
    task = _create_task(client)
    r = client.post(f"/api/tasks/{task['id']}/stop")
    assert r.status_code == 409


def test_pause_not_found(client):
    r = client.post("/api/tasks/99999/pause")
    assert r.status_code == 404


def test_start_task_no_jobs_finishes(client):
    """无岗位时 start 应快速结束，任务状态变为 finished。"""
    from app import db as db_module
    with Session(db_module.engine) as s:
        s.add(Profile(skills="linux,k8s", experience_years=3))
        s.commit()
    task = _create_task(client)
    r = client.post(f"/api/tasks/{task['id']}/start")
    assert r.status_code == 200
    time.sleep(0.5)
    with Session(db_module.engine) as s:
        t = s.get(Task, task["id"])
        assert t.status == "finished"


def test_start_invalid_status_returns_409(client):
    """running 状态的任务不能重复 start。"""
    task = _create_task(client)
    _set_task_status(client, task["id"], "running")
    r = client.post(f"/api/tasks/{task['id']}/start")
    assert r.status_code == 409


def test_resume_after_crash(client):
    task = _create_task(client)
    _set_task_status(client, task["id"], "interrupted")
    r = client.post(f"/api/tasks/{task['id']}/resume-after-crash")
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert r.json()["previous_status"] == "interrupted"


def test_resume_after_crash_wrong_status_returns_409(client):
    """非 interrupted 状态不能调用 resume-after-crash。"""
    task = _create_task(client)  # status=pending
    r = client.post(f"/api/tasks/{task['id']}/resume-after-crash")
    assert r.status_code == 409
    assert "interrupted" in r.json()["detail"]


def test_resume_invalid_status_returns_409(client):
    """非 paused 状态不能调用 resume。"""
    task = _create_task(client)  # status=pending
    r = client.post(f"/api/tasks/{task['id']}/resume")
    assert r.status_code == 409


# ---------- SSE Broker 单元测试（纯 async，无 HTTP） ----------

async def test_sse_broker_publish_subscribe():
    """Broker 发布事件，订阅者应能收到。"""
    broker = SseBroker()
    received = []

    async def subscriber():
        async for event in broker.subscribe():
            received.append(event)
            if len(received) >= 2:
                break

    task = asyncio.create_task(subscriber())
    await asyncio.sleep(0.05)  # 等待订阅者注册
    broker.publish({"type": "a", "data": 1})
    broker.publish({"type": "b", "data": 2})
    await asyncio.wait_for(task, timeout=2.0)

    assert len(received) == 2
    assert received[0]["type"] == "a"
    assert received[1]["type"] == "b"


async def test_sse_broker_multiple_subscribers():
    """多个订阅者都应收到广播事件。"""
    broker = SseBroker()
    received1, received2 = [], []

    async def subscriber(recv):
        async for event in broker.subscribe():
            recv.append(event)
            if len(recv) >= 1:
                break

    t1 = asyncio.create_task(subscriber(received1))
    t2 = asyncio.create_task(subscriber(received2))
    await asyncio.sleep(0.05)
    broker.publish({"type": "broadcast"})
    await asyncio.wait_for(t1, timeout=2.0)
    await asyncio.wait_for(t2, timeout=2.0)

    assert len(received1) == 1
    assert len(received2) == 1


async def test_sse_broker_unsubscribe_cleanup():
    """订阅者退出后应从订阅列表中移除。"""
    broker = SseBroker()
    assert len(broker._subscribers) == 0

    async def subscriber():
        async for event in broker.subscribe():
            break  # 收到一个事件就退出

    task = asyncio.create_task(subscriber())
    await asyncio.sleep(0.05)
    assert len(broker._subscribers) == 1
    broker.publish({"type": "x"})
    await asyncio.wait_for(task, timeout=2.0)
    await asyncio.sleep(0.05)
    assert len(broker._subscribers) == 0


# ---------- SSE 端点直接测试（避免 TestClient 无限流挂起） ----------

async def test_sse_endpoint_generator():
    """直接调用 SSE 端点函数，验证响应头和首个 connected 事件。"""
    from app.state import SseBroker
    from types import SimpleNamespace
    from app.api.tasks import task_events

    broker = SseBroker()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(sse_broker=broker)))

    resp = await task_events(task_id=42, request=request)
    assert resp.media_type == "text/event-stream"
    assert resp.headers.get("cache-control") == "no-cache"

    # 从生成器中读取第一个事件
    gen = resp.body_iterator
    first = await gen.__anext__()
    if isinstance(first, bytes):
        first = first.decode("utf-8")
    assert "connected" in first
    assert "42" in first
    await gen.aclose()
