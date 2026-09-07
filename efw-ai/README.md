# EFW-AI 智能投递助手

基于 LLM 决策链的自动化岗位投递助手，支持 Boss 直聘平台的岗位筛选、匹配评分、打招呼文案生成与自动投递。

## 功能特性

- **智能决策链**：预筛 → JD 解析 → 匹配评分 → 决策 → 文案生成，每岗位最多 3 次 LLM 调用
- **双模式投递**：全自动（AI 直接打招呼）/ 半自动（AI 筛选后人工确认）
- **崩溃续跑**：进程异常退出后自动标记中断任务，支持从游标恢复
- **跟进循环**：后台定时检查已投递岗位的回复状态并自动推进
- **对话式助手**：通过自然语言查询统计、控制任务运行
- **风控五层**：日配额、频率控制、验证码检测、冷却期、黑名单
- **成本统计**：LLM token 用量累计与费用估算

## 安装

```bash
# 安装 Python 依赖
uv sync

# 安装 Playwright 浏览器（用于自动投递）
uv run playwright install chromium
```

要求 Python >= 3.12。

## 配置

首次启动后访问 `http://127.0.0.1:8888/config` 配置以下项：

| Key | 说明 | 默认值 |
|-----|------|--------|
| `base_url` | LLM API 地址 | - |
| `api_key` | LLM API 密钥 | - |
| `model` | LLM 模型名称 | - |
| `follow_up_minutes` | 跟进循环间隔（分钟） | 10 |
| `price_per_1k` | 每千 token 单价（元），用于成本估算 | 0 |
| `chat_enabled` | 是否启用对话助手入口 | true |

也可通过 API 配置：
```bash
curl -X PUT http://127.0.0.1:8888/api/config \
  -H "Content-Type: application/json" \
  -d '{"key": "base_url", "value": "https://api.openai.com/v1"}'
```

## 启动

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8888
```

启动后访问：
- 看板：`http://127.0.0.1:8888/`
- 投递记录：`http://127.0.0.1:8888/applications`
- 半自动清单：`http://127.0.0.1:8888/semi-queue`
- 智能助手：`http://127.0.0.1:8888/chat`
- 配置：`http://127.0.0.1:8888/config`

## 测试

```bash
uv run pytest -v
```

## 项目结构

```
app/
├── main.py              # FastAPI 入口、页面路由、lifespan、崩溃恢复
├── db.py                # 数据库引擎与会话
├── models.py            # 9 张表的 SQLModel 定义
├── schemas.py           # Pydantic 请求模型
├── state.py             # 应用状态（SSE 广播、任务标志）
├── api/                 # REST API 路由
│   ├── tasks.py         # 任务 CRUD + 运行控制 + SSE
│   ├── applications.py  # 投递记录
│   ├── config.py        # 配置
│   ├── profile.py       # 个人档案
│   └── chat.py          # 对话助手
├── agent/               # LLM 决策链
│   ├── prefilter.py     # 规则预筛
│   ├── jd_parser.py     # JD 解析
│   ├── matcher.py       # 匹配评分
│   ├── decider.py       # 决策
│   ├── writer.py        # 文案生成
│   ├── llm.py           # LLM 客户端 + 熔断器
│   ├── orchestrator.py  # 编排器
│   └── followup.py      # 跟进分析
├── services/            # 业务服务层
│   ├── task_service.py       # 任务运行服务
│   ├── application_service.py # 投递记录服务
│   ├── followup_service.py   # 跟进服务
│   ├── chat_service.py       # 对话服务
│   ├── stats_service.py      # 统计服务
│   ├── risk_controller.py    # 风控
│   └── config_service.py     # 配置服务
├── worker/              # 执行层
│   ├── browser.py       # 浏览器管理
│   └── boss_client.py   # Boss 直聘客户端
└── templates/           # Jinja2 模板
    ├── base.html
    ├── dashboard.html
    ├── task_detail.html
    ├── applications.html
    ├── application_detail.html
    ├── semi_queue.html
    ├── chat.html
    └── config.html
```

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET/POST | `/api/tasks` | 任务列表/创建 |
| GET | `/api/tasks/{id}` | 任务详情 |
| POST | `/api/tasks/{id}/start` | 启动任务 |
| POST | `/api/tasks/{id}/pause` | 暂停任务 |
| POST | `/api/tasks/{id}/resume` | 继续任务 |
| POST | `/api/tasks/{id}/stop` | 停止任务 |
| POST | `/api/tasks/{id}/resume-after-crash` | 崩溃后续跑 |
| GET | `/api/tasks/{id}/events` | SSE 进度流 |
| GET | `/api/applications` | 投递记录列表 |
| GET | `/api/applications/{id}` | 投递详情 |
| POST | `/api/applications/{id}/status` | 更新状态 |
| POST | `/api/applications/{id}/regenerate-message` | 重生成文案 |
| GET/PUT | `/api/config` | 配置读取/更新 |
| GET/PUT | `/api/profile` | 档案读取/更新 |
| POST | `/api/chat` | 对话（SSE 流式） |

## 免责声明

本项目仅供个人学习与研究使用。使用时请遵守目标平台的用户协议与相关法律法规，不得用于大规模爬虫、垃圾投递或任何违反平台规则的行为。作者不对使用本工具导致的任何账号封禁、法律纠纷或其他后果承担责任。
