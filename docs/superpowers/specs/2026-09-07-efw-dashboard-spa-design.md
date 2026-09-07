# EFW-AI 看板重构 + 登录会话 + SPA 前端设计

- 日期: 2026-09-07
- 状态: 已获用户分节确认（登录交互 A / 前后端分离 SPA / Vue3+Vite / 全应用迁移 / 单端口托管）
- 前置事实: `is_logged_in` 误判 bug 已实证（11 个匿名统计 cookie 被判为已登录，无 wt2/__zp_stoken__/last_login_phone 等登录态标志）

## 1. 背景与目标

现有 EFW-AI 前端为 Jinja2 + htmx + Alpine 服务端渲染（看板/投递记录/半自动清单/任务详情/配置/智能助手 6 页面），看板仅含"今日投递统计 + 成本估算 + 任务列表"三块简单内容。用户要求：

1. 看板可看到 Boss 直聘登录状态，并可**从看板发起登录**（弹出真实浏览器窗口，人工登录，自动检测并落库）
2. 看板展示今日状态（投递数/配额/运行任务/待跟进/面试Offer/成本）
3. 看板展示投递情况（7 天趋势/8 状态分布/半自动待确认）
4. 前端整体重构为完整 SPA，不再使用简单模板

已确认决策：
- 登录交互: **A 看板发起登录**（后端启动 Playwright 真实窗口，前端轮询状态）
- 前端形态: **前后端分离 SPA**
- 框架: **Vue 3 + Vite**，不引入重型组件库（手写样式）
- 范围: **全应用 6 页面全部迁到 SPA**，FastAPI 只出 JSON API
- 部署: **单端口托管**（FastAPI 静态托管 frontend/dist，开发期 Vite dev server 代理 /api）

## 2. 总体架构

```
浏览器 (127.0.0.1:8000)
├── Vue 3 SPA（6 页面 · vue-router · ECharts · EventSource）
└── JSON API（同源）
    FastAPI（8000）
    ├── API: tasks / applications / config / profile / chat（现有保留）
    ├── 新增 auth: /api/auth/status · /api/auth/login · /api/auth/check
    ├── 新增 dashboard: /api/dashboard/today · /api/dashboard/deliveries
    ├── 静态托管 frontend/dist（SPA fallback → index.html）
    └── BrowserSessionManager（app.state 单例，asyncio 锁）
        └── Playwright Chromium（headless=False 真实窗口）
```

- FastAPI 只出 JSON；现有 API 路由与逻辑全部保留（127 个后端测试保持通过）
- 页面路由由 vue-router 接管；FastAPI 页面路由改为 SPA fallback
- `app/templates/` 停用（不再作为渲染路径）

## 3. 登录会话子系统

### 3.1 状态机

```
not_started ──POST /api/auth/login──▶ starting ──成功──▶ waiting_login
                                                          │
                     轮询 GET /api/auth/status ◄───────────┘
                          │ 四信号判定（5s 间隔）
        ┌─────────────────┼──────────────────────┐
        ▼                 ▼                      ▼
     logged_in        expired（401 重检）     timeout（>5min）
```

额外状态：`error`（启动失败，可重试）、`closed`（登录中窗口被用户关闭 → 回 not_started）。

### 3.2 四信号登录判定（修复误判）

`is_logged_in(page)` 改为四信号交叉验证：

- **A 强否定（一票否决）**: 访问用户中心 URL，若跳转到 passport 域名或 `/login` 路径 → 未登录
- **B DOM 肯定**: 头像元素 /「退出登录」菜单存在 → +1
- **C Cookie 肯定**: 登录态 cookie（`wt2` / `__zp_stoken__` / `last_login_phone`，可配置）存在 → +1
- **D 接口金标准**: 轻量 wapi 用户接口，200 且含用户字段 → +1；401 → 直接未登录

判定: A 命中 → 未登录；否则 B/C/D 命中 ≥ 2 → 已登录；< 2 → unknown（不降级，连续 3 次同信号才切换）。

**回归测试要求**: 11 个匿名统计 cookie（HMACCOUNT/__a/__g 等）必须判定"未登录"（当前 bug 的复现用例）。

cookie 名与 wapi 接口路径做成配置项（ConfigItem），首次真实登录后抓包校准。

### 3.3 BrowserSessionManager

- `app/services/browser_session.py` 新文件；挂 `app.state.browser_session`
- 职责: 启动/停止 Playwright 持久化上下文（`data/browser_profile`）、状态机流转、cookie 落库（复用 Cookie 表）、并发安全（asyncio.Lock + 幂等）
- 生命周期: 由 `/api/auth/login` 触发启动；应用关闭时 stop
- 登录后 cookie 保存复用现有 `BrowserManager.save_cookie`

## 4. 看板数据模块

### 4.1 GET /api/dashboard/today

| 字段 | 口径 |
|---|---|
| delivered_today | `Application.applied_at ∈ 今天` 且 `status ∈ {applied, responded, interview, offer, rejected, withdrawn}` |
| daily_limit | `ConfigItem.daily_limit`，默认 20 |
| remaining_ratio | 1 - delivered_today / daily_limit |
| running_tasks / paused_tasks | `Task.status` 计数 |
| pending_followup | `Application.status == responded` 计数 |
| interview_offer | `Application.status ∈ {interview, offer}` 计数 |
| total_tokens / total_cost | **累计口径**（复用现有 `_compute_cost_stats`：`ConfigItem.ai_tokens_*` 键 + `price_per_1k` 单价）。注: token 统计未按日存储，**今日细分不可还原，不编造**，看板成本卡标注"累计" |
| recent_events | 最近 10 条 `ApplicationEvent`（id 倒序） |

### 4.2 GET /api/dashboard/deliveries?days=7

| 字段 | 口径 |
|---|---|
| trend | 近 N 天按 `applied_at` 日期分组每日投递数（含 0 的日期补全） |
| status_today | 今日 8 状态分布 |
| status_total | 累计 8 状态分布 |
| pending_manual_count | `status == pending_manual` 总数 |
| per_task | 按 task 分组的投递数（可选） |

状态枚举: skip / pending_manual / applied / responded / interview / offer / rejected / withdrawn。

## 5. 前端结构

```
efw-ai/frontend/
├── vite.config.js          # dev: /api 代理 → 127.0.0.1:8000
├── index.html
└── src/
    ├── main.js / App.vue   # 全局布局: 顶导航 + 常驻登录状态条
    ├── router/index.js     # 6 路由（history）
    ├── api/client.js       # fetch 封装: JSON/错误 toast/loading
    ├── components/         # LoginStatusBar / StatCard / TrendChart(ECharts)
    │                       # StatusDistribution / EventTimeline / TaskTable
    └── views/              # Dashboard / Applications / SemiQueue
                            # TaskDetail(SSE) / Config / Chat(SSE+确认卡片)
```

| 路由 | 数据源 |
|---|---|
| `/` 看板 | dashboard API ×2 + `/api/tasks` |
| `/applications` | 现有 `/api/applications`（status/task_id 过滤） |
| `/semi-queue` | 现有半自动确认/跳过接口 |
| `/tasks/:id` | 现有任务接口 + `/api/tasks/events`（SSE） |
| `/config` | 现有 `/api/config` GET/PUT |
| `/chat` | 现有 `/api/chat`（SSE 流式 + 写操作确认卡片） |

样式: 手写 CSS 设计系统（无重型组件库），沿用主色 #1a1a2e 风格，响应式（移动端适配）。

## 6. 后端改动清单

1. `app/main.py`: 删除 8 个 Jinja2 页面渲染路由 → SPA fallback（`/{path:path}` 返回 dist/index.html，排除 /api/ 与静态资源）；挂载 auth/dashboard 路由；初始化 `app.state.browser_session`
2. 新增 `app/services/browser_session.py`: BrowserSessionManager
3. 新增 `app/api/auth.py`: status / login / check
4. 新增 `app/api/dashboard.py`: today / deliveries
5. `app/worker/browser.py`: `is_logged_in` 改造为四信号（B/C/D 信号需访问 DOM/cookie/接口）
6. `frontend/dist` 构建产物进 .gitignore（本地工具，不提交构建物）

## 7. 测试策略

- 后端 pytest（现有 127 保持全绿）:
  - `test_auth.py`: 状态机（mock BrowserManager）+ 四信号判定 + 匿名 cookie 回归用例
  - `test_dashboard_api.py`: 今日口径/配额/8 状态分布/7 天趋势（含补 0 日期）
- 前端: 核心组件冒烟（LoginStatusBar 状态渲染）；验收 = `vite build` 通过 + FastAPI 托管 curl `/` 返回 index.html
- 联调验收: 起后端 → 8000 → 登录流端到端（未登录→弹窗→人工登录→状态变绿→看板刷新）→ 全量 pytest

## 8. 错误处理与边界

见第四节设计表（启动失败/超时/关窗/401 失效/验证码/并发/抖动/空态/404/dist 未构建/SSE 断线/写操作 loading），全部有用户可见反馈，不静默失败。核心原则: 登录状态机是唯一新增复杂逻辑；其余为"现有 API + 新壳"。

## 9. 迁移顺序（供实施计划使用）

1. 后端: BrowserSessionManager + auth API + dashboard API + is_logged_in 四信号（TDD）
2. 前端: Vite 脚手架 + 路由 + 布局 + 登录状态条 + 看板页
3. 前端: 其余 5 页迁移（复用现有 API）
4. 联调: SPA fallback + 构建托管 + 登录流端到端 + 全量回归
