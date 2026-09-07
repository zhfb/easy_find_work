from app.agent.llm import CircuitBreaker, LlmClient, LLMResult, LlmUnavailable

class FakeCompletions:
    def __init__(self, resp): self._resp = resp
    async def create(self, **kw):
        if callable(self._resp): return self._resp()
        return type("C", (), {"choices": [type("Ch", (), {"message": type("M", (), {"content": self._resp})()})()],
                              "usage": type("U", (), {"prompt_tokens": 10, "completion_tokens": 20})})()

class FakeChat: 
    def __init__(self, resp): self.completions = FakeCompletions(resp)

class FakeClient:
    def __init__(self, resp): self.chat = FakeChat(resp)

def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker("t", threshold=3, cooldown_seconds=600)
    for _ in range(3): cb.record_failure()
    assert cb.is_open()

async def test_complete_returns_content():
    cli = LlmClient(client=FakeClient("hi"), base_url="http://x", api_key="k", model="m")
    r = await cli.complete([{"role": "user", "content": "hi"}])
    assert r.content == "hi"
