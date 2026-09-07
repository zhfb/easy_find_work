"""应用级状态：任务运行标志 + SSE 广播总线。"""
import asyncio
import logging
from typing import AsyncIterator

logger = logging.getLogger(__name__)


class SseBroker:
    """基于 asyncio.Queue 的简单广播总线。

    publish() 向所有订阅者推送事件；subscribe() 返回异步迭代器。
    """

    def __init__(self):
        self._subscribers: list[asyncio.Queue] = []

    def publish(self, event: dict) -> None:
        """向所有活跃订阅者推送事件（非阻塞，队列满时丢弃最旧事件）。"""
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # 队列满时丢弃最旧的一条再放入，避免慢消费者阻塞发布者
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass

    async def subscribe(self) -> AsyncIterator[dict]:
        """订阅事件流，退出时自动清理订阅者。"""
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.append(q)
        try:
            while True:
                event = await q.get()
                yield event
        finally:
            if q in self._subscribers:
                self._subscribers.remove(q)


class AppState:
    """FastAPI app.state 的结构化容器。

    task_flags: {task_id: "running"|"pause"|"stop"}，TaskService 轮询检查。
    running_tasks: 当前正在运行 run_task 循环的 task_id 集合，用于并发防护。
    sse_broker: SSE 事件广播总线。
    """

    def __init__(self):
        self.task_flags: dict[int, str] = {}
        self.running_tasks: set[int] = set()
        self.sse_broker: SseBroker = SseBroker()
