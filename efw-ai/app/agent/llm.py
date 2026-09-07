import asyncio
import time
from dataclasses import dataclass
from openai import APIError, AsyncOpenAI

class LlmUnavailable(Exception): ...

@dataclass
class LLMResult:
    content: str; prompt_tokens: int = 0; completion_tokens: int = 0
    model: str = ""; fallback: bool = False

class CircuitBreaker:
    def __init__(self, name: str, threshold: int = 3, cooldown_seconds: int = 600):
        self.name, self.threshold, self.cooldown = name, threshold, cooldown_seconds
        self._failures = 0; self._opened_at: float | None = None
    def record_failure(self):
        self._failures += 1
        if self._failures >= self.threshold: self._opened_at = time.time()
    def record_success(self):
        self._failures = 0; self._opened_at = None
    def is_open(self) -> bool:
        if self._opened_at is None: return False
        if time.time() - self._opened_at >= self.cooldown:
            self._failures = 0; self._opened_at = None; return False
        return True

class LlmClient:
    def __init__(self, client: AsyncOpenAI | None = None, session=None,
                 base_url: str = "", api_key: str = "", model: str = ""):
        self.session = session
        self._client = client or (AsyncOpenAI(base_url=base_url or None, api_key=api_key) if api_key else None)
        self.model = model
        self.breaker = CircuitBreaker("llm")

    async def is_available(self) -> bool:
        return self._client is not None and not self.breaker.is_open()

    async def complete(self, messages, temperature=0.5, json_mode=False) -> LLMResult:
        if not await self.is_available(): raise LlmUnavailable("llm unavailable")
        try:
            extra = {"response_format": {"type": "json_object"}} if json_mode else {}
            resp = await self._client.chat.completions.create(
                model=self.model, messages=messages, temperature=temperature, **extra)
            self.breaker.record_success()
            return LLMResult(content=resp.choices[0].message.content,
                             prompt_tokens=getattr(resp.usage, "prompt_tokens", 0),
                             completion_tokens=getattr(resp.usage, "completion_tokens", 0),
                             model=self.model)
        except (APIError, asyncio.TimeoutError):
            self.breaker.record_failure()
            raise
