from datetime import date, timedelta

from sqlmodel import Session, select, func

from ..models import Application


def get_today_stats(session: Session) -> dict:
    today_start = date.today().isoformat()
    tomorrow_start = (date.today() + timedelta(days=1)).isoformat()
    rows = session.exec(
        select(Application.status, func.count(Application.id))
        .where(Application.applied_at >= today_start)
        .where(Application.applied_at < tomorrow_start)
        .group_by(Application.status)
    ).all()
    return {status: count for status, count in rows}
