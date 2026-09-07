"""看板统计服务：今日状态与投递情况（纯 SQL 聚合，可单测）。"""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlmodel import Session, select, func

from ..models import Application, Task, ConfigItem, ApplicationEvent

DELIVERED_STATUSES = ("applied", "responded", "interview", "offer", "rejected", "withdrawn")
STATUS_ENUM = ("skip", "pending_manual", "applied", "responded", "interview",
               "offer", "rejected", "withdrawn")


def _count_by_status(session, start=None, end=None) -> dict:
    q = select(Application.status, func.count(Application.id))
    if start is not None:
        q = q.where(Application.applied_at >= start)
    if end is not None:
        q = q.where(Application.applied_at < end)
    rows = session.exec(q.group_by(Application.status)).all()
    dist = {s: 0 for s in STATUS_ENUM}
    for status, count in rows:
        dist[status] = count
    return dist


def get_today(session: Session) -> dict:
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    status_today = _count_by_status(session, today, tomorrow)
    delivered = sum(status_today[s] for s in DELIVERED_STATUSES)
    raw_limit = session.exec(
        select(ConfigItem).where(ConfigItem.key == "daily_limit")
    ).first()
    daily_limit = int(raw_limit.value) if raw_limit and raw_limit.value.isdigit() else 20
    running = session.exec(
        select(func.count(Task.id)).where(Task.status == "running")
    ).one()
    paused = session.exec(
        select(func.count(Task.id)).where(Task.status == "paused")
    ).one()
    followup = session.exec(
        select(func.count(Application.id)).where(Application.status == "responded")
    ).one()
    io = session.exec(
        select(func.count(Application.id)).where(Application.status.in_(("interview", "offer")))
    ).one()
    events = session.exec(
        select(ApplicationEvent).order_by(ApplicationEvent.id.desc()).limit(10)
    ).all()
    cost = _compute_cost(session)
    return {
        "delivered_today": delivered,
        "daily_limit": daily_limit,
        "remaining_ratio": round(1 - delivered / daily_limit, 3) if daily_limit else 0.0,
        "running_tasks": running,
        "paused_tasks": paused,
        "pending_followup": followup,
        "interview_offer": io,
        "total_tokens": cost["total_tokens"],
        "total_cost": cost["estimated_cost"],
        "price_per_1k": cost["price_per_1k"],
        "recent_events": [
            {"id": e.id, "event_type": e.event_type, "detail": e.detail,
             "created_at": e.created_at}
            for e in events
        ],
    }


def _compute_cost(session: Session) -> dict:
    total_prompt = total_completion = 0
    items = session.exec(
        select(ConfigItem).where(ConfigItem.key.like("ai_tokens_%"))
    ).all()
    for item in items:
        try:
            data = json.loads(item.value) if item.value else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        total_prompt += data.get("prompt_tokens", 0)
        total_completion += data.get("completion_tokens", 0)
    price_raw = session.exec(
        select(ConfigItem).where(ConfigItem.key == "price_per_1k")
    ).first()
    try:
        price = float(price_raw.value) if price_raw else 0.0
    except (ValueError, TypeError):
        price = 0.0
    total_tokens = total_prompt + total_completion
    return {"total_tokens": total_tokens, "estimated_cost": round(total_tokens / 1000 * price, 6),
            "price_per_1k": price}


def get_deliveries(session: Session, days: int = 7) -> dict:
    today = date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()
    rows = session.exec(
        select(Application.applied_at, func.count(Application.id))
        .where(Application.applied_at >= start)
        .where(Application.applied_at < tomorrow)
        .where(Application.status.in_(DELIVERED_STATUSES))
        .group_by(Application.applied_at)
    ).all()
    counts = dict(rows)
    trend = [
        {"date": (today - timedelta(days=days - 1 - i)).isoformat(),
         "count": counts.get((today - timedelta(days=days - 1 - i)).isoformat(), 0)}
        for i in range(days)
    ]
    per_task_rows = session.exec(
        select(Application.task_id, func.count(Application.id))
        .where(Application.status.in_(DELIVERED_STATUSES))
        .group_by(Application.task_id)
    ).all()
    per_task = []
    for task_id, count in per_task_rows:
        t = session.get(Task, task_id)
        per_task.append({"task_id": task_id,
                         "name": t.name if t else f"#{task_id}", "count": count})
    return {
        "trend": trend,
        "status_today": _count_by_status(session, today.isoformat(), tomorrow),
        "status_total": _count_by_status(session),
        "pending_manual_count": session.exec(
            select(func.count(Application.id)).where(Application.status == "pending_manual")
        ).one(),
        "per_task": per_task,
    }
