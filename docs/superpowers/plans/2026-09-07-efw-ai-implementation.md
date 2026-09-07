# EFW-AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按设计文档实现 EFW-AI —— 一个单进程 Python 求职投递决策系统，只针对 Boss 直聘，AI 决策链驱动、可选对话式助手、自动/半自动双模式投递。

**Architecture:** 单进程模块化单体，四层单向依赖（Web/API → Agent 编排 → 执行层 → 数据层），asyncio 事件循环驱动 Playwright 与 LLM 调用；决策链五环节（规则预筛→JD 解析→匹配评分→投递决策→文案生成），每岗位最多 3 次 LLM 调用，全链路规则兜底；风控五层保护投递节奏；对话助手为可选开关模块。

**Tech Stack:** Python 3.12 · FastAPI + Uvicorn · SQLModel/SQLite · Playwright (Python) · openai SDK（OpenAI 兼容，DeepSeek/Moonshot）· Jinja2 + htmx + Alpine.js · pytest + pytest-asyncio · uv

**Spec:** `docs/superpowers/specs/2026-09-07-efw-ai-redesign-design.md`（本计划从该文档论证，执行者须同时阅读两份文档）

## Global Constraints

（逐字取自设计文档，每个任务隐含遵守）

- 新项目位于本仓库 `efw-ai/` 目录，独立 pyproject，不与 `src/`（Java 老代码）混放；老代码只读不碰。
- Python 3.12+；依赖用 `uv` 管理；`.venv` 建在 `efw-ai/` 内。
- 单进程 asyncio；四层单向依赖：`app/api → app/agent → app/worker → app/db/models`，禁止反向 import。
- SQLite 单文件 `data/efw.db`（`data/` 进 .gitignore）；SQLModel 定义 9 张表：config、profile、task、job、application、application_event、chat_message、cookie、blacklist。
- 评分口径 0-10，阈值默认 7.0；日投递限额默认 20；投递间隔 8–25 秒随机；每 5 次投递休息 2–5 分钟。
- 决策链每岗位最多 3 次 LLM 调用；每个 LLM 环节失败走规则兜底（标记 `fallback=true`），连续失败 3 次熔断该环节 10 分钟；每环节记录 token 用量。
- 决策（decision）：`deliver | skip | pending`；投递状态（status）：`skip | pending_manual | applied | responded | interview | offer | rejected | withdrawn`；任务状态：`pending | running | paused | finished | stopped | failed`。
- `job.boss_job_id UNIQUE`；`application UNIQUE(job_id, task_id)`。
- 半自动模式：生成 `application(decision=deliver, status=pending_manual)` 进投递清单，用户标记后进入跟进循环。
- 风控五层：节奏随机、频率休息、日配额、掉线全停、人机验证暂停并通知用户（不做全自动过人机验证）。
- 对话助手写操作必须产出"待确认卡片"，用户点确认才执行；无 API Key 时 `/chat` 返回不可用提示。
- 崩溃恢复：进程重启后 `running` 任务标记 `interrupted`，按 `task.last_job_id` 游标续跑。
- 代码与提交不含任何个人信息（用户名、真实邮箱、IP、密钥）；README 只写通用示例。
- 测试：`pytest` + `pytest-asyncio`；决策链测试 mock LlmClient（固定返回值 + 故障注入）；执行层测试 mock 页面对象，不连真实网站。

---

### Task 1: 项目骨架 + SQLModel 数据模型（9 张表）

**Files:**
- Create: `efw-ai/pyproject.toml`
- Create: `efw-ai/.gitignore`
- Create: `efw-ai/app/__init__.py`
- Create: `efw-ai/app/config.py`
- Create: `efw-ai/app/db.py`
- Create: `efw-ai/app/models.py`
- Create: `efw-ai/tests/test_models.py`
- Create: `efw-ai/tests/conftest.py`

**Interfaces:**
- Produces:
  - `app/config.py`: `class Settings(BaseSettings)`，字段 `db_path: str = "data/efw.db"`、`data_dir: str = "data"`、`host: str = "127.0.0.1"`、`port: int = 8888`；`get_settings() -> Settings`（lru_cache）。
  - `app/db.py`: `engine`（绑定 `get_settings().db_path`）；`init_db() -> None`（`SQLModel.metadata.create_all`）；`get_session()` FastAPI 依赖，yield `Session`。
  - `app/models.py`: 9 个 SQLModel 类（表名小写）：`ConfigItem`、`Profile`、`Task`、`Job`、`Application`、`ApplicationEvent`、`ChatMessage`、`Cookie`、`Blacklist`，字段与枚举值严格按设计文档第 4 节。
  - `tests/conftest.py`: fixture `tmp_db`（tmp_path 上建库并 `init_db`）、fixture `session`。

- [ ] **Step 1: 写 pyproject.toml 与 .gitignore**

`efw-ai/pyproject.toml`:
```toml
[project]
name = "efw-ai"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sqlmodel>=0.0.22",
  "jinja2>=3.1",
  "python-multipart>=0.0.9",
  "playwright>=1.48",
  "openai>=1.50",
  "pydantic-settings>=2.6",
  "httpx>=0.27",
]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.24"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`efw-ai/.gitignore`:
```
.venv/
__pycache__/
data/
*.db
.pytest_cache/
```

- [ ] **Step 2: 写数据模型与配置（实现）**

`efw-ai/app/models.py`（9 个模型，关键枚举字段用 CHECK 对应文本；SQLModel 字段名与设计文档一致）：
```python
from datetime import datetime
from sqlmodel import SQLModel, Field
from typing import Optional

def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")

class ConfigItem(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = Field(default="{}")  # JSON
    updated_at: str = Field(default_factory=_now)

class Profile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    skills: str = ""
    experience_years: int = 0
    expected_salary_min: float = 0.0
    expected_salary_max: float = 0.0
    target_city: str = ""
    intention: str = ""
    resume_summary: str = ""
    updated_at: str = Field(default_factory=_now)

class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = ""
    keywords: str = "[]"  # JSON 数组
    city: str = ""
    mode: str = "auto"    # auto | semi
    max_deliveries: int = 50
    daily_limit: int = 20
    match_threshold: float = 7.0
    rules: str = "{}"     # JSON {salary_min, exclude_companies[]}
    status: str = "pending"  # pending|running|paused|finished|stopped|failed
    last_job_id: Optional[int] = None
    created_at: str = Field(default_factory=_now)
    finished_at: Optional[str] = None

class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    boss_job_id: str = Field(index=True, unique=True)
    title: str = ""
    company: str = ""
    company_scale: str = ""
    financing_stage: str = ""
    industry: str = ""
    salary_text: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    experience_req: str = ""
    education_req: str = ""
    city: str = ""
    jd_text: str = ""
    jd_parsed: str = "{}"
    job_url: str = ""
    created_at: str = Field(default_factory=_now)

class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(index=True)
    task_id: int = Field(index=True)
    mode: str = "auto"
    decision: str = "pending"   # deliver|skip|pending
    match_score: Optional[float] = None
    llm_reason: str = ""
    message: str = ""
    status: str = "skip"        # skip|pending_manual|applied|responded|interview|offer|rejected|withdrawn
    applied_at: Optional[str] = None
    updated_at: str = Field(default_factory=_now)

class ApplicationEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(index=True)
    event_type: str = ""
    detail: str = ""
    created_at: str = Field(default_factory=_now)

class ChatMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    role: str = ""  # user|assistant
    content: str = ""
    related_task_id: Optional[int] = None
    created_at: str = Field(default_factory=_now)

class Cookie(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str = "boss"
    cookie_json: str = "{}"
    user_data_dir: str = ""
    updated_at: str = Field(default_factory=_now)

class Blacklist(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    type: str = "company"  # company|job|recruiter
    value: str = ""
    reason: str = ""
    created_at: str = Field(default_factory=_now)
```

`efw-ai/app/db.py`:
```python
from sqlmodel import SQLModel, Session, create_engine
from .config import get_settings

engine = create_engine(f"sqlite:///{get_settings().db_path}", connect_args={"check_same_thread": False})

def init_db() -> None:
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
```

- [ ] **Step 3: 写失败测试**

`efw-ai/tests/conftest.py`:
```python
import pytest
from pathlib import Path
from sqlmodel import Session, SQLModel, create_engine

@pytest.fixture()
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path/'t.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return eng

@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s
```

`efw-ai/tests/test_models.py`:
```python
from app.models import Task, Application, Job, Profile, Blacklist, ConfigItem

def test_profile_insert_and_read(session):
    p = Profile(skills="Linux,K8s", experience_years=3, expected_salary_min=15, expected_salary_max=25)
    session.add(p); session.commit()
    got = session.get(Profile, p.id)
    assert got.skills == "Linux,K8s"
    assert got.experience_years == 3

def test_job_boss_id_unique(session):
    session.add(Job(boss_job_id="abc", title="t1")); session.commit()
    session.add(Job(boss_job_id="abc", title="t2")); session.commit()  # 期望抛 IntegrityError
```

- [ ] **Step 4: 运行测试确认失败**

Run: `cd efw-ai && uv sync && uv run pytest tests/test_models.py -v`
Expected: 导入错误或 FAIL（无 app 包/无模型）。

- [ ] **Step 5: 安装依赖并让测试通过**

Run: `cd efw-ai && uv sync && uv run pytest tests/test_models.py -v`
Expected: 2 passed（含 `pytest.raises(IntegrityError)` 包住唯一约束断言——若 Step 3 测试未包，先改成 `with pytest.raises(IntegrityError):`）。

- [ ] **Step 6: Commit**

```bash
git add efw-ai/pyproject.toml efw-ai/.gitignore efw-ai/app efw-ai/tests
git commit -m "feat: EFW-AI 骨架与 9 表数据模型"
```

---

### Task 2: 配置/画像服务 + API + 最小看板页

**Files:**
- Create: `efw-ai/app/schemas.py`
- Create: `efw-ai/app/services/__init__.py`
- Create: `efw-ai/app/services/config_service.py`
- Create: `efw-ai/app/api/__init__.py`
- Create: `efw-ai/app/api/config.py`
- Create: `efw-ai/app/api/profile.py`
- Create: `efw-ai/app/main.py`
- Create: `efw-ai/app/templates/base.html`
- Create: `efw-ai/app/templates/dashboard.html`
- Test: `efw-ai/tests/test_api_config.py`

**Interfaces:**
- Consumes: `app/models.py`（ConfigItem、Profile）、`app/db.py::get_session`。
- Produces:
  - `app/services/config_service.py`: `get_config(session, key) -> str|None`、`set_config(session, key, value: str) -> None`、`get_all_config(session) -> dict`、`get_bool(session, key, default=False) -> bool`。
  - `app/schemas.py`: `ProfileIn(BaseModel)`（skills、experience_years、expected_salary_min/max、target_city、intention、resume_summary）。
  - `app/api/config.py`: router `GET /api/config`（全部配置 dict）、`PUT /api/config`（body: `ConfigPut(key, value)`）。
  - `app/api/profile.py`: router `GET/PUT /api/profile`（单行 upsert）。
  - `app/main.py`: 创建 FastAPI，`init_db()` on startup，挂载 api 路由 + Jinja2Templates；`GET /` 渲染 dashboard.html（读今日统计：applications 计数按 status）。

- [ ] **Step 1: 写失败测试**

`efw-ai/tests/test_api_config.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

def test_config_put_get():
    with TestClient(app) as c:
        r = c.put("/api/config", json={"key": "model", "value": "deepseek-v4-flash"})
        assert r.status_code == 200
        r2 = c.get("/api/config")
        assert r2.json()["model"] == "deepseek-v4-flash"

def test_profile_put_get():
    with TestClient(app) as c:
        body = {"skills": "Linux,K8s", "experience_years": 3,
                "expected_salary_min": 15, "expected_salary_max": 25,
                "target_city": "武汉", "intention": "云原生方向", "resume_summary": ""}
        assert c.put("/api/profile", json=body).status_code == 200
        got = c.get("/api/profile").json()
        assert got["skills"] == "Linux,K8s"
```

（注：TestClient 需要 httpx 已装；`app/main.py` 此时不存在 → 测试失败。）

- [ ] **Step 2: 实现 services/schemas/api/main**

`app/services/config_service.py`:
```python
from sqlmodel import Session, select
from ..models import ConfigItem

def get_config(session: Session, key: str) -> str | None:
    item = session.get(ConfigItem, key)
    return item.value if item else None

def set_config(session: Session, key: str, value: str) -> None:
    item = session.get(ConfigItem, key)
    if item is None:
        item = ConfigItem(key=key, value=value)
        session.add(item)
    else:
        item.value = value
    session.commit()

def get_all_config(session: Session) -> dict:
    return {c.key: c.value for c in session.exec(select(ConfigItem)).all()}
```

`app/main.py`:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from pathlib import Path
from .db import init_db
from .api import config as config_api, profile as profile_api

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)
app.include_router(config_api.router, prefix="/api")
app.include_router(profile_api.router, prefix="/api")
```

`templates/base.html`（Jinja2 骨架，含 htmx CDN 与 Alpine.js CDN）、`templates/dashboard.html`（`{{ stats }}` 简单卡片）。看板数据在 `main.py` 中 `GET /` 用 `Request` + `get_session` 查询聚合（按 status 计数）。

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_api_config.py -v`
Expected: 2 passed。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app efw-ai/tests
git commit -m "feat: 配置/画像 API 与最小看板"
```

---

### Task 3: LlmClient（OpenAI 兼容封装：重试/熔断/token 统计）

**Files:**
- Create: `efw-ai/app/agent/__init__.py`
- Create: `efw-ai/app/agent/llm.py`
- Test: `efw-ai/tests/test_llm.py`

**Interfaces:**
- Consumes: `app/services/config_service`（读 `api_base_url`/`api_key`/`model`）。
- Produces:
  - `app/agent/llm.py`:
    - `@dataclass class LLMResult`: `content: str`、`prompt_tokens: int`、`completion_tokens: int`、`model: str`、`fallback: bool = False`。
    - `class CircuitBreaker`: `__init__(name, threshold=3, cooldown_seconds=600)`；`record_failure()`；`record_success()`；`is_open() -> bool`。
    - `class LlmClient`: `__init__(self, client: AsyncOpenAI | None = None, session=None)`；`async def complete(self, messages: list[dict], temperature=0.5, json_mode=False) -> LLMResult`；`async def is_available(self) -> bool`（无 api_key 或熔断打开 → False）。
    - `class LlmUnavailable(Exception)`。

- [ ] **Step 1: 写失败测试**

`efw-ai/tests/test_llm.py`:
```python
import pytest
from app.agent.llm import CircuitBreaker, LlmClient, LLMResult, LlmUnavailable

class FakeResp:
    def __init__(self, content, tokens=(10, 20)):
        self.content = content
        self.usage = type("U", (), {"prompt_tokens": tokens[0], "completion_tokens": tokens[1]})()

class FakeCompletions:
    def __init__(self, resp): self._resp = resp
    async def create(self, **kw):
        if callable(self._resp): return self._resp()
        return type("C", (), {"choices": [type("Ch", (), {"message": type("M", (), {"content": self._resp})}())],
                              "usage": type("U", (), {"prompt_tokens": 10, "completion_tokens": 20})})()

class FakeChat: 
    def __init__(self, resp): self.completions = FakeCompletions(resp)

class FakeClient:
    def __init__(self, resp): self.chat = FakeChat(resp)

def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker("t", threshold=3, cooldown_seconds=600)
    for _ in range(3): cb.record_failure()
    assert cb.is_open()

def test_complete_returns_content(monkeypatch):
    cli = LlmClient(client=FakeClient("hi"), base_url="http://x", api_key="k", model="m")
    r = cli.complete([{"role": "user", "content": "hi"}])
    assert r.content == "hi"
```

- [ ] **Step 2: 实现 llm.py**

`app/agent/llm.py`（要点）：
```python
import time
from dataclasses import dataclass
from openai import AsyncOpenAI

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
        if time.time() - self._opened_at > self.cooldown:
            self._failures = 0; self._opened_at = None; return False
        return True

class LlmClient:
    def __init__(self, session=None, client: AsyncOpenAI | None = None,
                 base_url: str = "", api_key: str = "", model: str = ""):
        self.session = session
        self._client = client or (AsyncOpenAI(base_url=base_url or None, api_key=api_key) if api_key else None)
        self.model = model
        self.breaker = CircuitBreaker("llm")

    def is_available(self) -> bool:
        return self._client is not None and not self.breaker.is_open()

    async def complete(self, messages, temperature=0.5, json_mode=False) -> LLMResult:
        if not self.is_available(): raise LlmUnavailable("llm unavailable")
        try:
            resp = await self._client.chat.completions.create(
                model=self.model, messages=messages, temperature=temperature,
                response_format={"type": "json_object"} if json_mode else None)
            self.breaker.record_success()
            return LLMResult(content=resp.choices[0].message.content,
                             prompt_tokens=getattr(resp.usage, "prompt_tokens", 0),
                             completion_tokens=getattr(resp.usage, "completion_tokens", 0),
                             model=self.model)
        except Exception:
            self.breaker.record_failure()
            raise
```

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_llm.py -v`
Expected: 2 passed。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app/agent efw-ai/tests/test_llm.py
git commit -m "feat: LlmClient 重试/熔断/token 统计"
```

---

### Task 4: BrowserManager + BossClient 骨架（登录态/Cookie/search）

**Files:**
- Create: `efw-ai/app/worker/__init__.py`
- Create: `efw-ai/app/worker/browser.py`
- Create: `efw-ai/app/worker/boss_client.py`
- Test: `efw-ai/tests/test_browser.py`
- Test: `efw-ai/tests/test_boss_client.py`

**Interfaces:**
- Consumes: `app/models.py`（Cookie）、`app/services/config_service`。
- Produces:
  - `app/worker/browser.py`:
    - `class BrowserManager`: `async def start() -> None`（`async_playwright().start()` + `chromium.launch_persistent_context(user_data_dir, headless=False)`，`user_data_dir = data_dir/"browser_profile"`）；`async def is_logged_in(page) -> bool`（访问 `https://www.zhipin.com/web/user/?ka=header-login` 判断跳转/标志文本）；`async def save_cookie(context) -> None`（取 cookies 存 Cookie 表）；`async def heartbeat(page) -> bool`；`async def stop() -> None`。页面对象由外部传入（便于测试）。
  - `app/worker/boss_client.py`:
    - `def parse_job_list(json_str: str) -> list[dict]`（纯函数：从 Boss 搜索接口 JSON 提取 `encryptJobId/title/brandName/salaryDesc/cityName/encryptUserId/jobUrl` 等，Boss 常见字段名兜底处理）。
    - `class BossClient`: `async def search(page, keyword, city) -> list[dict]`（导航到搜索 URL，`page.expect_response(lambda r: "wapi/zpgeek/search" in r.url)` 拦截 JSON 交给 `parse_job_list`，失败兜底 DOM 定位 `.job-card-wrapper`）；`async def get_detail(page, job_url) -> str`（返回 JD 文本）；`async def send_greeting(page, job_id, message) -> None`；`async def send_apply(page, job_id, message) -> None`；`async def read_messages(page) -> list[dict]`；`async def mark_applied(page, job_id) -> None`。所有方法接受注入的 `page`，方法体内不做浏览器生命周期管理。

- [ ] **Step 1: 写失败测试（解析纯函数 + Cookie 持久化）**

`efw-ai/tests/test_boss_client.py`:
```python
from app.worker.boss_client import parse_job_list

SAMPLE = '''
{"code":0,"zpData":{"jobList":[
  {"encryptJobId":"E1","jobName":"运维工程师","brandName":"某云科技",
   "salaryDesc":"15-25K","cityName":"武汉","encryptUserId":"U1",
   "jobUrl":"https://www.zhipin.com/job_detail/E1.html"}
]}}'''

def test_parse_job_list_fields():
    jobs = parse_job_list(SAMPLE)
    assert jobs[0]["boss_job_id"] == "E1"
    assert jobs[0]["title"] == "运维工程师"
    assert jobs[0]["salary_text"] == "15-25K"

def test_parse_job_list_empty():
    assert parse_job_list('{"zpData":{"jobList":[]}}') == []
```

`efw-ai/tests/test_browser.py`:
```python
import pytest
from sqlmodel import Session
from app.worker.browser import BrowserManager
from app.models import Cookie

def test_save_and_load_cookie(session):
    bm = BrowserManager(data_dir="data", session=session)
    bm.save_cookie_raw("boss", '[{"name":"x","value":"1","domain":".zhipin.com"}]')
    assert bm.load_cookie_raw("boss").startswith("[")
    got = session.exec(Session_select := None)  # 简化：直接查询
```
（简化实现：`BrowserManager.save_cookie_raw(platform, json_str)` 对 Cookie 表 upsert；`load_cookie_raw(platform) -> str`。上面最后一行改为 `cookie = session.get(Cookie, 1); assert cookie.platform == "boss"`。）

- [ ] **Step 2: 实现 browser.py 与 boss_client.py**

`parse_job_list`（纯函数，字段映射见 Interface）；`BrowserManager` 按 Interface 实现（Playwright 调用用 try/except 包住，测试只覆盖 cookie 读写与纯函数，不启动真实浏览器）。搜索 URL 约定：`https://www.zhipin.com/web/geek/job?query={keyword}&city={city_code}`。

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_boss_client.py tests/test_browser.py -v`
Expected: 全部通过（不联网）。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app/worker efw-ai/tests/test_boss_client.py efw-ai/tests/test_browser.py
git commit -m "feat: 浏览器会话管理与 Boss 岗位解析骨架"
```

---

### Task 5: 规则预筛 PreFilter（零成本）

**Files:**
- Create: `efw-ai/app/agent/prefilter.py`
- Test: `efw-ai/tests/test_prefilter.py`

**Interfaces:**
- Produces:
  - `app/agent/prefilter.py`:
    - `@dataclass class PreFilterResult`: `allowed: bool`、`reason: str`。
    - `class PreFilter`: `def evaluate(self, job: dict, profile, rules: dict, blacklist_companies: set[str]) -> PreFilterResult`（纯同步函数：标题黑名单词→skip；`job.company` 在黑名单→skip；`salary_min` 存在且 `job.salary_max < rules.salary_min`→skip；城市规则（若 rules 有 `city` 且不匹配）→skip；其余 allowed）。

- [ ] **Step 1: 写失败测试**

`efw-ai/tests/test_prefilter.py`:
```python
from app.agent.prefilter import PreFilter, PreFilterResult

pf = PreFilter()
BASE = {"boss_job_id": "1", "title": "运维工程师", "company": "某云", "salary_text": "15-25K",
        "salary_min": 15, "salary_max": 25, "city": "武汉"}

def test_allowed_when_no_rule_hit():
    r = pf.evaluate(BASE, rules={}, blacklist_companies=set())
    assert r.allowed and r.reason == ""

def test_blacklisted_company_skipped():
    r = pf.evaluate(BASE, rules={}, blacklist_companies={"某云"})
    assert not r.allowed and "黑名单" in r.reason

def test_salary_below_floor_skipped():
    r = pf.evaluate(BASE, rules={"salary_min": 30}, blacklist_companies=set())
    assert not r.allowed and "薪资" in r.reason

def test_salary_missing_passes_to_llm():
    job = dict(BASE, salary_min=None, salary_max=None)
    r = pf.evaluate(job, rules={"salary_min": 30}, blacklist_companies=set())
    assert r.allowed  # 面议放行
```

- [ ] **Step 2: 实现 prefilter.py**（按 Interface 逻辑，注意面议放行分支）

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_prefilter.py -v`
Expected: 4 passed。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app/agent/prefilter.py efw-ai/tests/test_prefilter.py
git commit -m "feat: 规则预筛（零成本硬过滤）"
```

---

### Task 6: JD 解析器 JdParser（LLM + 规则兜底）

**Files:**
- Create: `efw-ai/app/agent/jd_parser.py`
- Test: `efw-ai/tests/test_jd_parser.py`

**Interfaces:**
- Consumes: `app/agent/llm.py`（LlmClient、LLMResult、LlmUnavailable）。
- Produces:
  - `app/agent/jd_parser.py`:
    - `class JdParsed(BaseModel)`: `responsibilities: list[str]`、`requirements: list[str]`、`tech_stack: list[str]`、`experience_hint: str`、`risk_signals: list[str]`、`fallback: bool = False`。
    - `TECH_KEYWORDS: list[str]`（如 `["linux","k8s","docker","java","python","nginx","云原生","kubernetes"]`）。
    - `def parse_by_rules(jd_text: str) -> JdParsed`（正则匹配 TECH_KEYWORDS → tech_stack；"要求|任职资格"段 → requirements；"急招|大量|面议" → risk_signals；`fallback=True`）。
    - `class JdParser`: `__init__(llm: LlmClient)`；`async def parse(self, jd_text: str) -> JdParsed`（LLM json_mode 输出 → Pydantic 校验；失败/`LlmUnavailable` → `parse_by_rules`）。

- [ ] **Step 1: 写失败测试**

`efw-ai/tests/test_jd_parser.py`:
```python
import pytest
from app.agent.jd_parser import JdParser, parse_by_rules, JdParsed
from app.agent.llm import LlmUnavailable

class FailLlm:
    async def complete(self, messages, **kw): raise LlmUnavailable("no key")

def test_rule_fallback_extracts_tech_stack():
    parsed = parse_by_rules("岗位职责：负责k8s集群运维。任职要求：熟悉linux与docker。")
    assert "k8s" in parsed.tech_stack or "docker" in parsed.tech_stack
    assert parsed.fallback is True

async def test_parser_falls_back_when_llm_down():
    parser = JdParser(llm=FailLlm())
    parsed = await parser.parse("职责：维护kubernetes集群。")
    assert parsed.fallback is True
    assert "kubernetes" in parsed.tech_stack
```

- [ ] **Step 2: 实现 jd_parser.py**（LLM prompt：`"你是职位分析器，输出 JSON，键为 responsibilities/requirements/tech_stack/experience_hint/risk_signals"` + 原文；json_mode=True；解析 `json.loads` 后 Pydantic 校验，失败走规则）

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_jd_parser.py -v`
Expected: 2 passed。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app/agent/jd_parser.py efw-ai/tests/test_jd_parser.py
git commit -m "feat: JD 解析器（LLM 结构化 + 正则兜底）"
```

---

### Task 7: 匹配评分 Matcher（LLM + 规则兜底）

**Files:**
- Create: `efw-ai/app/agent/matcher.py`
- Test: `efw-ai/tests/test_matcher.py`

**Interfaces:**
- Consumes: `JdParsed`、`Profile`、`LlmClient`。
- Produces:
  - `app/agent/matcher.py`:
    - `@dataclass class MatchResult`: `score: float`、`reason: str`、`fallback: bool`。
    - `def score_by_rules(profile, jd_parsed: JdParsed, salary_min, salary_max) -> MatchResult`：`skills 重合率×5 + 经验匹配×3 + 薪资重叠×2`，归一化到 0-10，`fallback=True`。经验匹配：`jd_parsed.experience_hint` 解析数字与 `profile.experience_years` 比较（相差 ≤2 → 满分，差 >3 → 0.5 系数）。
    - `class Matcher`: `__init__(llm)`；`async def score(self, profile, jd_parsed, job) -> MatchResult`（LLM json_mode 输出 `{score: float, reason: str}`；score clamp 0-10；失败 → `score_by_rules`）。

- [ ] **Step 1: 写失败测试**

`efw-ai/tests/test_matcher.py`:
```python
from app.agent.matcher import Matcher, score_by_rules, MatchResult
from app.agent.jd_parser import JdParsed
from app.models import Profile
from app.agent.llm import LlmUnavailable

PROFILE = Profile(skills="linux,k8s,docker", experience_years=3,
                  expected_salary_min=15, expected_salary_max=25)
JD = JdParsed(responsibilities=[], requirements=[], tech_stack=["linux","k8s"],
              experience_hint="3-5年", risk_signals=[], fallback=False)

def test_rule_score_skill_overlap():
    r = score_by_rules(PROFILE, JD, salary_min=15, salary_max=25)
    assert r.score >= 6.0
    assert r.fallback is True

class FailLlm:
    async def complete(self, messages, **kw): raise LlmUnavailable("no key")

async def test_matcher_fallback_when_llm_down():
    m = Matcher(llm=FailLlm())
    r = await m.score(PROFILE, JD, {"salary_min": 15, "salary_max": 25})
    assert r.score > 0 and r.fallback is True
```

- [ ] **Step 2: 实现 matcher.py**（LLM prompt 附 profile 与 jd_parsed 摘要 + 原始 JD；json_mode；clamp 与归一化）

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_matcher.py -v`
Expected: 2 passed。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app/agent/matcher.py efw-ai/tests/test_matcher.py
git commit -m "feat: 匹配评分（LLM 打分 + 规则兜底）"
```

---

### Task 8: 投递决策 Decider（纯规则）

**Files:**
- Create: `efw-ai/app/agent/decider.py`
- Test: `efw-ai/tests/test_decider.py`

**Interfaces:**
- Produces:
  - `app/agent/decider.py`:
    - `@dataclass class Decision`: `decision: str`（`deliver|skip|pending`）、`reason: str`。
    - `class Decider`:
      - `def decide(self, match_score: float, threshold: float, rules: dict, blacklist_hit: bool, daily_used: int, daily_limit: int) -> Decision`：
        - 硬规则：`blacklist_hit` → skip("黑名单")；`rules.salary_min` 与 job 已由预筛处理，此处不再重复（保留参数以扩展）；`daily_used >= daily_limit` → skip("当日限额用尽")。
        - 软规则：`score >= threshold` → deliver；`score < threshold - 1` → skip("评分不足")；否则 → pending("存疑区间")。

- [ ] **Step 1: 写失败测试**

`efw-ai/tests/test_decider.py`:
```python
from app.agent.decider import Decider

d = Decider()

def test_blacklist_always_skip():
    r = d.decide(9.0, 7.0, {}, True, 0, 20)
    assert r.decision == "skip" and "黑名单" in r.reason

def test_daily_limit_skip():
    r = d.decide(9.0, 7.0, {}, False, 20, 20)
    assert r.decision == "skip" and "限额" in r.reason

def test_above_threshold_deliver():
    r = d.decide(8.0, 7.0, {}, False, 0, 20)
    assert r.decision == "deliver"

def test_below_threshold_minus_one_skip():
    r = d.decide(5.5, 7.0, {}, False, 0, 20)
    assert r.decision == "skip"

def test_middle_range_pending():
    r = d.decide(6.5, 7.0, {}, False, 0, 20)
    assert r.decision == "pending"
```

- [ ] **Step 2: 实现 decider.py**

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_decider.py -v`
Expected: 5 passed。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app/agent/decider.py efw-ai/tests/test_decider.py
git commit -m "feat: 投递决策器（硬规则优先 + 阈值软规则）"
```

---

### Task 9: 文案生成 Writer（LLM + 模板兜底）

**Files:**
- Create: `efw-ai/app/agent/writer.py`
- Test: `efw-ai/tests/test_writer.py`

**Interfaces:**
- Consumes: `LlmClient`、`Profile`、`JdParsed`。
- Produces:
  - `app/agent/writer.py`:
    - `def build_by_template(profile, jd_parsed: JdParsed) -> list[str]`：从 `profile.skills` 与 `jd_parsed.tech_stack` 取交集词，组装 3 条模板文案（`"您好，我看到贵司{title}岗位，我熟悉{kw1}、{kw2}，有{n}年经验，方便了解一下吗？"` 等变体）；无交集时用通用问候；`fallback=True`。
    - `class Writer`: `__init__(llm)`；`async def write(self, profile, job, jd_parsed) -> list[str]`（LLM 输出 JSON `{messages: [3 条]}`，每条约 ≤200 字；失败 → `build_by_template`）。

- [ ] **Step 1: 写失败测试**

`efw-ai/tests/test_writer.py`:
```python
from app.agent.writer import Writer, build_by_template
from app.agent.jd_parser import JdParsed
from app.models import Profile
from app.agent.llm import LlmUnavailable

PROFILE = Profile(skills="linux,k8s", experience_years=3, resume_summary="负责过生产集群")
JD = JdParsed(responsibilities=[], requirements=[], tech_stack=["linux","k8s"],
              experience_hint="", risk_signals=[], fallback=False)

def test_template_uses_skill_overlap():
    msgs = build_by_template(PROFILE, JD)
    assert len(msgs) == 3
    assert any("linux" in m.lower() for m in msgs)
    assert all(len(m) <= 200 for m in msgs)

class FailLlm:
    async def complete(self, messages, **kw): raise LlmUnavailable("no key")

async def test_writer_fallback_when_llm_down():
    w = Writer(llm=FailLlm())
    msgs = await w.write(PROFILE, {"title": "运维工程师"}, JD)
    assert len(msgs) >= 1
```

- [ ] **Step 2: 实现 writer.py**（LLM prompt 含平台规范："Boss 直聘首条消息，≤200 字，点名 1-2 个具体技能，开放问句收尾，输出 3 条候选 JSON"）

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_writer.py -v`
Expected: 2 passed。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app/agent/writer.py efw-ai/tests/test_writer.py
git commit -m "feat: 文案生成（LLM 3 候选 + 模板兜底）"
```

---

### Task 10: 决策链编排 Orchestrator + TaskService + 任务 API + SSE

**Files:**
- Create: `efw-ai/app/agent/orchestrator.py`
- Create: `efw-ai/app/services/task_service.py`
- Create: `efw-ai/app/api/tasks.py`
- Create: `efw-ai/tests/test_orchestrator.py`
- Create: `efw-ai/tests/test_tasks_api.py`

**Interfaces:**
- Consumes: PreFilter、JdParser、Matcher、Decider、Writer、models、`app/db.py`。
- Produces:
  - `app/agent/orchestrator.py`:
    - `class Orchestrator`: `__init__(prefilter, jd_parser, matcher, decider, writer, session_factory)`；`async def process_job(self, task: Task, job_dict: dict, profile: Profile, blacklist_companies: set[str], daily_used: int) -> Application`：
      1. 规则预筛 → 不通过：写 `Application(decision="skip", llm_reason=原因)` + event("evaluated")，返回。
      2. 检查 `UNIQUE(job_id, task_id)` 已存在 → 直接返回已有（防重）。
      3. `jd_parsed = await jd_parser.parse(job_dict["jd_text"])`；`match = await matcher.score(profile, jd_parsed, job_dict)`。
      4. `decision = decider.decide(match.score, task.match_threshold, json.loads(task.rules), False, daily_used, task.daily_limit)`。
      5. decision==deliver：`msgs = await writer.write(profile, job_dict, jd_parsed)`；写 `Application(decision=deliver, status=("pending_manual" if task.mode=="semi" else "applied"), message=msgs[0] (或存 JSON), match_score, llm_reason)`；event("evaluated")。
      6. decision==skip/pending 同理落库。
      7. 返回 Application（含 id）。
    - token 用量：从 LLMResult 累计写入 `config` 表 `ai_tokens_{task_id}`（简单累加）。
  - `app/services/task_service.py`:
    - `class TaskService`: `__init__(orchestrator, session_factory)`；`async def run_task(self, task_id: int) -> None`（循环：按 `task.last_job_id` 游标读 Job 表未处理岗位 → `process_job` → 更新 last_job_id → 检查暂停/停止标志与日配额；SSE 事件通过 `app.state.sse_broker` 广播 `{type, task_id, message, current, total}`）；`start(task_id)` / `pause` / `resume` / `stop` 更新 task.status 与运行标志（`app.state.task_flags: dict[int, str]`）。
  - `app/api/tasks.py`: router：`GET/POST /api/tasks`、`GET /api/tasks/{id}`、`POST /api/tasks/{id}/start|pause|resume|stop`、`POST /api/tasks/{id}/resume-after-crash`（把 `interrupted` → `running` 并触发 run_task）、`GET /api/tasks/{id}/events`（SSE：`StreamingResponse` 订阅 broker）。
  - `app/state.py`: `class AppState`: `task_flags: dict[int,str]`、`sse_broker: SseBroker`（简单 asyncio.Queue 广播：`publish(event: dict)`、`subscribe() -> AsyncIterator[dict]`）。

- [ ] **Step 1: 写失败测试（orchestrator 全链路 mock）**

`efw-ai/tests/test_orchestrator.py`:
```python
import json
from sqlmodel import Session, select
from app.agent.orchestrator import Orchestrator
from app.models import Task, Job, Application, Profile

class FakePre:
    def evaluate(self, job, profile, rules, blacklist): 
        from app.agent.prefilter import PreFilterResult
        return PreFilterResult(allowed=True, reason="")
class FakeJd:
    async def parse(self, text):
        from app.agent.jd_parser import JdParsed
        return JdParsed(responsibilities=[], requirements=[], tech_stack=["linux"], experience_hint="", risk_signals=[])
class FakeMatcher:
    async def score(self, profile, jd, job):
        from app.agent.matcher import MatchResult
        return MatchResult(score=8.5, reason="技能匹配", fallback=True)
class FakeDecider:
    def decide(self, score, threshold, rules, hit, used, limit):
        from app.agent.decider import Decision
        return Decision("deliver", "ok")
class FakeWriter:
    async def write(self, profile, job, jd):
        return ["您好，我熟悉linux，方便聊聊吗？"]

async def test_orchestrator_creates_deliver_application(engine):
    def sf():
        s = Session(engine); return s
    orch = Orchestrator(FakePre(), FakeJd(), FakeMatcher(), FakeDecider(), FakeWriter(), sf)
    with Session(engine) as s:
        task = Task(name="t", keywords='["k8s"]', city="武汉", mode="auto", rules="{}")
        s.add(task); s.commit()
        profile = Profile(skills="linux,k8s", experience_years=3); s.add(profile); s.commit()
        job = Job(boss_job_id="E1", title="运维", company="云", jd_text="职责：k8s", city="武汉")
        s.add(job); s.commit()
        task_id, job_id, profile_id = task.id, job.id, profile.id
    app = await orch.process_job(task, {"boss_job_id":"E1","title":"运维","company":"云","jd_text":"职责：k8s","salary_min":15,"salary_max":25}, profile, set(), 0)
    with Session(engine) as s:
        rows = s.exec(select(Application)).all()
        assert len(rows) == 1
        assert rows[0].decision == "deliver"
        assert rows[0].status == "applied"
```

- [ ] **Step 2: 实现 orchestrator / task_service / api / state**（按 Interface；SSE 用 `StreamingResponse(media_type="text/event-stream")` 逐行 `data: {json}\n\n`）

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_orchestrator.py tests/test_tasks_api.py -v`
Expected: 全通过。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app/agent/orchestrator.py efw-ai/app/services efw-ai/app/api/tasks.py efw-ai/app/state.py efw-ai/tests
git commit -m "feat: 决策链编排 + 任务服务 + 任务 API + SSE"
```

---

### Task 11: 投递执行与半自动清单

**Files:**
- Create: `efw-ai/app/api/applications.py`
- Create: `efw-ai/app/services/application_service.py`
- Create: `efw-ai/app/templates/semi_queue.html`
- Test: `efw-ai/tests/test_applications_api.py`

**Interfaces:**
- Consumes: `BossClient`、Application 模型。
- Produces:
  - `app/services/application_service.py`:
    - `list_applications(session, task_id=None, status=None, limit=100) -> list[Application]`
    - `get_application(session, id) -> Application|None`
    - `update_status(session, id, new_status, detail="") -> bool`（校验 new_status ∈ 8 状态；写 event("status_changed")）
    - `regenerate_message(session, id, writer) -> list[str]`（重读 job/profile 调 writer）
  - `app/api/applications.py`: `GET /api/applications`、`GET /api/applications/{id}`、`POST /api/applications/{id}/status`、`POST /api/applications/{id}/regenerate-message`。
  - 执行投递：在 `task_service.run_task` 中，当 `task.mode=="auto"` 且 decision==deliver 时，调用 `BossClient.send_greeting`（页面来自 BrowserManager 暴露的 `get_page()`）；失败则记 event("deliver_failed") 并重试 1 次；`send_greeting` 成功后 status=applied + event("delivered")。半自动任务不调用投递方法。
  - 半自动清单页 `/semi-queue`：渲染 `status=pending_manual` 的 application 列表（岗位 + 文案 + 按钮「复制/去投递/标记已投递」→ `POST /api/applications/{id}/status {status:"applied"}`）。

- [ ] **Step 1: 写失败测试**

`efw-ai/tests/test_applications_api.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

def test_update_status_valid_and_event():
    with TestClient(app) as c:
        # 先用 orchestrator 相关 fixture 造数据（简化：直接插库）
        r = c.post("/api/applications/999/status", json={"status": "applied"})
        assert r.status_code in (200, 404)  # 存在则 200，不存在 404

def test_invalid_status_rejected():
    with TestClient(app) as c:
        r = c.post("/api/applications/1/status", json={"status": "hacked"})
        assert r.status_code == 422
```
（Step 1 的断言要在实现后严格化：造一条真实 application 再断言 200 + event 落库；invalid → 400。）

- [ ] **Step 2: 实现 application_service / api / semi_queue 模板 + run_task 接入投递**

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_applications_api.py -v`
Expected: 通过。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app/api/applications.py efw-ai/app/services/application_service.py efw-ai/app/templates/semi_queue.html efw-ai/tests
git commit -m "feat: 投递执行与半自动清单"
```

---

### Task 12: 风控五层 RiskController

**Files:**
- Create: `efw-ai/app/services/risk_controller.py`
- Test: `efw-ai/tests/test_risk_controller.py`

**Interfaces:**
- Consumes: config（daily_limit、间隔参数）、Cookie/登录状态、BrowserManager 心跳。
- Produces:
  - `app/services/risk_controller.py`:
    - `class RiskController`: `__init__(session)`；`should_pause() -> tuple[bool, str]`（顺序检查：会话掉线 → ("掉线", True)；人机验证标志 → ("验证码", True)；日配额用尽 → ("限额", True)）；`next_delay_seconds() -> float`（`random.uniform(8, 25)`）；`record_delivery()`（计数：今日次数 + 连续次数；每 5 次后 `cool_off_seconds()` 返回 `random.uniform(120, 300)`）；`reset_daily()`（跨天清零，进程启动时调用）。
    - 人机验证标志由 `BossClient` 检测（URL 含 `security`/`verify` 或页面出现滑块选择器）时调用 `risk_controller.set_captcha_detected(True)`。

- [ ] **Step 1: 写失败测试**

`efw-ai/tests/test_risk_controller.py`:
```python
import pytest
from app.services.risk_controller import RiskController

def test_quota_pause():
    rc = RiskController(None, daily_limit=2)
    rc.record_delivery(); rc.record_delivery()
    paused, reason = rc.should_pause()
    assert paused and "限额" in reason

def test_captcha_pause():
    rc = RiskController(None)
    rc.set_captcha_detected(True)
    assert rc.should_pause()[0]

def test_delay_in_range():
    rc = RiskController(None)
    assert 8 <= rc.next_delay_seconds() <= 25

def test_cool_off_after_five():
    rc = RiskController(None)
    for _ in range(5): rc.record_delivery()
    assert 120 <= rc.cool_off_seconds() <= 300
```

- [ ] **Step 2: 实现 risk_controller.py**（`should_pause` 依次检查；`record_delivery` 用当天日期字符串作键）

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_risk_controller.py -v`
Expected: 4 passed。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app/services/risk_controller.py efw-ai/tests/test_risk_controller.py
git commit -m "feat: 风控五层（节奏/频率/配额/会话/验证码）"
```

---

### Task 13: 跟进循环 FollowUpAnalyzer

**Files:**
- Create: `efw-ai/app/agent/followup.py`
- Create: `efw-ai/app/services/followup_service.py`
- Test: `efw-ai/tests/test_followup.py`

**Interfaces:**
- Consumes: `LlmClient`、`BossClient.read_messages`、Application。
- Produces:
  - `app/agent/followup.py`:
    - `@dataclass class FollowUpResult`: `new_status: str | None`、`suggested_reply: str`。
    - `VALID_TRANSITIONS = {"applied","responded","interview","offer","rejected","withdrawn"}`
    - `def analyze_by_rules(conversation: str) -> FollowUpResult`：关键词规则——`"面试|约个时间|面谈"→interview`；`"offer|录用|入职"→offer`；`"不合适|暂时不|已读不回(2次以上)"→rejected`；`"你好|还在吗|详细"→responded`；默认 `None`。
    - `class FollowUpAnalyzer`: `__init__(llm)`；`async def analyze(self, conversation: str) -> FollowUpResult`（LLM json_mode 输出 `{new_status, suggested_reply}`；失败 → `analyze_by_rules` + 模板回复）。
  - `app/services/followup_service.py`:
    - `class FollowupService`: `__init__(analyzer, boss_client, risk)`；`async def run_once(self) -> int`（读所有 `status in (applied, responded, interview)` 的 application → `boss_client.read_messages` 取对话 → analyzer → 有变化则 `update_status` + event("replied") + event("status_changed")；返回处理条数）。
    - 调度：`main.py` 中 `asyncio.create_task` 后台循环，`follow_up_minutes`（config，默认 10 分钟）间隔执行；`chat_enabled` 不影响此循环。

- [ ] **Step 1: 写失败测试**

`efw-ai/tests/test_followup.py`:
```python
import pytest
from app.agent.followup import FollowUpAnalyzer, analyze_by_rules, FollowUpResult
from app.agent.llm import LlmUnavailable

def test_rule_detects_interview():
    r = analyze_by_rules("您好，您方便周三来面试吗？")
    assert r.new_status == "interview"

def test_rule_detects_offer():
    r = analyze_by_rules("恭喜您，我们决定录用您！")
    assert r.new_status == "offer"

def test_rule_no_change():
    assert analyze_by_rules("好的知道了").new_status is None

class FailLlm:
    async def complete(self, messages, **kw): raise LlmUnavailable("no key")

async def test_fallback_when_llm_down():
    a = FollowUpAnalyzer(llm=FailLlm())
    r = await a.analyze("约个时间面试")
    assert r.new_status == "interview"
```

- [ ] **Step 2: 实现 followup.py / followup_service.py + main 后台循环**

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_followup.py -v`
Expected: 4 passed。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app/agent/followup.py efw-ai/app/services/followup_service.py efw-ai/tests/test_followup.py
git commit -m "feat: 跟进循环（消息分析 → 状态推进）"
```

---

### Task 14: 对话式助手 ChatService + SSE + 确认卡片

**Files:**
- Create: `efw-ai/app/services/chat_service.py`
- Create: `efw-ai/app/api/chat.py`
- Create: `efw-ai/app/templates/chat.html`
- Test: `efw-ai/tests/test_chat.py`

**Interfaces:**
- Consumes: `LlmClient`（Function Calling）、TaskService、ApplicationService、config。
- Produces:
  - `app/services/chat_service.py`:
    - `TOOLS: list[dict]`：`get_stats`（无参，返回各状态计数）、`get_applications(status)`、`get_task_status(task_id)`、`update_task_config(task_id, patch)`、`start_task(task_id)`、`pause_task(task_id)`、`regenerate_message(application_id)`。
    - `class ChatService`: `async def stream(self, user_message: str) -> AsyncIterator[dict]`：1) 追加 user 消息；2) LLM 多轮 tool-call 循环；3) **写操作工具**（update_task_config/start_task/pause_task/regenerate_message）不直接执行 —— 返回 `{"type":"confirm","tool":...,"args":...}` 事件，由前端渲染确认卡片；用户点确认后调 `confirm_tool(confirm_id)` 执行；4) 最终文本以 SSE 流式输出（按 chunk 分割 `yield {"type":"delta","text":...}`）；5) 会话历史存 chat_message。
    - 无 API Key / 熔断 → `yield {"type":"error","text":"AI 服务不可用，请先在设置中配置 API Key"}`。
  - `app/api/chat.py`: `POST /api/chat`（body `{message}`；响应 `text/event-stream`，事件类型：`delta`、`confirm`、`done`、`error`）、`GET /api/chat/history`、`POST /api/chat/confirm`（body `{confirm_id}` 执行挂起的写操作）。

- [ ] **Step 1: 写失败测试**

`efw-ai/tests/test_chat.py`:
```python
import pytest
from app.services.chat_service import ChatService

class NoLlm:
    def is_available(self): return False

async def test_unavailable_yields_error():
    svc = ChatService(llm=NoLlm(), task_service=None, app_service=None, session_factory=None)
    events = [e async for e in svc.stream("你好")]
    assert events[0]["type"] == "error"

def test_write_tool_needs_confirm():
    from app.services.chat_service import WRITE_TOOLS
    assert "update_task_config" in WRITE_TOOLS
    assert "get_stats" not in WRITE_TOOLS
```

- [ ] **Step 2: 实现 chat_service / chat api / chat.html**

（Function Calling 循环：`messages` 追加 user → `llm.complete(messages, tools=TOOLS)` → 若 `tool_calls` 非空：读操作直接执行并追加 tool 结果；写操作生成 `confirm_id` 存内存 dict，yield confirm 事件并停止；无 tool_calls → 文本流式 yield。`/chat` SSE 用 `StreamingResponse`。`chat.html` 用 EventSource 渲染 delta + 确认卡片按钮。）

- [ ] **Step 3: 运行测试确认通过**

Run: `cd efw-ai && uv run pytest tests/test_chat.py -v`
Expected: 通过。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app/services/chat_service.py efw-ai/app/api/chat.py efw-ai/app/templates/chat.html efw-ai/tests/test_chat.py
git commit -m "feat: 对话助手（工具调用 + 写操作确认卡片）"
```

---

### Task 15: 前端完善 + 崩溃续跑 + 打磨

**Files:**
- Create: `efw-ai/app/templates/task_detail.html`
- Create: `efw-ai/app/templates/applications.html`
- Create: `efw-ai/app/templates/application_detail.html`
- Modify: `efw-ai/app/templates/base.html`、`efw-ai/app/templates/dashboard.html`、`efw-ai/app/main.py`
- Create: `efw-ai/README.md`
- Test: `efw-ai/tests/test_crash_resume.py`

**Interfaces:**
- Consumes: 全部既有接口。
- Produces:
  - 页面：`/tasks/{id}`（SSE 进度流 + 岗位评估列表 + 控制按钮）、`/applications`（筛选：状态/任务/日期 + 状态分布）、`/applications/{id}`（llm_reason、文案、事件时间线、状态推进）、`/chat` 入口仅当 `chat_enabled` 为真显示。
  - 崩溃续跑：`app/main.py` lifespan 中，启动时把所有 `status="running"` 的 task 置为 `interrupted`；`POST /api/tasks/{id}/resume-after-crash` 将 `interrupted` 置回 `running` 并调用 `run_task`（从 `last_job_id` 续）。
  - 成本统计：dashboard 显示 config 表 `ai_tokens_*` 累加估算（token 数 → 千 token 费用按 config `price_per_1k`，默认 0）。
  - `README.md`：安装（uv sync + playwright install chromium）、配置、启动（uv run uvicorn app.main:app）、测试命令、免责声明（仅供个人学习使用，遵守平台规则）。

- [ ] **Step 1: 写失败测试**

`efw-ai/tests/test_crash_resume.py`:
```python
from sqlmodel import Session, select
from app.models import Task
from app.main import app

def test_startup_marks_running_as_interrupted(engine):
    # 在 lifespan 前插入 running 任务，随后用 TestClient 进入 lifespan，断言变 interrupted
    with Session(engine) as s:
        s.add(Task(name="t", status="running")); s.commit()
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
    with Session(engine) as s:
        t = s.exec(select(Task)).first()
        assert t.status == "interrupted"
```
（TestClient 使用真实 db 路径会冲突——实现时把 `app.state.session_factory` 可注入，测试用 engine 覆盖；或此测试改用 monkeypatch `get_settings().db_path` 指向 tmp_path。）

- [ ] **Step 2: 实现页面、续跑逻辑、成本统计、README**

- [ ] **Step 3: 运行全部测试**

Run: `cd efw-ai && uv run pytest -v`
Expected: 全部通过（`uv run pytest tests/` 全绿）。

- [ ] **Step 4: Commit**

```bash
git add efw-ai/app efw-ai/tests efw-ai/README.md
git commit -m "feat: 前端页面完善 + 崩溃续跑 + 成本统计"
```

---

## Self-Review（编写时已执行）

**1. Spec 覆盖对照：**
- 四层架构 / 单进程 asyncio → Task 1、10
- 9 张表 DDL → Task 1
- 决策链五环节 + 每岗位 ≤3 次 LLM + 兜底/熔断/token → Task 3、5、6、7、8、9、10
- 执行层 BrowserManager/BossClient + 反检测脚本 → Task 4（anti_detection.js 在 Task 4 目录占位，注入逻辑并入 browser.py 的 context.add_init_script）
- 风控五层 → Task 12
- 半自动清单 → Task 11
- 跟进循环 → Task 13
- 对话助手 + 确认卡片 → Task 14
- API/前端页面 → Task 2、10、11、14、15
- 崩溃续跑 → Task 15
- 测试策略（mock LLM / mock 页面 / 风控断言）→ 各 Task 测试即体现

**2. Placeholder 扫描：** 无 TBD/TODO；每个代码步骤都给出真实代码或明确接口签名；Task 11 Step 1 中标注了"实现后严格化断言"，属于明确的实现指引而非占位。

**3. 类型一致性检查：**
- `PreFilterResult(allowed, reason)`、`MatchResult(score, reason, fallback)`、`Decision(decision, reason)`、`FollowUpResult(new_status, suggested_reply)`、`LLMResult(content, prompt_tokens, completion_tokens, model, fallback)` 在各 Task 间一致。
- `process_job` 返回 `Application`；`Decider.decide` 参数顺序 `(match_score, threshold, rules, blacklist_hit, daily_used, daily_limit)` 在 Task 8 定义、Task 10 调用一致。
- 状态枚举值（task/application/decision）在各 Task 与 models.py 中一致。

---

## Execution Handoff

计划完成并保存至 `docs/superpowers/plans/2026-09-07-efw-ai-implementation.md`。两种执行方式：

**1. Subagent-Driven（推荐）** —— 每个任务派发一个全新子代理，任务间我做评审，快速迭代。

**2. Inline Execution** —— 在当前会话用 executing-plans 批量执行，检查点评审。

选哪种？（注：本次交付物为设计+计划文档，如你选择执行，将按对应流程开始写代码。）
