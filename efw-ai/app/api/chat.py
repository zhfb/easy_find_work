"""对话式助手 API：SSE 流式聊天 + 历史记录 + 写操作确认。"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from ..db import get_session
from ..models import ChatMessage

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatRequest(BaseModel):
    message: str


class ConfirmRequest(BaseModel):
    confirm_id: str


def _get_chat_service(request: Request):
    svc = getattr(request.app.state, "chat_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="ChatService 未初始化")
    return svc


@router.post("/chat")
async def chat_stream(body: ChatRequest, request: Request):
    """SSE 流式聊天：接收用户消息，返回 delta/confirm/done/error 事件流。"""
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")

    svc = _get_chat_service(request)

    async def event_generator():
        async for event in svc.stream(body.message):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/history")
def chat_history(session: Session = Depends(get_session), limit: int = 50) -> dict:
    """获取聊天历史记录（按时间倒序）。"""
    msgs = session.exec(
        select(ChatMessage).order_by(ChatMessage.id.desc()).limit(limit)
    ).all()
    return {
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
            for m in reversed(msgs)
        ]
    }


@router.post("/chat/confirm")
async def chat_confirm(body: ConfirmRequest, request: Request) -> dict:
    """执行挂起的写操作（用户点击确认卡片后调用）。"""
    svc = _get_chat_service(request)
    result = await svc.confirm_tool(body.confirm_id)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error", "确认失败"))
    return result
