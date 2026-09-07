# EFW-AI 重新设计文档（设计稿）

> 日期：2026-09-07
> 状态：已通过分节评审，待用户终审
> 目标：在保留「AI 投递简历」主题的前提下，重新设计 easy_find_work 的逻辑、技术栈、方法与过程。

---

## 1. 设计输入（已与用户确认）

| 决策项 | 结论 |
|---|---|
| 交付物 | 本设计文档（本次不实施） |
| AI 角色 | AI 全程智能决策（解析→评估→决策→文案→跟进）+ 对话式助手（用户可选开启） |
| 投递方式 | 混合可配置：全自动 / 半自动按任务开关 |
| 平台范围 | 仅保留 Boss 直聘，架构做深 |
| 技术栈 | Python 3.12：FastAPI + SQLModel/SQLite + Playwright + Jinja2/htmx |
| 架构形态 | 单进程模块化单体（asyncio），四层单向依赖 |
| 项目代号 | EFW-AI（独立目录 `efw-ai`，不与老代码混放） |

与老项目的根本区别：老项目是「平台自动化工具 + 附带 AI 打招呼」；新项目是「AI Agent 驱动的投递决策系统，浏览器只是它的手」——决策链是系统大脑，Playwright 降级为可替换的执行器官。

---

## 2. 总体架构

四层单向依赖：**Web/API → Agent 编排 → 执行层 → 数据层**，任何一层只依赖下一层，均可独立测试（执行层可 mock 浏览器，编排层可 mock 执行层）。

```
┌─────────────────────────────────────────────────────────┐
│ ① Web / API 层（FastAPI，:8888）                          │
│    配置页 · 任务看板 · 投递清单 · 对话助手(可选) · SSE 推送    │
├─────────────────────────────────────────────────────────┤
│ ② Agent 编排层（核心 · asyncio 任务队列）                   │
│    JD解析 → 匹配评估 → 投递决策 → 文案生成 → 跟进分析          │
│    对话助手(可选开关)                                       │
├─────────────────────────────────────────────────────────┤
│ ③ 执行层（Playwright 1 个浏览器实例）                       │
│    BrowserManager(登录态/Cookie/反检测) + BossClient        │
├─────────────────────────────────────────────────────────┤
│ ④ 数据层（SQLite 单文件）                                  │
│    config · profile · task · job · application · chat     │
└─────────────────────────────────────────────────────────┘
```

关键决策：

1. **单进程 + asyncio**：Playwright 异步 API 与 LLM 调用共用一个事件循环；投递任务由进程内队列串行执行（单浏览器窗口下天然必须串行）。
2. **四层单向依赖**：每层职责单一、接口明确，可独立测试。
3. **决策链是大脑**：②层是系统核心，③层是可替换的执行器官。
4. **半自动内置**：半自动任务产出「投递清单 + 文案」落库并 SSE 推送，用户手动投递后标记，进入与全自动完全相同的跟进循环。

---

## 3. 领域模型与数据流

### 3.1 核心实体（6 类）

| 实体 | 职责 | 关键字段 |
|---|---|---|
| Profile 用户画像 | 描述"我是谁、我要什么" | skills、experience_years、expected_salary、target_city、intention（一句话求职意向）、resume_summary |
| Task 投递任务 | 一次投递任务的定义 | keywords、city、mode(auto/semi)、max_deliveries、match_threshold、rules(黑名单/薪资下限)、status |
| Job 岗位快照 | Boss 抓取的岗位 + LLM 解析结果 | boss_job_id、title、company、salary_text、salary_parsed、jd_text、jd_parsed(结构化)、url |
| Application 投递记录 | 决策与投递的完整事件 | job_id、task_id、mode、decision、match_score、llm_reason、message、status、applied_at |
| ChatMessage | 对话助手消息 | role、content、related_task_id、created_at |
| Config / Cookie / Blacklist | 系统配置、登录态、黑名单 | key-value / platform / 公司·职位·招聘者 |

### 3.2 核心数据流（投递闭环）

```
创建任务(Task) → 任务队列(asyncio)
  → ① BossClient 按关键词+城市搜索岗位 → Job 落库
  → ② 决策链逐岗执行：
       JD解析 → 匹配评估(LLM评分+规则兜底) → 投递决策
       ├─ 跳过 → Application(decision=skip, 附原因)
       └─ 投递 → 生成个性化文案(message)
           ├─ [全自动] BossClient 执行打招呼/投递 → status=applied
           └─ [半自动] 进入投递清单 → 用户手动投递 → 标记结果
  → ③ 每步通过 SSE 推送到前端看板
  → ④ 跟进循环(定时)：BossClient 读新消息 → 跟进分析器 → 状态推进
```

### 3.3 投递记录状态机

```
skip(跳过) ─────────────┐
pending_manual(待人工) ─┤ 半自动
applied(已投递) → responded(已回复) → interview(面试) → offer(拿到)
                    └→ rejected(拒绝) / withdrawn(主动放弃)
```

设计要点：

- **Job 与 Application 分离**：同一岗位可被多个任务评估，评估结果独立演进，天然支持重投/跟进。
- **决策可追溯**：每条 Application 记录 llm_reason（AI 为什么投/不投）。
- **半自动不丢上下文**：手动投递后点「已投递」即纳入跟进循环。
- **跟进循环独立于投递**：两种模式投递的岗位都进入消息监听 → 回复分析 → 状态推进。

---

## 4. 数据模型（SQLite 表结构）

单文件 `efw.db`，SQLModel（SQLAlchemy 2.0）定义，9 张表。

### 4.1 建表 DDL（设计稿）

**config**
```sql
key TEXT PRIMARY KEY,          -- api_base_url / api_key / model / chat_enabled / follow_up_minutes ...
value TEXT,                    -- JSON 序列化
updated_at TEXT
```

**profile**（单行）
```sql
id INTEGER PRIMARY KEY,
skills TEXT,                   -- "Linux,云原生,K8s,Python"
experience_years INTEGER,
expected_salary_min REAL, expected_salary_max REAL,
target_city TEXT,
intention TEXT,                -- 一句话求职意向
resume_summary TEXT,           -- AI 提炼的简历摘要（供文案生成）
updated_at TEXT
```

**task**
```sql
id INTEGER PRIMARY KEY,
name TEXT,
keywords TEXT,                 -- JSON 数组 ["linux运维","k8s"]
city TEXT,
mode TEXT CHECK(mode IN ('auto','semi')),
max_deliveries INTEGER,        -- 本次最大投递数
daily_limit INTEGER DEFAULT 20,-- 每日投递上限（风控）
match_threshold REAL DEFAULT 7.0,  -- 0-10 分阈值
rules TEXT,                    -- JSON {salary_min, exclude_companies[]}
status TEXT CHECK(status IN ('pending','running','paused','finished','stopped','failed')),
created_at TEXT, finished_at TEXT
```

**job**
```sql
id INTEGER PRIMARY KEY,
boss_job_id TEXT UNIQUE,       -- Boss encryptId（防重复入库）
title TEXT, company TEXT,
company_scale TEXT, financing_stage TEXT, industry TEXT,
salary_text TEXT, salary_min REAL, salary_max REAL,
experience_req TEXT, education_req TEXT, city TEXT,
jd_text TEXT,                  -- 原始 JD 全文
jd_parsed TEXT,                -- JSON：LLM 结构化 {responsibilities[], requirements[], tech_stack[], signals[]}
job_url TEXT,
created_at TEXT
```

**application**（核心表）
```sql
id INTEGER PRIMARY KEY,
job_id INTEGER REFERENCES job(id),
task_id INTEGER REFERENCES task(id),
mode TEXT CHECK(mode IN ('auto','semi')),
decision TEXT CHECK(decision IN ('deliver','skip','pending')),
match_score REAL,              -- 0-10 匹配分
llm_reason TEXT,               -- AI 决策理由（可追溯）
message TEXT,                  -- 生成的个性化打招呼文案
status TEXT CHECK(status IN ('skip','pending_manual','applied','responded','interview','offer','rejected','withdrawn')),
applied_at TEXT, updated_at TEXT,
UNIQUE(job_id, task_id)        -- 同任务不重复评估同一岗位
```

**application_event**
```sql
id INTEGER PRIMARY KEY,
application_id INTEGER REFERENCES application(id),
event_type TEXT,               -- evaluated / delivered / replied / status_changed ...
detail TEXT,                   -- 事件详情（如回复原文）
created_at TEXT
```

**chat_message**
```sql
id INTEGER PRIMARY KEY,
role TEXT CHECK(role IN ('user','assistant')),
content TEXT,
related_task_id INTEGER REFERENCES task(id),  -- 可空：对话绑定任务上下文
created_at TEXT
```

**cookie / blacklist**
```sql
cookie:   id, platform('boss'), cookie_json, user_data_dir, updated_at
blacklist:id, type('company'|'job'|'recruiter'), value, reason, created_at
```

### 4.2 表关系

```
task 1─N application
job 1─N application
application 1─N application_event
task 0─N chat_message（上下文关联）
profile 单行；config/cookie/blacklist 独立
```

### 4.3 设计要点

- `job.boss_job_id UNIQUE`：Boss 岗位加密 ID 去重，同一岗位跨任务只存一份快照。
- `application` 是核心事实表：一次评估+投递+跟进的全部证据（分、理由、文案、状态、事件链）。
- 分数口径统一 **0-10**（对齐通用 LLM 打分习惯），阈值默认 7.0。
- `application_event` 承载时间线，前端时间线/跟进分析从事件表读取，主表保持轻量。

---

## 5. AI 决策链（系统大脑）

### 5.1 五环节决策流水线

```
搜索到岗位
   ↓
① 规则预筛（零成本）     标题关键词 / 薪资下限 / 城市 / 黑名单 → 硬过滤，砍掉 60-80% 岗位
   ↓ 通过
② JD 解析（LLM ×1）     原始 JD → 结构化 jd_parsed（职责/要求/技术栈/风险信号），结果缓存
   ↓
③ 匹配评分（LLM ×1）     profile + jd_parsed → 0-10 分 + 评分理由
   ↓
④ 投递决策（纯规则）     硬规则(黑名单/薪资/限额) 优先 → 软规则(阈值) → deliver / skip / pending
   ↓ deliver
⑤ 文案生成（LLM ×1）     个性化打招呼语（点出具体技能与岗位关联，≤200 字）
   ↓
投递（auto 自动执行 / semi 进清单）
```

**每岗位最多 3 次 LLM 调用**；预筛与决策用纯规则，控制成本与延迟（老项目逐岗位调 LLM，成本高且慢）。

### 5.2 各环节设计

**① 规则预筛（RulesPreFilter）— 纯代码**
- 标题含黑名单词 / 公司黑名单 → skip
- 薪资区间与期望下限无重叠（Boss 面议则放行给 LLM 判断）→ skip
- 城市不匹配 → skip
- 命中任一硬条件立即淘汰，零 LLM 成本。

**② JD 解析（JdParser）— LLM 结构化输出**
- 输出 Pydantic 模型：`responsibilities[]`、`requirements[]`、`tech_stack[]`、`experience_hint`、`risk_signals[]`（如"急招""大量招人""薪资面议"）。
- 失败/超时 → 正则规则解析技术栈关键词，结果标记 `fallback=true`。
- 同一 `boss_job_id` 复用缓存，不重复解析。

**③ 匹配评分（Matcher）— LLM 打分 + 规则兜底**
- 输入：profile（技能/年限/期望薪资/求职意向）+ jd_parsed + 原始 JD。
- 输出：`score(0-10)` + `reason`（逐维依据：技能重合、经验、薪资、方向契合）。
- 规则兜底：技能重合率×5 + 经验匹配×3 + 薪资重叠×2 → 归一化 0-10。
- 低分岗位的 `reason` 也落库（Application.llm_reason），"为什么跳过"可追溯。

**④ 投递决策（Decider）— 纯规则，无 LLM**
- 硬规则（优先级最高）：黑名单 → skip；薪资 < rules.salary_min → skip；达到 daily_limit → 暂停任务。
- 软规则：`score ≥ threshold` → deliver；`score < threshold-1` → skip；中间区间 → pending（半自动交给用户决断；全自动按配置的存疑策略处理，默认保守跳过）。

**⑤ 文案生成（Writer）— LLM，模板兜底**
- 输入：resume_summary + 公司/岗位/tech_stack 要点 + 平台规范（Boss 首条消息规范）。
- 约束：≤200 字、必须点名 1-2 个岗位要求的具体技能、以开放问句收尾、禁止套话堆砌。
- 每次生成 3 个候选：全自动随机取 1（避免同文案批量发送触发风控）；半自动展示 3 条供选择。
- 兜底：模板组装（从 profile.skills 与 job.tech_stack 交集里选词成句）。

### 5.3 兜底与降级原则（贯穿全链）

| 场景 | 行为 |
|---|---|
| LLM 无 key / 超时 / 解析失败 | 当前环节走规则兜底，系统继续运行不瘫，退化为"关键词+规则"传统自动化 |
| 单环节 LLM 连续失败 3 次 | 熔断该环节 10 分钟，期间全走规则 |
| 每环节记录 token 用量 | 前端可见"本次任务 AI 成本估算"，成本透明 |

### 5.4 对话式助手如何复用决策链

开启后助手不另写一套逻辑：用户自然语言 → 解析意图 → **生成/修改 Task 配置** → 复用同一决策链执行；追问进展时从 application/event 表读实时数据回答。**助手是决策链的"遥控器"，不是第二条决策链。**

---

## 6. 执行引擎与风控

### 6.1 BrowserManager — 浏览器会话管理（单例）

| 能力 | 设计 |
|---|---|
| 浏览器实例 | `launch_persistent_context` 单实例 + 固定 `user_data_dir`（登录态天然持久化） |
| 启动逻辑 | 有有效 Cookie → 直接进已登录态；无 → 打开窗口等用户扫码，轮询检测登录成功后存 Cookie |
| 掉线检测 | 定时心跳：访问个人页判断会话是否被踢；掉线 → 立即暂停所有任务 + 通知用户 |
| headless 策略 | 默认有头（真实环境最稳），可选 headless；不做隐身模式伪装 |

### 6.2 BossClient — 平台适配层（唯一接触 Boss DOM/接口的模块）

```
search(keyword, city)      → 岗位列表
get_detail(job)            → JD 全文（触发 LLM 解析）
send_greeting(job, msg)    → 打招呼（全自动）
send_apply(job, msg)       → 投递（全自动）
read_messages()            → 消息流（跟进循环）
mark_applied(job)          → 半自动：用户手动投递后标记
```

- 列表解析**优先拦截 XHR JSON**（Boss 接口返回结构化 JSON，比 DOM 解析稳），失败兜底 DOM 解析。
- 岗位去重靠 `boss_job_id`（encryptId）；所有 DOM 操作走 Locator + 超时控制。

### 6.3 风控五层

| 层 | 机制 | 默认值 |
|---|---|---|
| ① 节奏 | 投递间隔随机化（非固定间隔，避免规律性） | 8–25 秒随机 |
| ② 频率 | 连续 N 次投递后强制休息 | 每 5 次休息 2–5 分钟 |
| ③ 配额 | 每日投递上限，超限自动暂停任务 | 20 次/天 |
| ④ 会话 | 掉线/踢下线检测 → 全任务暂停 + 通知 | 实时 |
| ⑤ 人机验证 | 检测到滑块/验证码 → **暂停并通知用户手动处理**（不做全自动过人机验证） | 实时 |

辅助策略：文案多样性（3 候选随机取）、真实浏览器环境（真实 UA/视口/时区，注入反检测脚本清除自动化标记）。

### 6.4 半自动模式

全自动：决策链 → `send_greeting/send_apply` 直接执行。
半自动：决策链 → 生成 `application(decision=deliver, status=pending_manual)` → 前端投递清单（岗位卡片 + 3 条候选文案 + 「复制」「去投递」「标记已投递」）→ 用户标记后进入与全自动完全相同的跟进循环。

### 6.5 异常与恢复

- **崩溃恢复**：进程重启后 `running` 任务标记为 `interrupted`，提供"一键续跑"——任务表记录 `last_job_id` 游标，从上次位置继续；已评估岗位不重复评估（application 表 UNIQUE 约束兜底）。
- **失败隔离**：单个岗位投递失败只记事件不中断任务；连续失败 5 个岗位才暂停任务并告警。

---

## 7. API 与前端

### 7.1 前端技术选型：Jinja2 + htmx + Alpine.js（服务端渲染）

Python 栈下不需要 Node 构建链：

- **零构建**，FastAPI 直接托管模板
- 单进程 `uvicorn` 搞定部署
- SSE 同源原生 EventSource
- 对话助手流式 = EventSource + 少量 JS
- 适合个人工具（表单 + 看板 + 清单 + 聊天）的复杂度

htmx 处理表单/局部刷新，Alpine.js 处理轻交互。

### 7.2 API 清单（FastAPI，前缀 /api）

**配置**
| 端点 | 方法 | 说明 |
|---|---|---|
| /config | GET/PUT | 环境配置（API Key/模型/对话开关/风控参数） |
| /profile | GET/PUT | 用户画像 |
| /blacklist | GET/POST/DELETE | 黑名单 |

**任务**
| 端点 | 方法 | 说明 |
|---|---|---|
| /tasks | GET/POST | 列表 / 创建 |
| /tasks/{id} | GET | 详情 + 统计 |
| /tasks/{id}/start /pause /resume /stop | POST | 任务控制 |
| /tasks/{id}/resume-after-crash | POST | 崩溃后续跑 |
| /tasks/{id}/events | GET(SSE) | 实时进度流 |

**投递记录**
| 端点 | 方法 | 说明 |
|---|---|---|
| /applications | GET | 列表（按状态/任务/日期筛选） |
| /applications/{id} | GET | 详情（分数/llm_reason/文案/事件时间线） |
| /applications/{id}/status | POST | 更新状态（半自动标记已投递等） |
| /applications/{id}/regenerate-message | POST | 重新生成文案 |

**对话助手（chat_enabled 开启后启用）**
| 端点 | 方法 | 说明 |
|---|---|---|
| /chat | POST(SSE) | 发送消息，流式回复 |
| /chat/history | GET | 历史消息 |

**系统**：/health、/boss/login-status

### 7.3 页面结构（7 个页面）

| 路由 | 页面 | 核心内容 |
|---|---|---|
| / | 看板 | 今日投递统计、任务列表、状态分布、Boss 登录状态横幅 |
| /tasks/new | 创建任务 | 关键词/城市/模式开关/阈值/限额/规则表单 |
| /tasks/{id} | 任务详情 | SSE 实时进度、岗位评估流、跳过原因、投递结果 |
| /applications | 投递记录 | 筛选 + 状态分布 + 搜索 |
| /applications/{id} | 投递详情 | llm_reason、文案、事件时间线、状态推进操作 |
| /semi-queue | 半自动清单 | 待人工投递岗位卡片 + 3 条文案 + 复制/去投递/标记 |
| /chat | 对话助手 | 流式对话（仅 chat_enabled 开启时显示） |

画像与设置并入看板弹窗，减少页面数。

---

## 8. 对话式助手（可选模块，chat_enabled 开关）

**定位**：决策链的"遥控器 + 仪表盘"，不是第二条决策链。

| 能力 | 示例 | 实现 |
|---|---|---|
| 配置操控 | "这周主投 k8s 岗，阈值降到 6.5" | Function Calling → 更新 task/config |
| 任务控制 | "开始投递""暂停" | Function Calling → 调任务 API |
| 进展查询 | "今天投了几个？谁回复了？" | 读 application/event 表回答 |
| 决策解释 | "为什么跳过 XX 公司？" | 读该条 llm_reason |
| 文案优化 | "把打招呼语改得更有诚意" | 调文案生成器重写 |

**安全边界**：写操作不直接执行 —— LLM 调工具后返回"待确认卡片"，用户在聊天里点确认才落地（改配置/启动任务/重新生成文案同理）。只读查询直接回答。与半自动模式"人做最后决定"的理念一致。

**技术**：OpenAI 兼容 Function Calling + SSE 流式；历史存 chat_message 表；无 API Key 时 /chat 返回不可用提示，不影响其他功能。

---

## 9. 新项目结构与依赖

### 9.1 目录结构（独立目录 efw-ai）

```
efw-ai/
├── app/
│   ├── main.py                # FastAPI 入口
│   ├── config.py              # Pydantic Settings
│   ├── db.py / models.py      # SQLModel 引擎 + 9 表
│   ├── schemas.py             # API 请求/响应模型
│   ├── api/                   # config/profile/tasks/applications/chat 路由
│   ├── agent/                 # AI 决策链（大脑）
│   │   ├── llm.py             #   LlmClient：OpenAI 兼容/重试/熔断/token 统计
│   │   ├── prefilter.py       #   ① 规则预筛（零成本）
│   │   ├── jd_parser.py       #   ② JD 解析
│   │   ├── matcher.py         #   ③ 匹配评分
│   │   ├── decider.py         #   ④ 投递决策（纯规则）
│   │   ├── writer.py          #   ⑤ 文案生成
│   │   ├── followup.py        #   跟进分析器
│   │   └── orchestrator.py    #   决策链编排（asyncio）
│   ├── worker/                # 执行层（手）
│   │   ├── browser.py         #   BrowserManager
│   │   ├── boss_client.py     #   BossClient
│   │   └── anti_detection.js
│   ├── services/              # task_service / application_service / chat_service
│   ├── templates/             # Jinja2：dashboard/task_detail/applications/semi_queue/chat
│   └── static/
├── data/                      # efw.db + user_data_dir（gitignore）
├── tests/                     # pytest：决策链 mock LLM + 执行层 mock 浏览器
├── pyproject.toml             # uv 管理依赖
└── README.md
```

### 9.2 依赖清单

- fastapi · uvicorn[standard] · sqlmodel · jinja2 · python-multipart
- playwright
- openai（兼容 DeepSeek / Moonshot 等）
- pydantic-settings · httpx
- pytest · pytest-asyncio（测试）

---

## 10. 落地方式（实施路线图，本次不实施）

| 阶段 | 内容 | 验收标准 |
|---|---|---|
| 0 | 骨架：FastAPI + SQLModel 建表 + 看板页面 | 启动后看板可见，配置可保存 |
| 1 | BrowserManager + BossClient：登录/Cookie/搜索 | 浏览器可登录并抓到岗位落库 |
| 2 | 决策链（**规则兜底先行**，LLM 后接） | mock LLM 时全链路可跑通 |
| 3 | 投递执行（auto/semi）+ SSE + 风控五层 | 全自动跑完一天配额，半自动清单可用 |
| 4 | 跟进循环：读消息 → 状态推进 | HR 回复能自动推进状态 |
| 5 | 对话助手（chat_enabled 开关） | 对话可查进展/改配置（带确认） |
| 6 | 打磨：成本统计、崩溃续跑、README | 全功能回归 |

关键原则：**第 2 阶段"规则先行"**——先让 LLM 全部 mock 掉也能投递，再逐步点亮 LLM 环节，避免"LLM 挂了整个系统就废"。

---

## 11. 测试策略

- **决策链单元测试**：mock LlmClient（固定返回值 + 故障注入），验证每一环节的规则兜底路径。
- **执行层测试**：mock 浏览器页面对象，验证 BossClient 的解析与投递逻辑（不连真实网站）。
- **风控测试**：模拟日配额用尽、掉线、验证码出现 → 断言任务正确暂停。
- **半自动流程测试**：模拟用户标记"已投递" → 断言进入跟进循环。
- **集成测试**：SQLite 内存库 + TestClient 跑 API 全链路。
