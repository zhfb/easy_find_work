"""对话式助手测试：ChatService 工具调用循环 + 写操作确认卡片 + SSE 事件。"""
import json
from types import SimpleNamespace

import pytest
from sqlmodel import Session, select

from app.agent.llm import LLMResult
from app.models import ChatMessage, Task


# ---------- 辅助 Fake ----------

class NoLlm:
    """模拟不可用的 LLM（无 API Key / 熔断打开）。"""
    async def is_available(self):
        return False


class FakeLlm:
    """可编排的 LLM：按顺序返回预设结果。"""
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    async def is_available(self):
        return True

    async def complete(self, messages, temperature=0.5, json_mode=False, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        if not self._results:
            return LLMResult(content="（无更多预设结果）")
        return self._results.pop(0)


def _tool_call(tc_id: str, name: str, arguments: dict) -> dict:
    """构造 LLMResult.tool_calls 中的单条工具调用。"""
    return {
        "id": tc_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


class FakeTaskService:
    def __init__(self):
        self.started = []
        self.paused = []

    def start(self, task_id):
        self.started.append(task_id)

    def pause(self, task_id):
        self.paused.append(task_id)

    async def run_task(self, task_id):
        pass  # 测试用空实现


# ---------- 基础：不可用 LLM ----------

async def test_unavailable_yields_error():
    from app.services.chat_service import ChatService
    svc = ChatService(llm=NoLlm(), task_service=None, session_factory=None)
    events = [e async for e in svc.stream("你好")]
    assert events[0]["type"] == "error"
    assert "API Key" in events[0]["text"]


def test_write_tool_needs_confirm():
    from app.services.chat_service import WRITE_TOOLS
    assert "update_task_config" in WRITE_TOOLS
    assert "start_task" in WRITE_TOOLS
    assert "pause_task" in WRITE_TOOLS
    assert "regenerate_message" in WRITE_TOOLS
    assert "get_stats" not in WRITE_TOOLS
    assert "get_applications" not in WRITE_TOOLS
    assert "get_task_status" not in WRITE_TOOLS


# ---------- 纯文本回复（无工具调用） ----------

async def test_plain_text_response_streams_delta_and_done():
    from app.services.chat_service import ChatService
    llm = FakeLlm([LLMResult(content="你好，我是助手")])
    svc = ChatService(llm=llm, task_service=None, session_factory=None)
    events = [e async for e in svc.stream("你好")]
    types = [e["type"] for e in events]
    assert "delta" in types
    assert "done" in types
    # delta 拼接应等于完整内容
    text = "".join(e["text"] for e in events if e["type"] == "delta")
    assert text == "你好，我是助手"


# ---------- 读工具调用：get_stats ----------

async def test_read_tool_get_stats_executes_and_feeds_back():
    """LLM 先返回 get_stats 工具调用 → ChatService 执行 → 把结果喂回 LLM → LLM 返回文本。"""
    from app.services.chat_service import ChatService
    # 第一次调用返回工具调用，第二次返回文本
    llm = FakeLlm([
        LLMResult(content="", tool_calls=[_tool_call("tc1", "get_stats", {})]),
        LLMResult(content="当前共有 5 条投递记录"),
    ])
    svc = ChatService(llm=llm, task_service=None, session_factory=None)
    # 注入一个假的 stats 执行器
    svc._tool_get_stats = lambda: {"applied": 3, "pending": 2}

    events = [e async for e in svc.stream("今天投递情况如何？")]
    types = [e["type"] for e in events]
    assert "delta" in types
    assert "done" in types
    text = "".join(e["text"] for e in events if e["type"] == "delta")
    assert "5" in text or "投递" in text
    # 验证 LLM 被调用了两次（工具调用 + 最终文本）
    assert len(llm.calls) == 2
    # 第二次调用的 messages 中应包含 tool 角色的结果
    second_msgs = llm.calls[1]["messages"]
    tool_msgs = [m for m in second_msgs if m["role"] == "tool"]
    assert len(tool_msgs) == 1


# ---------- 写工具调用：start_task 需要确认 ----------

async def test_write_tool_start_task_yields_confirm_not_execute():
    """写操作工具不直接执行，而是 yield confirm 事件并停止流。"""
    from app.services.chat_service import ChatService
    llm = FakeLlm([
        LLMResult(content="", tool_calls=[_tool_call("tc1", "start_task", {"task_id": 1})]),
    ])
    ts = FakeTaskService()
    svc = ChatService(llm=llm, task_service=ts, session_factory=None)

    events = [e async for e in svc.stream("启动任务 1")]
    types = [e["type"] for e in events]
    assert "confirm" in types
    assert "done" in types
    # 写操作不应被直接执行
    assert ts.started == []
    # confirm 事件应包含 tool、args、confirm_id
    confirm_ev = next(e for e in events if e["type"] == "confirm")
    assert confirm_ev["tool"] == "start_task"
    assert confirm_ev["args"] == {"task_id": 1}
    assert "confirm_id" in confirm_ev


async def test_confirm_tool_executes_pending_write():
    """用户确认后，confirm_tool 应执行挂起的写操作。"""
    from app.services.chat_service import ChatService
    llm = FakeLlm([
        LLMResult(content="", tool_calls=[_tool_call("tc1", "start_task", {"task_id": 42})]),
    ])
    ts = FakeTaskService()
    svc = ChatService(llm=llm, task_service=ts, session_factory=None)

    events = [e async for e in svc.stream("启动任务 42")]
    confirm_ev = next(e for e in events if e["type"] == "confirm")
    cid = confirm_ev["confirm_id"]

    result = await svc.confirm_tool(cid)
    assert result["ok"] is True
    assert ts.started == [42]


async def test_confirm_tool_invalid_id_returns_error():
    from app.services.chat_service import ChatService
    svc = ChatService(llm=NoLlm(), task_service=None, session_factory=None)
    result = await svc.confirm_tool("nonexistent-id")
    assert result["ok"] is False
    assert "找不到" in result["error"]


# ---------- 会话历史持久化 ----------

async def test_chat_history_persisted(session):
    """用户消息和助手回复应写入 chat_message 表。"""
    from app.services.chat_service import ChatService
    llm = FakeLlm([LLMResult(content="收到")])
    sf = lambda: session
    svc = ChatService(llm=llm, task_service=None, session_factory=sf)

    events = [e async for e in svc.stream("测试消息")]
    assert any(e["type"] == "done" for e in events)

    msgs = session.exec(select(ChatMessage).order_by(ChatMessage.id)).all()
    roles = [m.role for m in msgs]
    assert "user" in roles
    assert "assistant" in roles
    user_msg = next(m for m in msgs if m.role == "user")
    assert user_msg.content == "测试消息"
    asst_msg = next(m for m in msgs if m.role == "assistant")
    assert asst_msg.content == "收到"


# ---------- LlmClient tools 支持 ----------

def test_llmresult_has_tool_calls_field():
    r = LLMResult(content="hi")
    assert r.tool_calls == []


async def test_llmclient_complete_with_tools_passes_to_api():
    """LlmClient.complete(tools=...) 应将 tools 传给底层 API。"""
    from app.agent.llm import LlmClient

    captured = {}

    class FakeCompletions:
        async def create(self, **kw):
            captured.update(kw)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok", tool_calls=None))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    cli = LlmClient(client=FakeClient(), model="m")
    tools = [{"type": "function", "function": {"name": "get_stats", "parameters": {}}}]
    result = await cli.complete([{"role": "user", "content": "hi"}], tools=tools)
    assert "tools" in captured
    assert captured["tools"] == tools
    assert result.tool_calls == []


async def test_llmclient_complete_extracts_tool_calls_from_response():
    """API 返回 tool_calls 时，LlmClient 应解析到 result.tool_calls。"""
    from app.agent.llm import LlmClient

    raw_tc = SimpleNamespace(
        id="call_1",
        type="function",
        function=SimpleNamespace(name="get_stats", arguments="{}"),
    )

    class FakeCompletions:
        async def create(self, **kw):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=[raw_tc]))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    cli = LlmClient(client=FakeClient(), model="m")
    result = await cli.complete([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["id"] == "call_1"
    assert result.tool_calls[0]["function"]["name"] == "get_stats"
    assert result.tool_calls[0]["function"]["arguments"] == "{}"


# ---------- 多工具调用：读 + 写混合 ----------

async def test_mixed_read_and_write_tools():
    """LLM 同时返回读工具和写工具：读工具执行，写工具 yield confirm。"""
    from app.services.chat_service import ChatService
    llm = FakeLlm([
        LLMResult(content="", tool_calls=[
            _tool_call("tc1", "get_stats", {}),
            _tool_call("tc2", "start_task", {"task_id": 3}),
        ]),
    ])
    ts = FakeTaskService()
    svc = ChatService(llm=llm, task_service=ts, session_factory=None)
    svc._tool_get_stats = lambda: {"applied": 1}

    events = [e async for e in svc.stream("查看状态并启动任务3")]
    types = [e["type"] for e in events]
    # 写工具触发 confirm，流停止
    assert "confirm" in types
    assert ts.started == []  # 写操作未执行
    # 读工具结果应已追加到 messages（通过第二次 LLM 调用验证，但因为写工具停止了循环，可能没有第二次调用）
    # 关键：confirm 事件的 tool 应该是 start_task
    confirm_ev = next(e for e in events if e["type"] == "confirm")
    assert confirm_ev["tool"] == "start_task"


# ---------- 并发防护：重复启动任务 ----------

class FakeAppState:
    def __init__(self):
        self.running_tasks = set()


async def test_start_task_when_already_running_returns_error():
    """任务已在运行时，chat 发起的 start_task 应返回错误，不创建第二个 run_task 协程。"""
    from app.services.chat_service import ChatService
    llm = FakeLlm([
        LLMResult(content="", tool_calls=[_tool_call("tc1", "start_task", {"task_id": 7})]),
    ])
    ts = FakeTaskService()
    app_state = FakeAppState()
    app_state.running_tasks.add(7)
    svc = ChatService(llm=llm, task_service=ts, session_factory=None, app_state=app_state)

    events = [e async for e in svc.stream("启动任务7")]
    confirm_ev = next(e for e in events if e["type"] == "confirm")
    result = await svc.confirm_tool(confirm_ev["confirm_id"])
    assert result["ok"] is False
    assert "运行中" in result["error"]
    assert ts.started == []


# ---------- 异常处理：LLM 调用失败时 yield error ----------

class RaisingLlm:
    async def is_available(self):
        return True

    async def complete(self, messages, temperature=0.5, json_mode=False, tools=None):
        from app.agent.llm import LlmUnavailable
        raise LlmUnavailable("simulated failure")


async def test_llm_exception_in_loop_yields_error_event():
    """LLM 调用抛异常时，stream 应 yield error 事件而非中断生成器。"""
    from app.services.chat_service import ChatService
    svc = ChatService(llm=RaisingLlm(), task_service=None, session_factory=None)
    events = [e async for e in svc.stream("你好")]
    assert events[0]["type"] == "error"
    assert "暂时不可用" in events[0]["text"]
    assert not any(e["type"] == "done" for e in events)


# ---------- JSON 列类型修正：keywords/rules 序列化 ----------

async def test_update_task_config_serializes_json_columns(session):
    """update_task_config 对 keywords/rules 传入 list/dict 时应序列化为 JSON 字符串。"""
    from app.services.chat_service import ChatService
    from app.models import Task
    task = Task(name="测试", keywords='["old"]', rules='{}')
    session.add(task)
    session.commit()
    session.refresh(task)
    tid = task.id

    svc = ChatService(llm=NoLlm(), task_service=None, session_factory=lambda: session)
    svc._do_update_task_config(tid, {
        "keywords": ["k8s", "linux"],
        "rules": {"salary_min": 10000},
        "city": "北京",
    })

    updated = session.get(Task, tid)
    assert updated.keywords == '["k8s", "linux"]'
    assert updated.rules == '{"salary_min": 10000}'
    assert updated.city == "北京"


async def test_update_task_config_preserves_string_json_columns(session):
    """keywords/rules 已经是字符串时不应重复序列化。"""
    from app.services.chat_service import ChatService
    from app.models import Task
    task = Task(name="测试", keywords='["old"]', rules='{}')
    session.add(task)
    session.commit()
    session.refresh(task)
    tid = task.id

    svc = ChatService(llm=NoLlm(), task_service=None, session_factory=lambda: session)
    svc._do_update_task_config(tid, {
        "keywords": '["new"]',
        "rules": '{"x": 1}',
    })

    updated = session.get(Task, tid)
    assert updated.keywords == '["new"]'
    assert updated.rules == '{"x": 1}'
