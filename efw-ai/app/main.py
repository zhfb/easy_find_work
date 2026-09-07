from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from .db import init_db, get_session
from .api import config as config_api, profile as profile_api
from .services.stats_service import get_today_stats

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(config_api.router, prefix="/api")
app.include_router(profile_api.router, prefix="/api")


@app.get("/")
def dashboard(request: Request, session: Session = Depends(get_session)):
    stats = get_today_stats(session)
    total = sum(stats.values())
    today = date.today().isoformat()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "stats": stats, "total": total, "today": today},
    )
