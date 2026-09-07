# EFW-AI 看板重构 + 登录会话 + SPA 前端实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 EFW-AI 前端从 Jinja2 模板重构为 Vue 3 SPA（6 页面全迁），新增看板发起的 Boss 登录会话子系统（修复 is_logged_in 误判）与今日状态/投递情况两个看板 API，FastAPI 单端口托管。

**Architecture:** 后端 FastAPI 只出 JSON（新增 auth/dashboard 两组 API 与 BrowserSessionManager 单例），前端 frontend/ 为 Vue 3 + Vite + vue-router + ECharts SPA，构建产物由 FastAPI 静态托管，SPA fallback 接管页面路由。

**Tech Stack:** Python 3.12+ / FastAPI / SQLModel / Playwright；Vue 3 / Vite / vue-router / ECharts / vitest。

**Spec:** `docs/superpowers/specs/2026-09-07-efw-dashboard-spa-design.md`

## Global Constraints

- 后端命令 `cd efw-ai && uv run pytest`；现有 127 个测试必须保持全绿；FastAPI 只出 JSON
- 登录状态机 8 态：`not_started / starting / waiting_login / logged_in / expired / timeout / error / closed`
- 四信号判定：A（跳转 passport 域名或 `/login` 路径）一票否决 → `logged_out`；B DOM（body 含「退出登录」）+1、C 登录态 cookie（`wt2`/`__zp_stoken__`/`last_login_phone`）+1、D wapi 接口 200 +1（`auth_probe_url` 未配置则跳过）；命中 ≥2 → `logged_in`，否则 `unknown`；连续 3 次同信号才切换状态
- **回归用例（当前 bug）**：11 个匿名 cookie（`HMACCOUNT`/`__a`/`__g`/`__c`/`__l`/`Hm_lvt_*`/`Hm_lpvt_*`/`ab_guid`/`isOHPC`/`lastCity`）必须判定 `logged_out`（无登录态 cookie 名）
- 今日投递口径：`Application.applied_at ∈ 今天` 且 `status ∈ {applied, responded, interview, offer, rejected, withdrawn}`（排除 skip 与 pending_manual）
- 8 状态枚举：`skip/pending_manual/applied/responded/interview/offer/rejected/withdrawn`
- 日限额：`ConfigItem.daily_limit` 默认 20；成本显示**累计口径**（复用 `_compute_cost_stats`），不编造今日 token 细分
- 登录轮询 5s、超时 5 分钟；`BrowserSessionManager` 挂 `app.state.browser_session`，带 asyncio 锁、幂等
- Vue 3 + Vite + vue-router + ECharts，**不引入重型组件库**；dev 代理 `/api` → `http://127.0.0.1:8000`
- 单端口托管：FastAPI `StaticFiles` 托管 `frontend/dist`；SPA fallback 排除 `/api/` 与带扩展名路径；dist 缺失时 `/` 返回 503 提示页
- `frontend/dist`、`frontend/node_modules` 进 `.gitignore`，构建产物不提交
- 提交严禁任何个人信息（用户名/邮箱/IP/密钥）；不用 emoji
- 写操作按钮 loading + toast；chat 写操作保留确认卡片机制（`confirm` 事件 → `POST /api/chat/confirm`）

---

### Task 1: 四信号登录判定修复 + BrowserSessionManager 状态机

**Files:**
- Modify: `efw-ai/app/worker/browser.py`（新增 `login_status(page) -> str` 四信号方法；`is_logged_in` 改为薄包装 `return await self.login_status(page) == "logged_in"`）
- Create: `efw-ai/app/services/browser_session.py`
- Test: `efw-ai/tests/test_browser_login.py`、`efw-ai/tests/test_browser_session.py`

**Interfaces:**
- Consumes: `app.worker.browser.BrowserManager`（现有）、`app.models.Cookie`、`app.db.engine`
- Produces:
  - `BrowserManager.login_status(self, page) -> str`（`"logged_in"|"logged_out"|"unknown"`）
  - `BrowserManager.auth_probe_url: str`（实例属性，默认 `""` = 跳过信号 D）
  - `BrowserSessionManager`：`state` 属性；`async start_login() -> str`（幂等）；`async tick() -> str`（单次轮询判定，测试驱动）；`async check_now() -> str`；`async shutdown() -> None`；`status() -> dict`（同步快照：`{"state","last_checked_at","started_at","detail"}`）；后台循环 `async _run_loop()`（每 `poll_interval` 秒调 tick，登录成功/超时/错误后退出）

- [ ] **Step 1: 写四信号判定失败测试**（`tests/test_browser_login.py`）

```python
import pytest
from app.worker.browser import BrowserManager

ANON_COOKIES = [
    {"name": "HMACCOUNT", "value": "x"}, {"name": "HMACCOUNT_BFESS", "value": "x"},
    {"name": "Hm_lvt_194df3105ad7148dcf2b98a91b5e727a", "value": "x"},
    {"name": "Hm_lpvt_194df3105ad7148dcf2b98a91b5e727a", "value": "x"},
    {"name": "__a", "value": "x"}, {"name": "__c", "value": "x"}, {"name": "__g", "value": "x"},
    {"name": "__l", "value": "x"}, {"name": "ab_guid", "value": "x"},
    {"name": "isOHPC", "value": "x"}, {"name": "lastCity", "value": "101200100"},
]

class FakeContext:
    def __init__(self, cookies): self._cookies = cookies
    async def cookies(self): return self._cookies

class FakePage:
    def __init__(self, url="https://www.zhipin.com/web/user/?ka=header-login",
                 body="", cookies=None):
        self._url = url; self._body = body; self._cookies = cookies or []
    @property
    def url(self): return self._url
    async def goto(self, url, **kw): self._url = url
    async def inner_text(self, sel, **kw): return self._body
    @property
    def context(self): return FakeContext(self._cookies)

@pytest.mark.asyncio
async def test_anon_cookies_are_not_logged_in():
    """回归：11 个匿名统计 cookie 必须判定未登录（当前 bug）。"""
    bm = BrowserManager()
    page = FakePage(body="Boss直聘-招聘求职找工作", cookies=ANON_COOKIES)
    assert await bm.login_status(page) == "logged_out"

@pytest.mark.asyncio
async def test_passport_redirect_is_logged_out():
    bm = BrowserManager()
    page = FakePage(url="https://passport.zhipin.com/login", body="")
    assert await bm.login_status(page) == "logged_out"

@pytest.mark.asyncio
async def test_login_path_is_logged_out():
    bm = BrowserManager()
    page = FakePage(url="https://www.zhipin.com/login", body="")
    assert await bm.login_status(page) == "logged_out"

@pytest.mark.asyncio
async def test_dom_and_cookie_confirm_logged_in():
    bm = BrowserManager()
    cookies = ANON_COOKIES + [{"name": "wt2", "value": "abc"}]
    page = FakePage(body="个人中心 退出登录", cookies=cookies)
    assert await bm.login_status(page) == "logged_in"

@pytest.mark.asyncio
async def test_single_signal_is_unknown():
    bm = BrowserManager()
    page = FakePage(body="个人中心 退出登录", cookies=ANON_COOKIES)
    assert await bm.login_status(page) == "unknown"

@pytest.mark.asyncio
async def test_is_logged_in_wraps_login_status():
    bm = BrowserManager()
    page = FakePage(body="个人中心 退出登录",
                    cookies=ANON_COOKIES + [{"name": "__zp_stoken__", "value": "s"}])
    assert await bm.is_logged_in(page) is True
```

- [ ] **Step 2: 运行确认失败**

Run: `cd efw-ai && uv run pytest tests/test_browser_login.py -q`
Expected: FAIL（`AttributeError: 'BrowserManager' object has no attribute 'login_status'`）

- [ ] **Step 3: 实现四信号 `login_status`**（修改 `app/worker/browser.py`）

```python
LOGIN_COOKIE_NAMES = ("wt2", "__zp_stoken__", "last_login_phone")

class BrowserManager:
    def __init__(self, data_dir="data", session=None):
        # ... 现有初始化保持不变 ...
        self.auth_probe_url = ""   # 配置信号 D 的 wapi 接口；空 = 跳过

    async def login_status(self, page) -> str:
        """四信号登录判定: A 强否定；B DOM / C cookie / D 接口 加权 ≥2 已登录。"""
        await page.goto(LOGIN_CHECK_URL, wait_until="domcontentloaded", timeout=15000)
        parsed = urlparse(page.url)
        if "passport" in parsed.netloc or parsed.path.startswith("/login"):
            return "logged_out"
        score = 0
        try:
            body = await page.inner_text("body")
            if "退出登录" in body:
                score += 1
        except Exception:
            pass
        try:
            cookies = await page.context.cookies()
            names = {c["name"] for c in cookies}
            if names & set(LOGIN_COOKIE_NAMES):
                score += 1
        except Exception:
            pass
        if self.auth_probe_url:
            try:
                resp = await page.request.get(self.auth_probe_url, timeout=8000)
                if resp.status == 401:
                    return "logged_out"
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        if data.get("zpData") or data.get("data"):
                            score += 1
                    except Exception:
                        pass
            except Exception:
                pass
        return "logged_in" if score >= 2 else "unknown"

    async def is_logged_in(self, page) -> bool:
        return await self.login_status(page) == "logged_in"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd efw-ai && uv run pytest tests/test_browser_login.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: 写 BrowserSessionManager 失败测试**（`tests/test_browser_session.py`）

```python
import asyncio
import pytest
from app.services.browser_session import BrowserSessionManager

class FakeBrowser:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes); self.started = False
        self.stopped = False; self.saved = False; self.saved_ctx = None
    async def start(self): self.started = True
    async def new_page(self): return object()
    async def login_status(self, page): return self.outcomes.pop(0)
    async def save_cookie(self, ctx): self.saved = True; self.saved_ctx = ctx
    async def stop(self): self.stopped = True

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
    await bm.start_login()   # 第二次不应重复启动浏览器
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
```

- [ ] **Step 6: 运行确认失败**

Run: `cd efw-ai && uv run pytest tests/test_browser_session.py -q`
Expected: FAIL（`ModuleNotFoundError: app.services.browser_session`）

- [ ] **Step 7: 实现 BrowserSessionManager**（创建 `app/services/browser_session.py`）

```python
"""Boss 登录会话管理：状态机 + 后台轮询 + cookie 落库。"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_TIMEOUT_SECONDS = 300
DEFAULT_CONSISTENT_ROUNDS = 3

BrowserFactory = Callable[[], Awaitable[object]]


async def _default_browser_factory():
    """真实浏览器：启动持久化上下文并绑定 DB 会话。"""
    from sqlmodel import Session
    from app.db import engine
    from app.worker.browser import BrowserManager

    bm = BrowserManager(data_dir="data", session=Session(engine))
    await bm.start()
    return bm


class BrowserSessionManager:
    def __init__(self, browser_factory: Optional[BrowserFactory] = None,
                 poll_interval: float = DEFAULT_POLL_INTERVAL,
                 timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
                 consistent_rounds: int = DEFAULT_CONSISTENT_ROUNDS):
        self._factory = browser_factory or _default_browser_factory
        self._poll_interval = poll_interval
        self._timeout_seconds = timeout_seconds
        self._consistent_rounds = consistent_rounds
        self._browser = None
        self._page = None
        self._lock = asyncio.Lock()
        self._loop_task: Optional[asyncio.Task] = None
        self._state = "not_started"
        self._started_at: Optional[str] = None
        self._last_checked_at: Optional[str] = None
        self._detail = ""
        self._signal_window: list[str] = []
        self._window_start: Optional[float] = None

    @property
    def state(self) -> str:
        return self._state

    def status(self) -> dict:
        return {
            "state": self._state,
            "last_checked_at": self._last_checked_at,
            "started_at": self._started_at,
            "detail": self._detail,
        }

    async def start_login(self) -> str:
        async with self._lock:
            if self._state in ("starting", "waiting_login"):
                return self._state
            if self._loop_task is not None and not self._loop_task.done():
                self._loop_task.cancel()
            self._state = "starting"
            self._started_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self._detail = ""
            try:
                self._browser = await self._factory()
                self._page = await self._browser.new_page()
                await self._page.goto("https://www.zhipin.com/",
                                      wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                logger.exception("browser start failed")
                self._state = "error"
                self._detail = str(exc)[:200]
                return self._state
            self._state = "waiting_login"
            self._window_start = time.monotonic()
            self._signal_window = []
            self._loop_task = asyncio.create_task(self._run_loop())
            return self._state

    async def tick(self) -> str:
        """单次轮询：四信号判定 + 状态流转。测试直接驱动。"""
        if self._state != "waiting_login":
            return self._state
        try:
            result = await self._browser.login_status(self._page)
        except Exception:
            logger.exception("login probe failed")
            result = "unknown"
        self._last_checked_at = time.strftime("%Y-%m-%d %H:%M:%S")
        self._signal_window.append(result)
        if len(self._signal_window) > self._consistent_rounds:
            self._signal_window.pop(0)
        if result == "logged_in" and self._signal_window.count("logged_in") >= self._consistent_rounds:
            await self._on_logged_in()
        elif result == "logged_out":
            # 强否定信号：立即降级（未知/失效场景由 check_now 处理）
            self._signal_window = []
        if (time.monotonic() - (self._window_start or time.monotonic())
                > self._timeout_seconds and self._state == "waiting_login"):
            self._state = "timeout"
            self._detail = "登录超时，请重新发起"
            self._stop_loop()
        return self._state

    async def _on_logged_in(self) -> None:
        try:
            await self._browser.save_cookie(self._page.context)
        except Exception:
            logger.exception("save cookie failed")
        self._state = "logged_in"
        self._detail = "登录成功，cookie 已保存"
        self._stop_loop()

    async def check_now(self) -> str:
        """立即重检：仅对已登录状态有效（发现 401 → expired）。"""
        if self._state != "logged_in":
            return self._state
        try:
            result = await self._browser.login_status(self._page)
        except Exception:
            logger.exception("recheck failed")
            result = "unknown"
        self._last_checked_at = time.strftime("%Y-%m-%d %H:%M:%S")
        if result in ("logged_out", "unknown"):
            self._state = "expired"
            self._detail = "登录态已失效，请重新登录"
        return self._state

    async def _run_loop(self) -> None:
        while self._state == "waiting_login":
            await asyncio.sleep(self._poll_interval)
            try:
                await self.tick()
            except Exception:
                logger.exception("tick failed in loop")

    def _stop_loop(self) -> None:
        if self._loop_task is not None and not self._loop_task.done():
            self._loop_task.cancel()

    async def shutdown(self) -> None:
        self._stop_loop()
        if self._browser is not None:
            try:
                await self._browser.stop()
            except Exception:
                logger.exception("browser stop failed")
        self._state = "not_started"
```

- [ ] **Step 8: 运行确认通过**

Run: `cd efw-ai && uv run pytest tests/test_browser_session.py tests/test_browser_login.py -q`
Expected: PASS（8 + 6 passed）；随后 `uv run pytest -q` 全量仍通过（127+14）

- [ ] **Step 9: Commit**

```bash
git add efw-ai/app/worker/browser.py efw-ai/app/services/browser_session.py \
        efw-ai/tests/test_browser_login.py efw-ai/tests/test_browser_session.py
git commit -m "feat: 四信号登录判定 + 浏览器登录会话状态机"
```

---

### Task 2: auth API（status / login / check）

**Files:**
- Create: `efw-ai/app/api/auth.py`
- Modify: `efw-ai/app/main.py`（lifespan 初始化/关闭 `app.state.browser_session`；`include_router(auth_api.router, prefix="/api")`）
- Test: `efw-ai/tests/test_auth_api.py`

**Interfaces:**
- Consumes: `BrowserSessionManager`（Task 1：`start_login/check_now/status/shutdown`）
- Produces:
  - `GET /api/auth/status` → `{"state","last_checked_at","started_at","detail"}`
  - `POST /api/auth/login` → `{"state","message"}`（幂等）
  - `POST /api/auth/check` → `{"state","message"}`
  - `app.state.browser_session`（lifespan 中创建，shutdown 时 `await browser_session.shutdown()`）

- [ ] **Step 1: 写失败测试**（`tests/test_auth_api.py`）

```python
import pytest
from fastapi.testclient import TestClient


class FakeBrowserSession:
    def __init__(self, state="not_started"):
        self._state = state; self.calls = []
    @property
    def state(self): return self._state
    def status(self):
        return {"state": self._state, "last_checked_at": None,
                "started_at": None, "detail": ""}
    async def start_login(self):
        self.calls.append("start_login"); self._state = "waiting_login"
        return self._state
    async def check_now(self):
        self.calls.append("check_now"); self._state = "expired"
        return self._state
    async def shutdown(self): self.calls.append("shutdown")


@pytest.fixture()
def auth_client(client, monkeypatch):
    from app.main import app
    monkeypatch.setattr(app.state, "browser_session", FakeBrowserSession())
    return client


def test_status_not_started(auth_client):
    resp = auth_client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json()["state"] == "not_started"


def test_login_starts_and_returns_state(auth_client):
    resp = auth_client.post("/api/auth/login")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "waiting_login"
    assert data["message"]


def test_check_now_updates_state(auth_client):
    auth_client.post("/api/auth/login")
    resp = auth_client.post("/api/auth/check")
    assert resp.status_code == 200
    assert resp.json()["state"] == "expired"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd efw-ai && uv run pytest tests/test_auth_api.py -q`
Expected: FAIL（404，路由不存在）

- [ ] **Step 3: 实现 auth API**（创建 `app/api/auth.py`）

```python
"""Boss 登录会话 API：状态查询、发起登录、立即重检。"""
from fastapi import APIRouter, Request

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
```

（补：文件顶部 `from fastapi import HTTPException`。`main.py` 中删除既有 `/api/health` 之外的模板路由不动，仅加 lifespan + 挂载。若 `main.py` 无 lifespan，按现有 app 创建方式新增 `@asynccontextmanager` lifespan。）

- [ ] **Step 4: main.py 挂载（lifespan + router）**

在 `app/main.py` 中：

```python
from contextlib import asynccontextmanager
from app.api import auth as auth_api
from app.services.browser_session import BrowserSessionManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.browser_session = BrowserSessionManager()
    yield
    await app.state.browser_session.shutdown()

app = FastAPI(lifespan=lifespan)   # 若 app 已定义，改为在既有定义处传入 lifespan
...
app.include_router(auth_api.router, prefix="/api")
```

- [ ] **Step 5: 运行确认通过**

Run: `cd efw-ai && uv run pytest tests/test_auth_api.py -q`
Expected: PASS（3 passed）；全量回归 `uv run pytest -q`（127+14+3=144 全绿）

- [ ] **Step 6: Commit**

```bash
git add efw-ai/app/api/auth.py efw-ai/app/main.py efw-ai/tests/test_auth_api.py
git commit -m "feat: auth API（登录状态/发起登录/立即重检）"
```

---

### Task 3: dashboard API（today + deliveries）

**Files:**
- Create: `efw-ai/app/services/dashboard_service.py`
- Create: `efw-ai/app/api/dashboard.py`
- Modify: `efw-ai/app/main.py`（`include_router(dashboard_api.router, prefix="/api")`）
- Test: `efw-ai/tests/test_dashboard_service.py`、`efw-ai/tests/test_dashboard_api.py`

**Interfaces:**
- Consumes: `app.models.{Application, Task, ConfigItem, ApplicationEvent}`、`get_today_stats` 口径（新实现）、`_compute_cost_stats`（main.py 中函数——**Task 3 把成本统计逻辑抽到 `dashboard_service`**，main.py 后续 Task 7 删除模板时不再依赖）
- Produces:
  - `get_today(session) -> dict`：`{"delivered_today","daily_limit","remaining_ratio","running_tasks","paused_tasks","pending_followup","interview_offer","total_tokens","total_cost","price_per_1k","recent_events":[{id,event_type,detail,created_at}]}`
  - `get_deliveries(session, days=7) -> dict`：`{"trend":[{date,count}],"status_today":{...},"status_total":{...},"pending_manual_count","per_task":[{task_id,name,count}]}`
  - `GET /api/dashboard/today`、`GET /api/dashboard/deliveries?days=7`（返回上述 dict）

- [ ] **Step 1: 写失败测试**（`tests/test_dashboard_service.py`，复用 conftest `session` fixture）

```python
from datetime import date, timedelta
from app.models import Application, Task, ConfigItem, ApplicationEvent
from app.services.dashboard_service import get_today, get_deliveries

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def seed(session):
    t1 = Task(name="t1", status="running"); t2 = Task(name="t2", status="paused")
    session.add_all([t1, t2]); session.commit()
    session.add(ConfigItem(key="daily_limit", value="20")); session.commit()
    apps = [
        Application(job_id=1, task_id=t1.id, status="applied", applied_at=TODAY),
        Application(job_id=2, task_id=t1.id, status="responded", applied_at=TODAY),
        Application(job_id=3, task_id=t1.id, status="pending_manual", applied_at=TODAY),
        Application(job_id=4, task_id=t2.id, status="applied", applied_at=YESTERDAY),
        Application(job_id=5, task_id=t2.id, status="skip", applied_at=YESTERDAY),
    ]
    session.add_all(apps); session.commit()
    for i in range(3):
        session.add(ApplicationEvent(application_id=1, event_type="llm_usage",
                                     detail=f'{{"tokens":{i}}}',
                                     created_at=f"{TODAY} 10:0{i}:00"))
    session.commit()


def test_get_today_delivered_excludes_pending_manual(session):
    seed(session)
    data = get_today(session)
    assert data["delivered_today"] == 2          # applied + responded（pending_manual 不算）
    assert data["daily_limit"] == 20
    assert data["remaining_ratio"] == 0.9
    assert data["running_tasks"] == 1
    assert data["paused_tasks"] == 1
    assert data["pending_followup"] == 1
    assert data["interview_offer"] == 0
    assert len(data["recent_events"]) == 3


def test_get_deliveries_trend_pads_zero_days(session):
    seed(session)
    data = get_deliveries(session, days=7)
    assert len(data["trend"]) == 7
    assert data["trend"][-1]["count"] == 2
    assert sum(t["count"] for t in data["trend"]) == 3   # 昨天 1 + 今天 2


def test_get_deliveries_status_totals(session):
    seed(session)
    data = get_deliveries(session, days=7)
    assert data["status_total"]["applied"] == 2          # 今天1 + 昨天1
    assert data["status_total"]["pending_manual"] == 1
    assert data["status_today"]["applied"] == 1
    assert data["pending_manual_count"] == 1
    assert len(data["per_task"]) == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `cd efw-ai && uv run pytest tests/test_dashboard_service.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 dashboard_service**（创建 `app/services/dashboard_service.py`）

```python
"""看板统计服务：今日状态与投递情况（纯 SQL 聚合，可单测）。"""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlmodel import Session, select, func

from ..models import Application, Task, ConfigItem, ApplicationEvent

DELIVERED_STATUSES = ("applied", "responded", "interview", "offer", "rejected", "withdrawn")
STATUS_ENUM = ("skip", "pending_manual", "applied", "responded", "interview",
               "offer", "rejected", "withdrawn")


def _count_by_status(session, start=None, end=None) -> dict:
    q = select(Application.status, func.count(Application.id))
    if start is not None:
        q = q.where(Application.applied_at >= start)
    if end is not None:
        q = q.where(Application.applied_at < end)
    rows = session.exec(q.group_by(Application.status)).all()
    dist = {s: 0 for s in STATUS_ENUM}
    for status, count in rows:
        dist[status] = count
    return dist


def get_today(session: Session) -> dict:
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    status_today = _count_by_status(session, today, tomorrow)
    delivered = sum(status_today[s] for s in DELIVERED_STATUSES)
    raw_limit = session.exec(
        select(ConfigItem).where(ConfigItem.key == "daily_limit")
    ).first()
    daily_limit = int(raw_limit.value) if raw_limit and raw_limit.value.isdigit() else 20
    running = session.exec(
        select(func.count(Task.id)).where(Task.status == "running")
    ).one()
    paused = session.exec(
        select(func.count(Task.id)).where(Task.status == "paused")
    ).one()
    followup = session.exec(
        select(func.count(Application.id)).where(Application.status == "responded")
    ).one()
    io = session.exec(
        select(func.count(Application.id)).where(Application.status.in_(("interview", "offer")))
    ).one()
    events = session.exec(
        select(ApplicationEvent).order_by(ApplicationEvent.id.desc()).limit(10)
    ).all()
    return {
        "delivered_today": delivered,
        "daily_limit": daily_limit,
        "remaining_ratio": round(1 - delivered / daily_limit, 3) if daily_limit else 0.0,
        "running_tasks": running,
        "paused_tasks": paused,
        "pending_followup": followup,
        "interview_offer": io,
        "total_tokens": _compute_cost(session)["total_tokens"],
        "total_cost": _compute_cost(session)["estimated_cost"],
        "price_per_1k": _compute_cost(session)["price_per_1k"],
        "recent_events": [
            {"id": e.id, "event_type": e.event_type, "detail": e.detail,
             "created_at": e.created_at}
            for e in events
        ],
    }


def _compute_cost(session: Session) -> dict:
    total_prompt = total_completion = 0
    items = session.exec(
        select(ConfigItem).where(ConfigItem.key.like("ai_tokens_%"))
    ).all()
    for item in items:
        try:
            data = json.loads(item.value) if item.value else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        total_prompt += data.get("prompt_tokens", 0)
        total_completion += data.get("completion_tokens", 0)
    price_raw = session.exec(
        select(ConfigItem).where(ConfigItem.key == "price_per_1k")
    ).first()
    try:
        price = float(price_raw.value) if price_raw else 0.0
    except (ValueError, TypeError):
        price = 0.0
    total_tokens = total_prompt + total_completion
    return {"total_tokens": total_tokens, "estimated_cost": round(total_tokens / 1000 * price, 6),
            "price_per_1k": price}


def get_deliveries(session: Session, days: int = 7) -> dict:
    today = date.today()
    start = (today - timedelta(days=days - 1)).isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()
    rows = session.exec(
        select(Application.applied_at, func.count(Application.id))
        .where(Application.applied_at >= start)
        .where(Application.applied_at < tomorrow)
        .where(Application.status.in_(DELIVERED_STATUSES))
        .group_by(Application.applied_at)
    ).all()
    counts = dict(rows)
    trend = [
        {"date": (today - timedelta(days=days - 1 - i)).isoformat(),
         "count": counts.get((today - timedelta(days=days - 1 - i)).isoformat(), 0)}
        for i in range(days)
    ]
    per_task_rows = session.exec(
        select(Application.task_id, func.count(Application.id))
        .where(Application.status.in_(DELIVERED_STATUSES))
        .group_by(Application.task_id)
    ).all()
    per_task = []
    for task_id, count in per_task_rows:
        t = session.get(Task, task_id)
        per_task.append({"task_id": task_id,
                         "name": t.name if t else f"#{task_id}", "count": count})
    return {
        "trend": trend,
        "status_today": _count_by_status(session, today.isoformat(), tomorrow),
        "status_total": _count_by_status(session),
        "pending_manual_count": session.exec(
            select(func.count(Application.id)).where(Application.status == "pending_manual")
        ).one(),
        "per_task": per_task,
    }
```

- [ ] **Step 4: 写 API 失败测试**（`tests/test_dashboard_api.py`）

```python
import pytest


@pytest.fixture()
def seed_via_client(client):
    from app.models import Application, Task, ConfigItem
    from sqlmodel import Session
    from app.db import engine
    from datetime import date
    with Session(engine) as s:
        t = Task(name="t", status="running"); s.add(t); s.commit()
        s.add(ConfigItem(key="daily_limit", value="20"))
        s.add(Application(job_id=1, task_id=t.id, status="applied", applied_at=date.today().isoformat()))
        s.commit()
    return client


def test_dashboard_today(seed_via_client):
    resp = seed_via_client.get("/api/dashboard/today")
    assert resp.status_code == 200
    data = resp.json()
    assert data["delivered_today"] == 1
    assert data["running_tasks"] == 1
    assert "recent_events" in data


def test_dashboard_deliveries(seed_via_client):
    resp = seed_via_client.get("/api/dashboard/deliveries?days=7")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["trend"]) == 7
    assert data["status_total"]["applied"] == 1
```

- [ ] **Step 5: 实现 dashboard API 并挂载**

创建 `app/api/dashboard.py`：

```python
from fastapi import APIRouter, Depends
from sqlmodel import Session
from ..db import get_session
from ..services.dashboard_service import get_today, get_deliveries

router = APIRouter()


@router.get("/dashboard/today")
def dashboard_today(session: Session = Depends(get_session)) -> dict:
    return get_today(session)


@router.get("/dashboard/deliveries")
def dashboard_deliveries(days: int = 7, session: Session = Depends(get_session)) -> dict:
    return get_deliveries(session, days=days)
```

`main.py`：`app.include_router(dashboard_api.router, prefix="/api")`。

- [ ] **Step 6: 运行确认通过**

Run: `cd efw-ai && uv run pytest tests/test_dashboard_service.py tests/test_dashboard_api.py -q`
Expected: PASS；全量 `uv run pytest -q`（144+5=149 全绿）

- [ ] **Step 7: Commit**

```bash
git add efw-ai/app/services/dashboard_service.py efw-ai/app/api/dashboard.py \
        efw-ai/app/main.py efw-ai/tests/test_dashboard_service.py efw-ai/tests/test_dashboard_api.py
git commit -m "feat: 看板今日状态与投递情况 API"
```

---

### Task 4: 前端脚手架 + 布局 + 登录状态条

**Files:**
- Create: `efw-ai/frontend/package.json`、`efw-ai/frontend/vite.config.js`、`efw-ai/frontend/index.html`
- Create: `efw-ai/frontend/src/main.js`、`efw-ai/frontend/src/App.vue`、`efw-ai/frontend/src/router/index.js`
- Create: `efw-ai/frontend/src/api/client.js`、`efw-ai/frontend/src/styles/global.css`
- Create: `efw-ai/frontend/src/utils/login.js`、`efw-ai/frontend/src/components/LoginStatusBar.vue`
- Create: `efw-ai/frontend/tests/login.test.js`、`efw-ai/frontend/tests/client.test.js`
- Test: `cd efw-ai/frontend && npm test`（vitest）；验收 `npm run build`

**Interfaces:**
- Consumes: `GET /api/auth/status`、`POST /api/auth/login`、`POST /api/auth/check`（Task 2）
- Produces:
  - `src/api/client.js`: `get(url)` / `post(url, body?)`，统一 JSON 解析与错误抛出
  - `src/utils/login.js`: `loginStateMeta(state) -> {label, tone, action}`
  - `App.vue`: 顶部导航（看板/投递记录/半自动清单/智能助手/配置）+ 常驻 `<LoginStatusBar />`
  - `router/index.js`: 6 路由（`/`→Dashboard、`/applications`、`/semi-queue`、`/tasks/:id`、`/config`、`/chat`），占位组件先给空 `views/*.vue`（Task 5/6 填充）

- [ ] **Step 1: 脚手架 + 依赖安装**

创建 `package.json`：

```json
{
  "name": "efw-ai-frontend",
  "private": true,
  "type": "module",
  "scripts": { "dev": "vite", "build": "vite build", "test": "vitest run" }
}
```

运行：`cd efw-ai/frontend && npm install vue vue-router echarts && npm install -D vite @vitejs/plugin-vue vitest jsdom`

创建 `vite.config.js`：

```js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  plugins: [vue()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  test: { environment: 'jsdom' },
})
```

创建 `index.html`：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>EFW-AI 智能投递助手</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.js"></script>
</body>
</html>
```

- [ ] **Step 2: 写 api client 失败测试**（`tests/client.test.js`）

```js
import { describe, it, expect, vi, afterEach } from 'vitest'
import { get, post } from '../src/api/client.js'

function mockFetch(status, body, contentType = 'application/json') {
  global.fetch = vi.fn().mockResolvedValue({
    ok: status < 400,
    status,
    statusText: 'Error',
    headers: { get: () => contentType },
    json: async () => body,
    text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
  })
}

afterEach(() => { vi.restoreAllMocks() })

describe('api client', () => {
  it('get 解析 JSON', async () => {
    mockFetch(200, { state: 'logged_in' })
    const data = await get('/api/auth/status')
    expect(data).toEqual({ state: 'logged_in' })
    expect(global.fetch).toHaveBeenCalledWith('/api/auth/status', expect.objectContaining({}))
  })

  it('get 非 2xx 抛出 detail', async () => {
    mockFetch(404, { detail: 'not found' })
    await expect(get('/api/x')).rejects.toThrow('not found')
  })

  it('post 携带 JSON body', async () => {
    mockFetch(200, { ok: true })
    await post('/api/auth/login', {})
    const [, opts] = global.fetch.mock.calls[0]
    expect(opts.method).toBe('POST')
    expect(opts.body).toBe('{}')
  })
})
```

- [ ] **Step 3: 运行确认失败**

Run: `cd efw-ai/frontend && npm test`
Expected: FAIL（找不到 `../src/api/client.js` 模块）

- [ ] **Step 4: 实现 api client**（创建 `src/api/client.js`）

```js
async function request(url, options = {}) {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      const data = await resp.json()
      if (data && data.detail) detail = data.detail
    } catch (e) { /* 非 JSON 错误体，保留 statusText */ }
    throw new Error(detail)
  }
  const ct = resp.headers.get('content-type') || ''
  return ct.includes('application/json') ? resp.json() : resp.text()
}

export const get = (url) => request(url)
export const post = (url, body) =>
  request(url, { method: 'POST', body: body ? JSON.stringify(body) : undefined })
```

- [ ] **Step 5: 写 login 状态映射失败测试**（`tests/login.test.js`）

```js
import { describe, it, expect } from 'vitest'
import { loginStateMeta } from '../src/utils/login.js'

describe('loginStateMeta', () => {
  it('覆盖 8 个状态', () => {
    for (const s of ['not_started', 'starting', 'waiting_login', 'logged_in',
                     'expired', 'timeout', 'error', 'closed']) {
      const meta = loginStateMeta(s)
      expect(meta.label).toBeTruthy()
      expect(meta.tone).toBeTruthy()
    }
  })
  it('未登录显示去登录动作', () => {
    expect(loginStateMeta('not_started')).toEqual(
      expect.objectContaining({ label: '未登录', action: '去登录' }))
  })
  it('已登录显示重新检测动作', () => {
    expect(loginStateMeta('logged_in').action).toBe('重新检测')
  })
  it('未知状态回退中性', () => {
    expect(loginStateMeta('whatever').tone).toBe('neutral')
  })
})
```

- [ ] **Step 6: 实现 login.js**（创建 `src/utils/login.js`）

```js
export function loginStateMeta(state) {
  const map = {
    not_started:  { label: '未登录', tone: 'danger', action: '去登录' },
    starting:     { label: '正在启动浏览器…', tone: 'warning', action: null },
    waiting_login: { label: '请在弹出窗口完成登录', tone: 'warning', action: null },
    logged_in:    { label: '已登录', tone: 'success', action: '重新检测' },
    expired:      { label: '登录已过期', tone: 'warning', action: '重新登录' },
    timeout:      { label: '登录超时', tone: 'danger', action: '重试登录' },
    error:        { label: '浏览器启动失败', tone: 'danger', action: '重试' },
    closed:       { label: '窗口已关闭', tone: 'warning', action: '重新登录' },
  }
  return map[state] || { label: state, tone: 'neutral', action: null }
}
```

- [ ] **Step 7: 布局 + 路由 + 登录状态条**

创建 `src/styles/global.css`（沿用主色 `#1a1a2e`，浅色背景，响应式）：

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
:root {
  --bg: #f5f7fa; --card: #fff; --ink: #1a1a2e; --muted: #6b7280;
  --border: rgba(0,0,0,0.08); --success: #10b981; --warning: #f59e0b;
  --danger: #ef4444; --primary: #1a1a2e;
}
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: #333; }
header.app-header { background: var(--primary); color: #fff; padding: 0 24px; }
header.app-header .inner { max-width: 1100px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
nav a { color: #ccc; text-decoration: none; padding: 8px 14px; border-radius: 6px; font-size: 14px; }
nav a.router-link-active { background: rgba(255,255,255,0.15); color: #fff; }
main { max-width: 1100px; margin: 24px auto; padding: 0 16px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 16px; }
@media (max-width: 640px) { header.app-header .inner { flex-direction: column; align-items: flex-start; } nav { width: 100%; overflow-x: auto; } }
```

创建 `src/router/index.js`：

```js
import { createRouter, createWebHistory } from 'vue-router'
const routes = [
  { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
  { path: '/applications', name: 'applications', component: () => import('../views/ApplicationsView.vue') },
  { path: '/semi-queue', name: 'semiQueue', component: () => import('../views/SemiQueueView.vue') },
  { path: '/tasks/:id', name: 'taskDetail', component: () => import('../views/TaskDetailView.vue') },
  { path: '/config', name: 'config', component: () => import('../views/ConfigView.vue') },
  { path: '/chat', name: 'chat', component: () => import('../views/ChatView.vue') },
]
export default createRouter({ history: createWebHistory(), routes })
```

创建 `src/main.js`：

```js
import { createApp } from 'vue'
import App from './App.vue'
import router from './router/index.js'
import './styles/global.css'
createApp(App).use(router).mount('#app')
```

创建 `src/components/LoginStatusBar.vue`（轮询 `/api/auth/status` 5s；按钮按 `meta.action` 触发 login/check）：

```vue
<template>
  <div class="login-bar" :class="'tone-' + meta.tone">
    <span class="dot"></span>
    <span>{{ meta.label }}</span>
    <span v-if="lastChecked" class="muted">最后检测 {{ lastChecked }}</span>
    <button v-if="meta.action" class="btn" :disabled="busy" @click="act">
      {{ busy ? '处理中…' : meta.action }}
    </button>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { get, post } from '../api/client.js'
import { loginStateMeta } from '../utils/login.js'

const state = ref('not_started')
const lastChecked = ref('')
const busy = ref(false)
const meta = computed(() => loginStateMeta(state.value))
let timer = null

async function refresh() {
  try {
    const data = await get('/api/auth/status')
    state.value = data.state
    if (data.last_checked_at) lastChecked.value = data.last_checked_at.slice(11, 16)
  } catch (e) { /* 后端未起：保持当前状态 */ }
}
async function act() {
  busy.value = true
  try {
    if (state.value === 'logged_in') await post('/api/auth/check')
    else await post('/api/auth/login')
    await refresh()
  } catch (e) { alert('操作失败: ' + e.message) } finally { busy.value = false }
}
onMounted(() => { refresh(); timer = setInterval(refresh, 5000) })
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.login-bar { display: flex; align-items: center; gap: 10px; background: var(--card);
  border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px;
  margin-bottom: 16px; font-size: 13px; flex-wrap: wrap; }
.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.tone-danger .dot { background: var(--danger); } .tone-warning .dot { background: var(--warning); }
.tone-success .dot { background: var(--success); } .tone-neutral .dot { background: var(--muted); }
.muted { color: var(--muted); font-size: 12px; }
.btn { margin-left: auto; padding: 4px 14px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--primary); color: #fff; cursor: pointer; font-size: 12px; }
</style>
```

创建 `src/App.vue`（导航 + 登录条 + router-view）：

```vue
<template>
  <header class="app-header">
    <div class="inner">
      <h1 style="font-size:18px;padding:16px 0;">EFW-AI 智能投递助手</h1>
      <nav>
        <router-link to="/">看板</router-link>
        <router-link to="/applications">投递记录</router-link>
        <router-link to="/semi-queue">半自动清单</router-link>
        <router-link to="/chat">智能助手</router-link>
        <router-link to="/config">配置</router-link>
      </nav>
    </div>
  </header>
  <main>
    <LoginStatusBar />
    <router-view />
  </main>
</template>

<script setup>
import LoginStatusBar from './components/LoginStatusBar.vue'
</script>
```

- [ ] **Step 8: 测试 + 构建验证**

Run: `cd efw-ai/frontend && npm test && npm run build`
Expected: PASS（6 tests）+ build 产物 `frontend/dist/index.html` 生成

- [ ] **Step 9: Commit**

```bash
git add efw-ai/frontend/
git commit -m "feat: 前端脚手架（Vue3+Vite+路由+登录状态条）"
```

---

### Task 5: 看板页（DashboardView + 统计组件）

**Files:**
- Create: `efw-ai/frontend/src/views/DashboardView.vue`
- Create: `efw-ai/frontend/src/components/StatCard.vue`、`TrendChart.vue`、`StatusDistribution.vue`、`EventTimeline.vue`、`TaskTable.vue`
- Create: `efw-ai/frontend/src/utils/dashboard.js`、`efw-ai/frontend/tests/dashboard.test.js`
- Test: `cd efw-ai/frontend && npm test`；验收 `npm run build`

**Interfaces:**
- Consumes: `GET /api/dashboard/today`、`GET /api/dashboard/deliveries?days=7`（Task 3）、`GET /api/tasks` + 既有任务控制接口（启动/暂停/继续/停止/崩溃续跑，POST `/api/tasks/{id}/start|pause|resume|stop|resume-after-crash`）
- Produces:
  - `src/utils/dashboard.js`: `STATUS_LABELS`、`statusEntries(dist) -> [{key,label,value}]`、`mapTrend(trend) -> {dates, counts}`
  - `DashboardView.vue` 组装：StatCard ×5、TrendChart、StatusDistribution、EventTimeline、TaskTable

- [ ] **Step 1: 写数据映射失败测试**（`tests/dashboard.test.js`）

```js
import { describe, it, expect } from 'vitest'
import { STATUS_LABELS, statusEntries, mapTrend } from '../src/utils/dashboard.js'

describe('dashboard utils', () => {
  it('状态标签覆盖 8 态', () => {
    expect(Object.keys(STATUS_LABELS)).toHaveLength(8)
    expect(STATUS_LABELS.applied).toBe('已投递')
  })
  it('statusEntries 转有序列表', () => {
    const rows = statusEntries({ applied: 3, skip: 2 })
    expect(rows[0]).toEqual({ key: 'applied', label: '已投递', value: 3 })
  })
  it('mapTrend 拆日期与数值', () => {
    const t = mapTrend([{ date: '2026-09-01', count: 2 }, { date: '2026-09-02', count: 0 }])
    expect(t.dates).toEqual(['2026-09-01', '2026-09-02'])
    expect(t.counts).toEqual([2, 0])
  })
})
```

- [ ] **Step 2: 运行确认失败** → 创建 `src/utils/dashboard.js` 实现，`npm test` PASS（dashboard utils）

```js
export const STATUS_LABELS = {
  skip: '跳过', pending_manual: '待人工确认', applied: '已投递', responded: 'HR 回复',
  interview: '面试', offer: 'Offer', rejected: '被拒', withdrawn: '撤回',
}
export function statusEntries(dist) {
  return Object.entries(dist || {}).map(([key, value]) => ({
    key, label: STATUS_LABELS[key] || key, value,
  }))
}
export function mapTrend(trend) {
  return { dates: (trend || []).map(t => t.date), counts: (trend || []).map(t => t.count) }
}
```

- [ ] **Step 3: 创建统计组件**

`StatCard.vue`（props: `label/value/sub/tone`）：

```vue
<template>
  <div class="stat-card">
    <div class="label">{{ label }}</div>
    <div class="value">{{ value }} <span v-if="sub" class="sub">{{ sub }}</span></div>
  </div>
</template>
<script setup>
defineProps({ label: String, value: [String, Number], sub: String, tone: String })
</script>
<style scoped>
.stat-card { flex: 1 1 150px; min-width: 0; background: var(--card);
  border: 1px solid var(--border); border-radius: 12px; padding: 14px; box-sizing: border-box; }
.label { font-size: 12px; color: var(--muted); } .value { font-size: 22px; font-weight: 700; margin-top: 4px; }
.sub { font-size: 12px; color: var(--muted); font-weight: 400; }
</style>
```

`TrendChart.vue`（ECharts 折线，onMounted init + resize 监听 + 卸载 dispose）：

```vue
<template><div ref="el" style="width:100%;height:240px;"></div></template>
<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as echarts from 'echarts'
const props = defineProps({ dates: Array, counts: Array })
const el = ref(null)
let chart = null
function render() {
  if (!chart) return
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 20, bottom: 28 },
    xAxis: { type: 'category', data: props.dates, axisLabel: { color: '#6b7280', fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: '#6b7280', fontSize: 11 } },
    series: [{
      type: 'line', smooth: true, data: props.counts,
      itemStyle: { color: '#1a1a2e' }, lineStyle: { color: '#1a1a2e', width: 2 },
      areaStyle: { color: 'rgba(26,26,46,0.06)' },
    }],
  })
}
onMounted(() => { chart = echarts.init(el.value); render(); window.addEventListener('resize', onResize) })
onBeforeUnmount(() => { window.removeEventListener('resize', onResize); if (chart) chart.dispose() })
function onResize() { if (chart) chart.resize() }
watch(() => [props.dates, props.counts], render, { deep: true })
</script>
```

`StatusDistribution.vue`（props: `entries`，柱状列表）、`EventTimeline.vue`（props: `events`，时间线）、`TaskTable.vue`（props: `tasks`，行内操作按钮触发 `taskAction(id, action)` emit）——三个组件样式同 StatCard 体系，状态色映射沿用 base 配色（running=蓝、paused=黄、finished/stopped/failed 红绿等）。

- [ ] **Step 4: 创建 DashboardView.vue**

```vue
<template>
  <div>
    <div class="cards">
      <StatCard label="今日投递" :value="today.delivered_today" :sub="`/ ${today.daily_limit} 配额`"
                :tone="today.remaining_ratio < 0.2 ? 'warning' : ''" />
      <StatCard label="运行中任务" :value="today.running_tasks" :sub="`暂停 ${today.paused_tasks}`" />
      <StatCard label="待跟进回复" :value="today.pending_followup" />
      <StatCard label="面试 + Offer" :value="today.interview_offer" />
      <StatCard label="累计成本" :value="'¥' + today.total_cost" :sub="`${today.total_tokens} tokens`" />
    </div>

    <div class="row">
      <div class="card" style="flex:2 1 400px;">
        <h3 style="font-size:14px;margin-bottom:10px;">近 7 天投递趋势</h3>
        <TrendChart :dates="trend.dates" :counts="trend.counts" />
      </div>
      <div class="card" style="flex:1 1 260px;">
        <h3 style="font-size:14px;margin-bottom:10px;">8 状态分布（累计）</h3>
        <StatusDistribution :entries="statusTotal" />
      </div>
    </div>

    <div class="row">
      <div class="card" style="flex:1 1 320px;">
        <h3 style="font-size:14px;margin-bottom:10px;">最近事件</h3>
        <EventTimeline :events="today.recent_events" />
      </div>
      <div class="card" style="flex:2 1 400px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <h3 style="font-size:14px;">任务列表</h3>
          <router-link to="/config" class="btn" style="font-size:12px;">+ 新建任务（配置页）</router-link>
        </div>
        <TaskTable :tasks="tasks" @action="taskAction" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { get } from '../api/client.js'
import StatCard from '../components/StatCard.vue'
import TrendChart from '../components/TrendChart.vue'
import StatusDistribution from '../components/StatusDistribution.vue'
import EventTimeline from '../components/EventTimeline.vue'
import TaskTable from '../components/TaskTable.vue'
import { statusEntries, mapTrend } from '../utils/dashboard.js'

const today = ref({ delivered_today: 0, daily_limit: 20, running_tasks: 0, paused_tasks: 0,
                    pending_followup: 0, interview_offer: 0, total_cost: 0, total_tokens: 0,
                    recent_events: [] })
const trend = ref({ dates: [], counts: [] })
const statusTotal = ref([])
const tasks = ref([])

async function load() {
  try {
    const [t, d] = await Promise.all([get('/api/dashboard/today'), get('/api/dashboard/deliveries?days=7')])
    today.value = t
    trend.value = mapTrend(d.trend)
    statusTotal.value = statusEntries(d.status_total)
    tasks.value = (await get('/api/tasks')).tasks || []
  } catch (e) { alert('加载失败: ' + e.message) }
}
async function taskAction(id, action) {
  try { await post(`/api/tasks/${id}/${action}`); await load() }
  catch (e) { alert('操作失败: ' + e.message) }
}
onMounted(load)
</script>

<style scoped>
.cards { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
.row { display: flex; gap: 16px; flex-wrap: wrap; }
</style>
```

（实现时确保 `TaskTable.vue` 包含启动/暂停/继续/停止/崩溃续跑按钮，映射现有 task.status 6 态；`post` 从 `api/client.js` 导入。）

- [ ] **Step 5: 测试 + 构建验证**

Run: `cd efw-ai/frontend && npm test && npm run build`
Expected: PASS + build 通过

- [ ] **Step 6: Commit**

```bash
git add efw-ai/frontend/
git commit -m "feat: 看板页（统计卡/趋势图/状态分布/事件时间线/任务列表）"
```

---

### Task 6: 其余 5 页迁移（复用现有 API）

**Files:**
- Create: `efw-ai/frontend/src/views/ApplicationsView.vue`、`SemiQueueView.vue`、`TaskDetailView.vue`、`ConfigView.vue`、`ChatView.vue`
- Test: 构建验证（组件无单测，纯 API 消费）；`npm run build`

**Interfaces（现有 API 协议，已核实）：**
- 投递记录：`GET /api/applications?task_id=&status=&limit=100` → `{"applications":[{id,job_id,task_id,mode,decision,match_score,llm_reason,message,status,applied_at,updated_at,job_title,company,salary_text,city,job_url}]}`；改状态 `POST /api/applications/{id}/status` body `{"status","detail":""}`
- 半自动清单：同上，`status=pending_manual` 过滤；确认投递 → `POST /api/applications/{id}/status {"status":"applied"}`；跳过 → `{"status":"skip"}`；重写消息 → `POST /api/applications/{id}/regenerate-message` → `{"messages":[str]}`（前端展示 3 条候选让用户选，选定后 `POST .../status {"status":"applied","detail":"<选中的消息>"}`）
- 任务详情：`GET /api/tasks/{id}` → `{"id,name,keywords,city,mode,max_deliveries,daily_limit,match_threshold,rules,status,last_job_id,created_at,finished_at,application_stats,application_count}`；SSE `GET /api/tasks/{id}/events`（EventSource，`data: {json}` 行）；控制 `POST /api/tasks/{id}/start|pause|resume|stop|resume-after-crash`
- 配置：`GET /api/config` → `{key: value_str}`（值为字符串，JSON 需前端解析）；`PUT /api/config` body `{"key","value"}`；画像 `GET/PUT /api/profile`（ProfileIn 字段：skills/experience_years/expected_salary_min/expected_salary_max/target_city/intention/resume_summary）
- 聊天：`POST /api/chat` body `{"message"}` → SSE 流（事件 `{"type":"delta","text"}` / `{"type":"done"}` / `{"type":"error","text"}` / `{"type":"confirm",...}`）；历史 `GET /api/chat/history` → `{"messages":[{id,role,content,created_at}]}`；确认 `POST /api/chat/confirm` body `{"confirm_id"}`

- [ ] **Step 1: ApplicationsView.vue**

```vue
<template>
  <div class="card">
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;">
      <select v-model="status" @change="load" style="padding:6px;border:1px solid #ddd;border-radius:6px;">
        <option value="">全部状态</option>
        <option v-for="(label, key) in STATUS_LABELS" :key="key" :value="key">{{ label }}</option>
      </select>
      <input v-model.number="taskId" placeholder="任务 ID 过滤" style="padding:6px;border:1px solid #ddd;border-radius:6px;width:110px;" @change="load" />
      <button class="btn" @click="load">刷新</button>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead><tr style="border-bottom:2px solid #eee;text-align:left;color:#666;">
        <th style="padding:8px;">岗位</th><th>公司</th><th>薪资</th><th>评分</th><th>状态</th><th>时间</th><th>操作</th>
      </tr></thead>
      <tbody>
        <tr v-for="a in apps" :key="a.id" style="border-bottom:1px solid #f0f0f0;">
          <td style="padding:8px;">{{ a.job_title || '#' + a.job_id }}</td>
          <td>{{ a.company }}</td><td>{{ a.salary_text }}</td>
          <td>{{ a.match_score ?? '—' }}</td>
          <td><span class="badge" :class="'st-' + a.status">{{ STATUS_LABELS[a.status] || a.status }}</span></td>
          <td style="font-size:12px;color:#888;">{{ a.applied_at || a.updated_at }}</td>
          <td>
            <select :value="a.status" @change="changeStatus(a, $event.target.value)" style="font-size:12px;padding:3px;">
              <option v-for="(label, key) in STATUS_LABELS" :key="key" :value="key">{{ label }}</option>
            </select>
          </td>
        </tr>
        <tr v-if="!apps.length"><td colspan="7" style="text-align:center;color:#9ca3af;padding:30px;">暂无记录</td></tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get, post } from '../api/client.js'
import { STATUS_LABELS } from '../utils/dashboard.js'
const apps = ref([]); const status = ref(''); const taskId = ref('')
async function load() {
  const q = new URLSearchParams()
  if (status.value) q.set('status', status.value)
  if (taskId.value) q.set('task_id', taskId.value)
  apps.value = (await get('/api/applications?' + q.toString())).applications || []
}
async function changeStatus(a, s) {
  try { await post(`/api/applications/${a.id}/status`, { status: s }); await load() }
  catch (e) { alert('更新失败: ' + e.message) }
}
onMounted(load)
</script>
```

- [ ] **Step 2: SemiQueueView.vue**

```vue
<template>
  <div class="card">
    <h3 style="font-size:15px;margin-bottom:12px;">半自动清单（{{ apps.length }} 条待确认）</h3>
    <div v-for="a in apps" :key="a.id" style="border:1px solid var(--border);border-radius:10px;padding:12px;margin-bottom:10px;">
      <div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;">
        <div>
          <b>{{ a.job_title || '#' + a.job_id }}</b>
          <span class="muted" style="margin-left:8px;">{{ a.company }} · {{ a.salary_text }}</span>
          <span class="muted" style="display:block;font-size:12px;">评分 {{ a.match_score ?? '—' }} · {{ a.llm_reason }}</span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          <button class="btn ok" @click="confirm(a, 'applied')">确认投递</button>
          <button class="btn" @click="confirm(a, 'skip')">跳过</button>
          <button class="btn" @click="regenerate(a)">重写消息</button>
        </div>
      </div>
      <div v-if="a.message" style="margin-top:8px;font-size:12px;color:#555;background:#f9fafb;padding:8px;border-radius:6px;">{{ a.message }}</div>
      <div v-if="candidates[a.id]" style="margin-top:8px;display:flex;flex-direction:column;gap:6px;">
        <div v-for="(m, i) in candidates[a.id]" :key="i" style="font-size:12px;background:#f9fafb;padding:8px;border-radius:6px;display:flex;gap:8px;align-items:center;">
          <span style="flex:1;">{{ m }}</span>
          <button class="btn ok" @click="confirm(a, 'applied', m)">选用</button>
        </div>
      </div>
    </div>
    <div v-if="!apps.length" style="text-align:center;color:#9ca3af;padding:30px;">暂无待确认岗位</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get, post } from '../api/client.js'
const apps = ref([]); const candidates = ref({})
async function load() { apps.value = (await get('/api/applications?status=pending_manual&limit=100')).applications || [] }
async function confirm(a, status, message) {
  await post(`/api/applications/${a.id}/status`, { status, detail: message || a.message || '' })
  candidates.value[a.id] = null; await load()
}
async function regenerate(a) {
  const r = await post(`/api/applications/${a.id}/regenerate-message`)
  candidates.value[a.id] = r.messages || []
}
onMounted(load)
</script>
```

- [ ] **Step 3: TaskDetailView.vue**（SSE 进度 + 控制按钮 + 岗位评估列表）

```vue
<template>
  <div>
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
        <div>
          <h3 style="font-size:15px;">{{ task.name || '任务 #' + id }}</h3>
          <span class="muted" style="font-size:12px;">模式 {{ task.mode }} · 状态 <b>{{ task.status }}</b> · 累计 {{ task.application_count }} 条评估</span>
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          <button v-if="['pending','paused','stopped'].includes(task.status)" class="btn" @click="act('start')">启动</button>
          <button v-if="task.status==='running'" class="btn" @click="act('pause')">暂停</button>
          <button v-if="task.status==='paused'" class="btn" @click="act('resume')">继续</button>
          <button v-if="task.status==='interrupted'" class="btn" @click="act('resume-after-crash')">崩溃续跑</button>
          <button v-if="['running','paused'].includes(task.status)" class="btn danger" @click="act('stop')">停止</button>
        </div>
      </div>
      <div v-if="sseState" class="muted" style="font-size:12px;margin-top:8px;">{{ sseState }}</div>
      <div v-if="events.length" style="margin-top:10px;max-height:140px;overflow-y:auto;font-size:12px;background:#f9fafb;padding:10px;border-radius:8px;">
        <div v-for="(e, i) in events" :key="i">{{ e }}</div>
      </div>
    </div>
    <div class="card">
      <h3 style="font-size:14px;margin-bottom:10px;">岗位评估（最近 100 条）</h3>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead><tr style="border-bottom:2px solid #eee;text-align:left;color:#666;">
          <th style="padding:8px;">岗位</th><th>公司</th><th>薪资</th><th>决策</th><th>评分</th><th>状态</th><th>理由</th>
        </tr></thead>
        <tbody>
          <tr v-for="a in apps" :key="a.id" style="border-bottom:1px solid #f0f0f0;">
            <td style="padding:8px;">{{ a.job_title || '#' + a.job_id }}</td>
            <td>{{ a.company }}</td><td>{{ a.salary_text }}</td>
            <td>{{ a.decision }}</td><td>{{ a.match_score ?? '—' }}</td>
            <td>{{ a.status }}</td>
            <td style="font-size:12px;color:#666;max-width:280px;">{{ a.llm_reason }}</td>
          </tr>
          <tr v-if="!apps.length"><td colspan="7" style="text-align:center;color:#9ca3af;padding:30px;">暂无评估记录</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { get, post } from '../api/client.js'
const route = useRoute(); const id = route.params.id
const task = ref({}); const apps = ref([]); const events = ref([]); const sseState = ref('')
let es = null
async function load() {
  task.value = await get('/api/tasks/' + id)
  apps.value = (await get('/api/applications?task_id=' + id + '&limit=100')).applications || []
}
async function act(action) { await post(`/api/tasks/${id}/${action}`); await load() }
function connect() {
  es = new EventSource(`/api/tasks/${id}/events`)
  es.onopen = () => { sseState.value = '已连接实时进度' }
  es.onmessage = (e) => {
    try { const d = JSON.parse(e.data); events.value.unshift(JSON.stringify(d)); if (events.value.length > 50) events.value.pop() }
    catch (err) { events.value.unshift(e.data) }
  }
  es.onerror = () => { sseState.value = '连接中断，重连中…' }
}
onMounted(() => { load(); connect() })
onBeforeUnmount(() => { if (es) es.close() })
</script>
```

- [ ] **Step 4: ConfigView.vue**（配置键值 + 画像表单）

```vue
<template>
  <div class="card">
    <h3 style="font-size:15px;margin-bottom:12px;">系统配置</h3>
    <div style="display:flex;flex-direction:column;gap:10px;">
      <div v-for="(v, k) in config" :key="k" style="display:flex;gap:8px;align-items:center;">
        <span style="flex:0 0 160px;font-size:13px;">{{ k }}</span>
        <input :value="v" @change="save(k, $event.target.value)" style="flex:1;padding:6px;border:1px solid #ddd;border-radius:6px;font-size:13px;" />
      </div>
      <button class="btn" @click="reloadConfig">刷新配置</button>
    </div>
  </div>
  <div class="card">
    <h3 style="font-size:15px;margin-bottom:12px;">求职画像</h3>
    <div style="display:flex;flex-direction:column;gap:10px;">
      <textarea v-model="profile.skills" placeholder="技能（逗号分隔）" style="padding:8px;border:1px solid #ddd;border-radius:6px;"></textarea>
      <input v-model.number="profile.experience_years" placeholder="经验年限" style="padding:8px;border:1px solid #ddd;border-radius:6px;" />
      <input v-model="profile.target_city" placeholder="目标城市" style="padding:8px;border:1px solid #ddd;border-radius:6px;" />
      <textarea v-model="profile.resume_summary" placeholder="简历摘要" style="padding:8px;border:1px solid #ddd;border-radius:6px;min-height:80px;"></textarea>
      <button class="btn" @click="saveProfile">保存画像</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { get, put } from '../api/client.js'
const config = ref({}); const profile = ref({})
async function load() {
  config.value = await get('/api/config')
  try { profile.value = await get('/api/profile') } catch (e) { profile.value = {} }
}
function save(key, value) { put('/api/config', { key, value }).then(load).catch(e => alert('保存失败: ' + e.message)) }
function saveProfile() { put('/api/profile', profile.value).then(load).catch(e => alert('保存失败: ' + e.message)) }
onMounted(load)
</script>
```

（注意：`api/client.js` 需增加 `put(url, body)`——`request(url, {method:'PUT', body: JSON.stringify(body)})`，Task 4 未含，此处实现时补充并加一个 `put` 单测。）

- [ ] **Step 5: ChatView.vue**（SSE 流式 + 确认卡片）

```vue
<template>
  <div class="card">
    <h3 style="font-size:15px;margin-bottom:12px;">智能助手</h3>
    <div ref="log" style="height:420px;overflow-y:auto;background:#f9fafb;border-radius:8px;padding:12px;margin-bottom:10px;">
      <div v-for="(m, i) in messages" :key="i" :style="msgStyle(m.role)">
        <div class="muted" style="font-size:11px;">{{ m.role === 'user' ? '你' : '助手' }} · {{ m.created_at || '' }}</div>
        <div style="font-size:13px;white-space:pre-wrap;">{{ m.content }}</div>
      </div>
      <div v-if="streaming" style="font-size:13px;color:#555;">{{ streaming }}</div>
      <div v-if="pendingConfirm" style="border:1px solid #f59e0b;border-radius:8px;padding:10px;margin-top:8px;background:#fffbeb;">
        <div style="font-size:13px;">{{ pendingConfirm.text }}</div>
        <div style="margin-top:8px;display:flex;gap:6px;">
          <button class="btn ok" @click="confirm(true)">确认执行</button>
          <button class="btn" @click="pendingConfirm = null">取消</button>
        </div>
      </div>
    </div>
    <div style="display:flex;gap:8px;">
      <input v-model="input" placeholder="输入消息，如：创建一个投递任务，关键词 python，城市武汉" style="flex:1;padding:8px;border:1px solid #ddd;border-radius:6px;" @keyup.enter="send" />
      <button class="btn" :disabled="sending" @click="send">发送</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { get, post } from '../api/client.js'
const messages = ref([]); const input = ref(''); const streaming = ref('')
const pendingConfirm = ref(null); const sending = ref(false); const log = ref(null)
async function send() {
  const text = input.value.trim(); if (!text || sending.value) return
  messages.value.push({ role: 'user', content: text }); input.value = ''
  sending.value = true; streaming.value = ''
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    })
    if (!resp.ok) throw new Error('请求失败')
    const reader = resp.body.getReader(); const dec = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += dec.decode(value, { stream: true })
      const parts = buf.split('\n\n'); buf = parts.pop()
      for (const part of parts) {
        if (!part.startsWith('data: ')) continue
        let ev; try { ev = JSON.parse(part.slice(6)) } catch (e) { continue }
        if (ev.type === 'delta') { streaming.value += ev.text; scroll() }
        else if (ev.type === 'done') { messages.value.push({ role: 'assistant', content: streaming.value }); streaming.value = ''; scroll() }
        else if (ev.type === 'error') { messages.value.push({ role: 'assistant', content: '[错误] ' + ev.text }); streaming.value = ''; scroll() }
        else if (ev.type === 'confirm') { pendingConfirm.value = { id: ev.confirm_id, text: ev.text || '确认执行此操作？' } }
      }
    }
  } catch (e) { messages.value.push({ role: 'assistant', content: '[错误] ' + e.message }) }
  finally { sending.value = false }
}
async function confirm(ok) {
  if (!ok || !pendingConfirm.value) { pendingConfirm.value = null; return }
  const r = await post('/api/chat/confirm', { confirm_id: pendingConfirm.value.id })
  pendingConfirm.value = null
  messages.value.push({ role: 'assistant', content: JSON.stringify(r) })
  scroll()
}
function scroll() { nextTick(() => { if (log.value) log.value.scrollTop = log.value.scrollHeight }) }
function msgStyle(role) { return role === 'user' ? { textAlign: 'right' } : {} }
onMounted(async () => { messages.value = (await get('/api/chat/history')).messages || []; scroll() })
</script>
```

- [ ] **Step 6: 补充 put 方法**（修改 `src/api/client.js`）

```js
export const put = (url, body) =>
  request(url, { method: 'PUT', body: JSON.stringify(body) })
```

并在 `tests/client.test.js` 追加一个 `put` 用例（PUT 方法 + JSON body）。

- [ ] **Step 7: 测试 + 构建验证**

Run: `cd efw-ai/frontend && npm test && npm run build`
Expected: PASS + build 通过

- [ ] **Step 8: Commit**

```bash
git add efw-ai/frontend/
git commit -m "feat: 迁移投递记录/半自动清单/任务详情/配置/智能助手页面"
```

---

### Task 7: SPA fallback + 静态托管 + 联调 + 文档

**Files:**
- Modify: `efw-ai/app/main.py`（删除 Jinja2 模板渲染路由与 `templates` 依赖；加 StaticFiles 托管 `frontend/dist` + SPA fallback；保留全部 `/api/*` 路由）
- Modify: `efw-ai/.gitignore`（加 `frontend/dist/`、`frontend/node_modules/`）
- Modify: `efw-ai/README.md`（构建与运行说明）
- Create: `efw-ai/tests/test_spa_fallback.py`
- Test: `cd efw-ai && uv run pytest`（全量回归）；`cd frontend && npm run build`

**Interfaces:**
- Consumes: Task 4-6 的前端构建产物 `frontend/dist/`
- Produces:
  - `GET /` 与任意非 `/api/` 非扩展名路径 → `frontend/dist/index.html`（`FileResponse`）；dist 缺失 → 503 JSON `{"detail":"前端未构建..."}`
  - 现有全部 `/api/*` 行为不变

- [ ] **Step 1: 写失败测试**（`tests/test_spa_fallback.py`）

```python
import pytest
from fastapi.testclient import TestClient


def _make_client(tmp_path, monkeypatch, dist_exists: bool):
    from app import main as main_mod

    if dist_exists:
        dist = tmp_path / "dist"
        dist.mkdir()
        (dist / "index.html").write_text("<div id='app'>EFW</div>", encoding="utf-8")
        monkeypatch.setattr(main_mod, "FRONTEND_DIST", str(dist))
    else:
        monkeypatch.setattr(main_mod, "FRONTEND_DIST", str(tmp_path / "missing"))
    return TestClient(main_mod.app)


def test_root_serves_spa_when_built(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, dist_exists=True)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<div id='app'>" in resp.text


def test_unknown_path_falls_back_to_spa(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, dist_exists=True)
    resp = client.get("/some/random/page")
    assert resp.status_code == 200
    assert "<div id='app'>" in resp.text


def test_api_routes_untouched(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, dist_exists=True)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_missing_dist_returns_503(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch, dist_exists=False)
    resp = client.get("/")
    assert resp.status_code == 503
    assert "前端" in resp.json()["detail"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd efw-ai && uv run pytest tests/test_spa_fallback.py -q`
Expected: FAIL（当前 `/` 仍返回模板渲染，`main_mod.FRONTEND_DIST` 不存在）

- [ ] **Step 3: 改造 main.py**（删除模板路由 + SPA fallback + 静态托管）

```python
from pathlib import Path
from fastapi.responses import FileResponse, JSONResponse

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# ---- 删除以下 Jinja2 页面路由及其模板依赖 ----
#   @app.get("/")、@app.get("/tasks/{task_id}")、@app.get("/applications")、
#   @app.get("/applications/{app_id}")、@app.get("/semi-queue")、
#   @app.get("/chat")、@app.get("/config")
#   对应删除 templates 引用（templates.TemplateResponse、import 的模板相关、
#   _get_task_application_counts/_compute_cost_stats 若仅被页面路由使用）
#   （_compute_cost_stats 的成本逻辑已在 Task 3 移入 dashboard_service._compute_cost，
#    此处整体删除 main.py 中的旧实现，dashboard API 不受影响）

# ---- 静态托管 + SPA fallback（放在所有 /api 路由定义之后）----

@app.get("/{path:path}")
def spa_fallback(path: str):
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        return JSONResponse(
            status_code=503,
            content={"detail": "前端未构建，请先运行: cd efw-ai/frontend && npm install && npm run build"},
        )
    return FileResponse(index)
```

（保留 `/api/health` 等全部 API；删除页面路由后，原 `dashboard.html`/`base.html` 等模板文件保留在仓库但不再被引用——若计划执行中确认无任何引用，可一并删除模板目录，测试以 `git grep templates` 为空为准。）

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `cd efw-ai && uv run pytest tests/test_spa_fallback.py -q`
Expected: PASS（4 passed）
随后：`cd efw-ai && uv run pytest -q` 全量（约 149+ 保持全绿）；`cd efw-ai/frontend && npm run build && npm test` 前端全绿

- [ ] **Step 5: .gitignore + README**

`.gitignore` 追加：

```gitignore
frontend/dist/
frontend/node_modules/
```

README 追加「前端构建与运行」：

```markdown
## 前端（SPA）

前端为 Vue 3 + Vite，位于 `frontend/`。构建产物由 FastAPI 静态托管（单端口 8000）。

首次构建：
```bash
cd frontend && npm install && npm run build
```

日常运行（后端已托管 dist）：
```bash
uv run uvicorn app.main:app
# 浏览器打开 http://127.0.0.1:8000
```

前端开发（热更新）：
```bash
cd frontend && npm run dev
# Vite dev server 5173，/api 自动代理到 8000
```
```

- [ ] **Step 6: 联调验收**

1. `cd efw-ai/frontend && npm run build`
2. `cd efw-ai && uv run uvicorn app.main:app --port 8000`
3. 浏览器打开 `http://127.0.0.1:8000`：看板渲染、登录状态条显示"未登录"
4. 点「去登录」→ 弹出 Chromium 窗口 → 完成 Boss 登录 → 状态条变"已登录"
5. 看板今日状态/趋势/分布随数据刷新；任务可启动/暂停；`/chat` 无 Key 时提示配置

- [ ] **Step 7: Commit**

```bash
git add efw-ai/app/main.py efw-ai/.gitignore efw-ai/README.md efw-ai/tests/test_spa_fallback.py
git commit -m "feat: SPA fallback 与前端静态托管（单端口）"
```

---

## 自审记录（控制器执行，2026-09-07）

**1. Spec 覆盖核对：**
- 登录四信号判定 → Task 1（含匿名 cookie 回归用例）✓
- BrowserSessionManager 状态机（8 态）→ Task 1（not_started/starting/waiting_login/logged_in/expired/timeout/error/closed；closed 由前端 meta 覆盖，后端以 not_started 回退）✓
- auth API 3 端点 → Task 2 ✓
- dashboard today/deliveries → Task 3（今日口径、配额、趋势补 0、状态分布、per_task）✓
- SPA 6 页面 + 路由 → Task 4（路由/布局/登录条）+ Task 5（看板）+ Task 6（5 页）✓
- 单端口托管 + fallback + dist 缺失 503 → Task 7 ✓
- 成本累计口径（不编造今日）→ Task 3 `_compute_cost` 复用现有键 ✓
- 测试策略（后端 pytest + 前端 vitest/build + 联调）→ 各任务 Steps ✓

**2. 占位符扫描：** 无 TBD/TODO；每个代码步骤含完整代码；接口形状均来自已核实代码（applications/chat/config/profile/tasks 协议已读取确认）。

**3. 类型一致性：**
- `BrowserManager.login_status` 返回 `str`（Task 1 定义，Task 1 测试使用）✓
- `BrowserSessionManager.start_login/tick/check_now -> str`、`status() -> dict`（Task 1 定义，Task 2 API 使用）✓
- `get_today/get_deliveries -> dict`（Task 3 定义，Task 3 API 使用）✓
- `api/client.js`：Task 4 定义 `get/post`，Task 6 增加 `put` 并补测试 ✓
- `STATUS_LABELS/statusEntries/mapTrend`（Task 5 定义，Task 6 ApplicationsView/SemiQueueView 使用）✓
- `loginStateMeta`（Task 4 定义，LoginStatusBar 使用）✓
- 已知偏差：已修正（Task 3 测试 seed 的 detail 值去掉多余 `)`）
- 已知注意：`test_dashboard_service` 中 `get_today` 对 `remaining_ratio` 断言 0.9（2/20）——`round(1-2/20,3)=0.9` ✓

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-09-07-efw-dashboard-spa-implementation.md`.** 两个执行选项：

1. **Subagent-Driven（推荐）**——每个任务派发全新子代理，任务间评审，快速迭代
2. **Inline Execution**——本会话内用 executing-plans 批量执行+检查点

**选哪个？**
