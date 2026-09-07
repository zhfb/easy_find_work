from fastapi import APIRouter, Depends
from sqlmodel import Session
from ..db import get_session
from ..services.dashboard_service import get_today, get_deliveries

router = APIRouter()


@router.get("/dashboard/today")
def dashboard_today(session: Session = Depends(get_session)) -> dict:
    return get_today(session)


@router.get("/dashboard/deliveries")
def dashboard_deliveries(days: int = 7, session: Session = Depends(get_session)) -> dict:
    return get_deliveries(session, days=days)
