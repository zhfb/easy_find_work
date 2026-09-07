"""对话式助手：LLM Function Calling 循环 + 写操作确认卡片 + SSE 流式输出。"""
import asyncio
import json
import logging
import uuid
from typing import AsyncIterator

from sqlmodel import Session, select

from app.models import Application, ChatMessage, Job, Task

logger = logging.getLogger(__name__)

# ---------- 工具定义（OpenAI Function Calling 格式） ----------

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_stats",
            "description": "获取今日投递统计，返回各状态的投递数量",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_applications",
            "description": "按状态筛选投递记录列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "投递状态：skip|pending_manual|applied|responded|interview|offer|rejected|withdrawn",
                    }
                },
                "required": ["status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_task_status",
            "description": "查询指定任务的当前状态和配置",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "integer", "description": "任务 ID"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task_config",
            "description": "更新任务配置（关键词、城市、每日上限等）。此操作需要用户确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer", "description": "任务 ID"},
                    "patch": {
                        "type": "object",
                        "description": "要更新的字段键值对，如 {\"daily_limit\": 30, \"city\": \"北京\"}",
                    },
                },
                "required": ["task_id", "patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_task",
            "description": "启动指定投递任务。此操作需要用户确认。",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "integer", "description": "任务 ID"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pause_task",
            "description": "暂停指定投递任务。此操作需要用户确认。",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "integer", "description": "任务 ID"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "regenerate_message",
            "description": "重新生成指定投递记录的打招呼文案。此操作需要用户确认。",
            "parameters": {
                "type": "object",
                "properties": {"application_id": {"type": "integer", "description": "投递记录 ID"}},
                "required": ["application_id"],
            },
        },
    },
]

# 写操作工具：不直接执行，返回确认卡片由用户确认
WRITE_TOOLS = frozenset({
    "update_task_config", "start_task", "pause_task", "regenerate_message",
})

SYSTEM_PROMPT = (
    "你是 EFW-AI 智能投递助手，帮助用户管理自动投递任务和投递记录。"
    "你可以查询统计、投递记录、任务状态，也可以在用户确认后启动/暂停任务、更新配置、重新生成文案。"
    "回答简洁明了，用中文回复。"
)

# SSE delta 分块大小（字符数）
_DELTA_CHUNK_SIZE = 6


class ChatService:
    """对话式助手服务。

    职责：
      - stream: 接收用户消息，LLM 多轮 tool-call 循环，SSE 事件输出
      - 读操作工具直接执行并把结果喂回 LLM
      - 写操作工具生成 confirm_id 挂起，yield confirm 事件，由 confirm_tool 执行
      - 会话历史持久化到 chat_message 表
    """

    def __init__(self, llm, task_service=None, session_factory=None, app_state=None):
        self.llm = llm
        self.task_service = task_service
        self.session_factory = session_factory
        self.app_state = app_state
        # 挂起的写操作确认：{confirm_id: {"tool": name, "args": dict}}
        self._pending_confirms: dict[str, dict] = {}

    # ---------- 主流程 ----------

    async def stream(self, user_message: str) -> AsyncIterator[dict]:
        """处理用户消息，产出 SSE 事件流。

        事件类型：
          - delta: 文本增量
          - confirm: 写操作确认卡片
          - done: 流结束
          - error: 错误
        """
        # 1. LLM 可用性检查
        if not await self.llm.is_available():
            yield {"type": "error", "text": "AI 服务不可用，请先在设置中配置 API Key"}
            return

        # 2. 加载历史 + 追加用户消息
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if self.session_factory is not None:
            history = self._load_history(limit=20)
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        # 持久化用户消息
        self._save_message("user", user_message)

        # 3. LLM 多轮 tool-call 循环
        assistant_text = ""
        max_rounds = 8
        try:
            for _ in range(max_rounds):
                result = await self.llm.complete(messages, tools=TOOLS)

                if result.tool_calls:
                    # 追加 assistant 消息（含 tool_calls）
                    messages.append({
                        "role": "assistant",
                        "content": result.content or "",
                        "tool_calls": result.tool_calls,
                    })

                    write_triggered = False
                    for tc in result.tool_calls:
                        name = tc["function"]["name"]
                        try:
                            args = json.loads(tc["function"]["arguments"] or "{}")
                        except json.JSONDecodeError:
                            args = {}

                        if name in WRITE_TOOLS:
                            # 写操作：挂起并 yield confirm，停止循环
                            confirm_id = uuid.uuid4().hex[:16]
                            self._pending_confirms[confirm_id] = {"tool": name, "args": args}
                            yield {
                                "type": "confirm",
                                "tool": name,
                                "args": args,
                                "confirm_id": confirm_id,
                            }
                            write_triggered = True
                            break  # 不再处理后续工具调用
                        else:
                            # 读操作：直接执行，结果追加到 messages
                            tool_result = self._execute_read_tool(name, args)
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                            })

                    if write_triggered:
                        yield {"type": "done"}
                        return
                    # 所有工具均为读操作，继续下一轮 LLM 调用
                    continue

                # 无 tool_calls：最终文本回复
                assistant_text = result.content or ""
                break
        except Exception as e:
            logger.exception("chat stream LLM loop failed: %s", e)
            yield {"type": "error", "text": "AI 服务暂时不可用，请稍后重试"}
            return

        # 4. 流式输出文本
        self._save_message("assistant", assistant_text)
        for chunk in self._split_text(assistant_text):
            yield {"type": "delta", "text": chunk}
        yield {"type": "done"}

    # ---------- 确认执行 ----------

    async def confirm_tool(self, confirm_id: str) -> dict:
        """执行挂起的写操作。"""
        pending = self._pending_confirms.pop(confirm_id, None)
        if pending is None:
            return {"ok": False, "error": "确认请求已过期或找不到，请重新发起操作"}

        tool = pending["tool"]
        args = pending["args"]

        try:
            if tool == "start_task":
                await self._do_start_task(args.get("task_id"))
            elif tool == "pause_task":
                self._do_pause_task(args.get("task_id"))
            elif tool == "update_task_config":
                self._do_update_task_config(args.get("task_id"), args.get("patch", {}))
            elif tool == "regenerate_message":
                await self._do_regenerate_message(args.get("application_id"))
            else:
                return {"ok": False, "error": f"未知工具: {tool}"}
            return {"ok": True, "tool": tool, "args": args}
        except Exception as e:
            logger.exception("confirm_tool %s failed: %s", tool, e)
            return {"ok": False, "error": str(e)}

    # ---------- 读工具执行 ----------

    def _execute_read_tool(self, name: str, args: dict) -> dict:
        if name == "get_stats":
            return self._tool_get_stats()
        if name == "get_applications":
            return self._tool_get_applications(args.get("status"))
        if name == "get_task_status":
            return self._tool_get_task_status(args.get("task_id"))
        return {"error": f"未知读工具: {name}"}

    def _tool_get_stats(self) -> dict:
        if self.session_factory is None:
            return {"applied": 0, "pending": 0}
        from app.services.stats_service import get_today_stats
        with self.session_factory() as session:
            return get_today_stats(session)

    def _tool_get_applications(self, status: str | None) -> dict:
        if self.session_factory is None:
            return {"applications": []}
        with self.session_factory() as session:
            stmt = select(Application)
            if status:
                stmt = stmt.where(Application.status == status)
            stmt = stmt.order_by(Application.id.desc()).limit(50)
            apps = session.exec(stmt).all()
            result = []
            for a in apps:
                job = session.get(Job, a.job_id)
                result.append({
                    "id": a.id,
                    "status": a.status,
                    "decision": a.decision,
                    "match_score": a.match_score,
                    "job_title": job.title if job else "",
                    "company": job.company if job else "",
                    "salary_text": job.salary_text if job else "",
                })
            return {"applications": result, "count": len(result)}

    def _tool_get_task_status(self, task_id: int | None) -> dict:
        if self.session_factory is None or task_id is None:
            return {"error": "缺少 task_id 或数据库未配置"}
        with self.session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                return {"error": f"任务 {task_id} 不存在"}
            return {
                "id": task.id,
                "name": task.name,
                "status": task.status,
                "city": task.city,
                "mode": task.mode,
                "daily_limit": task.daily_limit,
                "match_threshold": task.match_threshold,
            }

    # ---------- 写工具执行（confirm 后） ----------

    async def _do_start_task(self, task_id: int | None) -> None:
        if task_id is None:
            raise ValueError("缺少 task_id")
        if self.task_service is None:
            raise RuntimeError("task_service 未配置")
        # 并发防护：与 api/tasks.py 的 _check_not_running 一致，防止重复启动 run_task 协程
        if self.app_state is not None and task_id in self.app_state.running_tasks:
            raise RuntimeError("任务已在运行中")
        self.task_service.start(task_id)
        asyncio.create_task(self.task_service.run_task(task_id))

    def _do_pause_task(self, task_id: int | None) -> None:
        if task_id is None:
            raise ValueError("缺少 task_id")
        if self.task_service is None:
            raise RuntimeError("task_service 未配置")
        self.task_service.pause(task_id)

    def _do_update_task_config(self, task_id: int | None, patch: dict) -> None:
        if task_id is None:
            raise ValueError("缺少 task_id")
        if self.session_factory is None:
            raise RuntimeError("数据库未配置")
        allowed_fields = {"name", "keywords", "city", "mode", "max_deliveries",
                          "daily_limit", "match_threshold", "rules"}
        json_string_fields = {"keywords", "rules"}
        with self.session_factory() as session:
            task = session.get(Task, task_id)
            if task is None:
                raise ValueError(f"任务 {task_id} 不存在")
            for key, value in patch.items():
                if key in allowed_fields:
                    # keywords/rules 在模型中为 JSON 字符串列，非字符串值需序列化
                    if key in json_string_fields and not isinstance(value, str):
                        value = json.dumps(value, ensure_ascii=False)
                    setattr(task, key, value)
            session.commit()

    async def _do_regenerate_message(self, application_id: int | None) -> None:
        if application_id is None:
            raise ValueError("缺少 application_id")
        if self.session_factory is None:
            raise RuntimeError("数据库未配置")
        from app.services.application_service import regenerate_message
        # writer 从 orchestrator 获取；若 task_service 有 orchestrator 则用之
        writer = None
        if self.task_service is not None and hasattr(self.task_service, "orchestrator"):
            writer = getattr(self.task_service.orchestrator, "writer", None)
        with self.session_factory() as session:
            await regenerate_message(session, application_id, writer)

    # ---------- 历史持久化 ----------

    def _load_history(self, limit: int = 20) -> list[dict]:
        if self.session_factory is None:
            return []
        with self.session_factory() as session:
            msgs = session.exec(
                select(ChatMessage).order_by(ChatMessage.id.desc()).limit(limit)
            ).all()
            return [{"role": m.role, "content": m.content} for m in reversed(msgs)]

    def _save_message(self, role: str, content: str) -> None:
        if self.session_factory is None:
            return
        try:
            with self.session_factory() as session:
                session.add(ChatMessage(role=role, content=content))
                session.commit()
        except Exception as e:
            logger.warning("保存聊天消息失败: %s", e)

    # ---------- 文本分块 ----------

    @staticmethod
    def _split_text(text: str) -> list[str]:
        if not text:
            return []
        return [text[i:i + _DELTA_CHUNK_SIZE] for i in range(0, len(text), _DELTA_CHUNK_SIZE)]
