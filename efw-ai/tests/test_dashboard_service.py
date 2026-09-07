from datetime import date, timedelta
from app.models import Application, Task, ConfigItem, ApplicationEvent
from app.services.dashboard_service import get_today, get_deliveries

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def seed(session):
    t1 = Task(name="t1", status="running"); t2 = Task(name="t2", status="paused")
    session.add_all([t1, t2]); session.commit()
    session.add(ConfigItem(key="daily_limit", value="20"))
    session.add(ConfigItem(key="ai_tokens_1", value='{"prompt_tokens": 100, "completion_tokens": 50}'))
    session.add(ConfigItem(key="ai_tokens_2", value='{"prompt_tokens": 200, "completion_tokens": 30}'))
    session.add(ConfigItem(key="price_per_1k", value="0.002"))
    session.commit()
    apps = [
        Application(job_id=1, task_id=t1.id, status="applied", applied_at=TODAY),
        Application(job_id=2, task_id=t1.id, status="responded", applied_at=TODAY),
        Application(job_id=3, task_id=t1.id, status="pending_manual", applied_at=TODAY),
        Application(job_id=4, task_id=t2.id, status="applied", applied_at=YESTERDAY),
        Application(job_id=5, task_id=t2.id, status="skip", applied_at=YESTERDAY),
    ]
    session.add_all(apps); session.commit()
    for i in range(3):
        session.add(ApplicationEvent(application_id=1, event_type="llm_usage",
                                     detail=f'{{"tokens":{i}}}',
                                     created_at=f"{TODAY} 10:0{i}:00"))
    session.commit()


def test_get_today_delivered_excludes_pending_manual(session):
    seed(session)
    data = get_today(session)
    assert data["delivered_today"] == 2          # applied + responded（pending_manual 不算）
    assert data["daily_limit"] == 20
    assert data["remaining_ratio"] == 0.9
    assert data["running_tasks"] == 1
    assert data["paused_tasks"] == 1
    assert data["pending_followup"] == 1
    assert data["interview_offer"] == 0
    assert len(data["recent_events"]) == 3
    # cumulative cost: ai_tokens_1 (100+50) + ai_tokens_2 (200+30) = 380
    assert data["total_tokens"] == 380
    assert data["price_per_1k"] == 0.002
    assert data["total_cost"] == round(380 / 1000 * 0.002, 6)


def test_get_deliveries_trend_pads_zero_days(session):
    seed(session)
    data = get_deliveries(session, days=7)
    assert len(data["trend"]) == 7
    assert data["trend"][-1]["count"] == 2
    assert sum(t["count"] for t in data["trend"]) == 3   # 昨天 1 + 今天 2


def test_get_deliveries_status_totals(session):
    seed(session)
    data = get_deliveries(session, days=7)
    assert data["status_total"]["applied"] == 2          # 今天1 + 昨天1
    assert data["status_total"]["pending_manual"] == 1
    assert data["status_today"]["applied"] == 1
    assert data["pending_manual_count"] == 1
    assert len(data["per_task"]) == 2
