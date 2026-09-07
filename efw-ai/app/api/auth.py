"""Boss 登录会话 API：状态查询、发起登录、立即重检。"""
from fastapi import APIRouter, Request, HTTPException

router = APIRouter()


def _get_session(request: Request):
    svc = getattr(request.app.state, "browser_session", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="BrowserSession 未初始化")
    return svc


@router.get("/auth/status")
def auth_status(request: Request) -> dict:
    return _get_session(request).status()


@router.post("/auth/login")
async def auth_login(request: Request) -> dict:
    svc = _get_session(request)
    state = await svc.start_login()
    return {"state": state, "message": "已在浏览器中打开登录窗口，请完成登录"}


@router.post("/auth/check")
async def auth_check(request: Request) -> dict:
    svc = _get_session(request)
    state = await svc.check_now()
    return {"state": state, "message": "已触发登录态重检"}
