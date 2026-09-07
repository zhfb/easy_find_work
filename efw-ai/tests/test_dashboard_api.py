import pytest


@pytest.fixture()
def seed_via_client(client):
    # conftest's client fixture monkeypatches app.db.engine to an isolated
    # test SQLite DB (monkeypatch.setattr(db_module, "engine", test_engine)).
    # Importing app.db.engine here (after client fixture runs) resolves to
    # that same test engine, so seed data is visible to the API handlers.
    from app.models import Application, Task, ConfigItem
    from sqlmodel import Session
    from app.db import engine
    from datetime import date
    with Session(engine) as s:
        t = Task(name="t", status="running"); s.add(t); s.commit()
        s.add(ConfigItem(key="daily_limit", value="20"))
        s.add(Application(job_id=1, task_id=t.id, status="applied", applied_at=date.today().isoformat()))
        s.commit()
    return client


def test_dashboard_today(seed_via_client):
    resp = seed_via_client.get("/api/dashboard/today")
    assert resp.status_code == 200
    data = resp.json()
    assert data["delivered_today"] == 1
    assert data["running_tasks"] == 1
    assert "recent_events" in data


def test_dashboard_deliveries(seed_via_client):
    resp = seed_via_client.get("/api/dashboard/deliveries?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["trend"]) == 7
    assert data["status_total"]["applied"] == 1
