import asyncio
import pytest
from app.services.browser_session import BrowserSessionManager


class FakePage:
    def __init__(self):
        self.context = object()

    async def goto(self, url, **kw):
        pass


class FakeBrowser:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.started = False
        self.stopped = False
        self.saved = False
        self.saved_ctx = None

    async def start(self):
        self.started = True

    async def new_page(self):
        return FakePage()

    async def login_status(self, page):
        return self.outcomes.pop(0)

    async def save_cookie(self, ctx):
        self.saved = True
        self.saved_ctx = ctx

    async def stop(self):
        self.stopped = True


async def make_browser_factory(outcomes):
    b = FakeBrowser(outcomes)

    async def factory():
        await b.start()
        return b

    return factory, b


@pytest.mark.asyncio
async def test_initial_state_not_started():
    bm = BrowserSessionManager()
    assert bm.state == "not_started"


@pytest.mark.asyncio
async def test_start_login_transitions_to_waiting():
    factory, fake = await make_browser_factory([])
    bm = BrowserSessionManager(browser_factory=factory)
    assert await bm.start_login() == "waiting_login"
    assert bm.state == "waiting_login"
    assert fake.started is True


@pytest.mark.asyncio
async def test_start_login_idempotent():
    factory, fake = await make_browser_factory([])
    bm = BrowserSessionManager(browser_factory=factory)
    await bm.start_login()
    await bm.start_login()  # Second call should not re-start browser
    assert fake.started is True


@pytest.mark.asyncio
async def test_tick_detects_login_and_saves_cookie():
    factory, fake = await make_browser_factory(["unknown", "logged_in"])
    bm = BrowserSessionManager(browser_factory=factory, consistent_rounds=1)
    await bm.start_login()
    assert await bm.tick() == "unknown"
    assert await bm.tick() == "logged_in"
    assert fake.saved is True


@pytest.mark.asyncio
async def test_tick_timeout():
    factory, fake = await make_browser_factory(["unknown"] * 10)
    bm = BrowserSessionManager(browser_factory=factory, consistent_rounds=1,
                               timeout_seconds=0.0)
    await bm.start_login()
    assert await bm.tick() == "timeout"


@pytest.mark.asyncio
async def test_start_failure_sets_error():
    async def bad_factory():
        raise RuntimeError("playwright missing")

    bm = BrowserSessionManager(browser_factory=bad_factory)
    assert await bm.start_login() == "error"


@pytest.mark.asyncio
async def test_check_now_expired():
    factory, fake = await make_browser_factory(["logged_in", "logged_out"])
    bm = BrowserSessionManager(browser_factory=factory, consistent_rounds=1)
    await bm.start_login()
    await bm.tick()
    assert await bm.check_now() == "expired"


@pytest.mark.asyncio
async def test_shutdown_stops_browser():
    factory, fake = await make_browser_factory(["logged_in"])
    bm = BrowserSessionManager(browser_factory=factory, consistent_rounds=1)
    await bm.start_login()
    await bm.tick()
    await bm.shutdown()
    assert fake.stopped is True
    assert bm.state == "closed"


@pytest.mark.asyncio
async def test_restart_after_closed():
    factory, fake = await make_browser_factory(["logged_in"])
    bm = BrowserSessionManager(browser_factory=factory, consistent_rounds=1)
    await bm.start_login()
    await bm.tick()
    await bm.shutdown()
    assert bm.state == "closed"
    # Restart from closed should succeed
    assert await bm.start_login() == "waiting_login"


@pytest.mark.asyncio
async def test_partial_start_failure_stops_browser():
    """If factory succeeds but new_page fails, browser must be stopped (no leak)."""
    class LeakyFakeBrowser(FakeBrowser):
        async def new_page(self):
            raise RuntimeError("page crash")

    b = LeakyFakeBrowser([])

    async def factory():
        await b.start()
        return b

    bm = BrowserSessionManager(browser_factory=factory)
    assert await bm.start_login() == "error"
    assert b.started is True
    assert b.stopped is True


@pytest.mark.asyncio
async def test_restart_login_stops_previous_browser():
    """回归：已登录后再次点「去登录」，必须先关闭旧浏览器实例再启动新的。"""
    mgr = BrowserSessionManager(browser_factory=lambda: _fake())
    # 第一次登录
    state = await mgr.start_login()
    assert state == "waiting_login"
    # 用户已登录（直接驱动状态）
    mgr._state = "logged_in"
    mgr._stop_loop()
    # 第二次点击「去登录」
    mgr._browser.stopped = False  # 重置标记
    state2 = await mgr.start_login()
    assert state2 == "waiting_login"
    assert first_browser.stopped is True, "旧浏览器必须在重启登录前关闭"


first_browser = None


async def _fake():
    global first_browser
    b = FakeBrowser([])
    if first_browser is None:
        first_browser = b
    return b
