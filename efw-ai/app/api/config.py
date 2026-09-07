from fastapi import APIRouter, Depends
from sqlmodel import Session
from ..db import get_session
from ..schemas import ConfigPut
from ..services.config_service import get_all_config, set_config

router = APIRouter()


@router.get("/config")
def list_config(session: Session = Depends(get_session)) -> dict:
    return get_all_config(session)


@router.put("/config")
def update_config(body: ConfigPut, session: Session = Depends(get_session)) -> dict:
    set_config(session, body.key, body.value)
    return {"ok": True}
