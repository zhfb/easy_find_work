# easy_find_work (EFW)

> 一款集成多平台求职自动化工具，支持 AI 评估、自动投递、管道管理、简历解析与面试准备。

[![Java](https://img.shields.io/badge/Java-21-blue.svg)](https://adoptium.net/)
[![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.5.7-brightgreen.svg)](https://spring.io/projects/spring-boot)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![SQLite](https://img.shields.io/badge/SQLite-3-07405e.svg)](https://sqlite.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 技术栈

| 层次 | 技术 | 版本 |
|------|------|------|
| **语言** | Java | 21 (Temurin) |
| **后端框架** | Spring Boot | 3.5.7 |
| **ORM** | MyBatis-Plus | 3.5.9 |
| **数据库** | SQLite (via Xerial JDBC) | 3.45 |
| **浏览器自动化** | Playwright | 1.51 |
| **文档解析** | Apache Tika | 3.1 |
| **前端框架** | Next.js (App Router) | 16.0 |
| **UI 库** | React 19 + shadcn/ui + Framer Motion | — |
| **样式** | Tailwind CSS | 4 |
| **包管理** | pnpm | 9 |
| **构建工具** | Gradle | — |

---

## 功能总览

### 🤖 多平台自动投递
- 支持 **Boss直聘**、**猎聘**、**51job**、**智联招聘** 四个平台
- 基于 Playwright 的浏览器自动化，支持反检测
- 自动登录状态检测与 Cookie 持久化
- 每 3 秒轮询登录状态，登录成功自动保存 Cookie

### 🧠 A-G 七维评估引擎
基于 Career-Ops 的 A-G 七块评估体系适配：

| 维度 | 权重 | 说明 |
|------|------|------|
| **A** 角色匹配 | 20% | 岗位名称 + JD 描述完整性 |
| **B** 能力匹配 | 20% | 技能关键词匹配 + 经验年限 |
| **C** 薪酬合理 | 15% | 薪酬区间合理性与期望薪资 |
| **D** 公司文化 | 10% | 公司规模、融资阶段、HR 活跃度 |
| **E** 成长空间 | 15% | 晋升、期权、技术挑战描述 |
| **F** 面试准备 | 10% | JD 技术栈明确度、业务描述 |
| **G** 岗位合法性 | 10% | HR 活跃度、公司信息完整性 |

**评分机制**：每项 1-5 分，加权总分 ≥ 3.5 推荐投递。

### 🔍 岗位原型分类
自动识别 8 种岗位类型：
- `Tech-Backend` / `Tech-Frontend` / `Tech-Data` / `Tech-Ops`
- `Product` / `Design` / `Operation` / `General`

### 📊 求职管道管理
- 8 个规范状态（Evaluated → Applied → Responded → Interview → Offer → Rejected → Discarded → SKIP）
- 支持中/英/西文别名输入
- 按平台/状态筛选、统计数据

### 📄 简历管理
- **AI 自动生成**：根据 JD 生成 HTML 简历
- **PDF/Word 上传解析**：Apache Tika 提取文本
- **AI 技能分析**：自动提取技能标签、工作年限、目标岗位
- **自我进化**：每生成 10 份简历自动触发评审

### 🎙️ 面试准备
- **STAR+L 故事库**（Situation / Task / Action / Result / Learning）
- **15 道面试题**：行为、技术、薪酬、职业规划等维度
- **智能推荐**：根据 JD 匹配高相关度故事
- **面试文档生成**：一键生成完整面试准备文档

### 🤖 AI 集成
- 支持 **DeepSeek**（`deepseek-v4-flash` / `deepseek-v4-pro`）
- 支持 **OpenAI**（`gpt-4o` 等）
- 支持任何 OpenAI 兼容 API（Moonshot 等）
- Chat Completions + Responses API 双协议支持

---

## 快速启动

### 前置要求

- **Java 21**（建议使用 [Temurin](https://adoptium.net/)）
- **Node.js 20+**
- **pnpm 9+**（`npm install -g pnpm`）

### 方式一：一键启动（推荐）

后端自带前端静态资源，**启动后端即开即用**：

```bash
# 1. 构建前端
cd front
pnpm install
npx next build
cd ..

# 2. 复制前端到后端静态目录
rm -rf src/main/resources/static
cp -r front/out src/main/resources/static

# 3. 启动后端（端口 8888 API + 6866 GUI）
JAVA_HOME=/opt/homebrew/opt/openjdk@21 ./gradlew bootRun
```

打开浏览器访问 **http://localhost:6866** 即可使用。

### 方式二：前后端分离开发

```bash
# 终端 1：启动后端
JAVA_HOME=/opt/homebrew/opt/openjdk@21 ./gradlew bootRun

# 终端 2：启动前端开发服务器（支持热更新）
cd front
pnpm install
pnpm dev   # 默认 http://localhost:3000
```

---

## 配置指南

### 1. 环境配置（`http://localhost:6866/env-config`）

| 配置项 | 说明 | DeepSeek 示例 |
|--------|------|--------------|
| API Base URL | AI 服务地址 | `https://api.deepseek.com` |
| API Key | 你的 API 密钥 | `sk-xxx` |
| AI 模型 | 模型名称 | `deepseek-v4-flash` |
| 企业微信 Webhook | 通知机器人 URL | 可选 |

可直接点击预设按钮一键填充。

### 2. AI 配置（`http://localhost:6866/ai-config`）

- **技能介绍**：你的技能和经验描述，AI 据此生成个性化内容
- **AI 提示词**：生成模板，支持 `%s` 占位符

### 3. 平台配置

Boss直聘、猎聘、51job、智联招聘各有独立配置页，支持：
- 搜索关键词设置
- 城市/薪资筛选
- A-G 评估阈值滑块
- 黑名单管理

### 4. 平台登录

启动后在浏览器窗口对应标签页手动登录，系统自动检测并保存 Cookie：
```
猎聘：已登录 ✓
Boss：已登录 ✓
51job：未登录 → 手动登录后自动识别
智联招聘：未登录 → 手动登录后自动识别
```

---

## 项目结构

```
easy_find_work/
├── build.gradle.kts              # 后端构建配置
├── settings.gradle               # Gradle 项目名称
├── src/
│   ├── main/java/com/efw/
│   │   ├── EfwApplication.java   # 启动入口
│   │   ├── application/
│   │   │   ├── config/           # Spring 配置（CORS、静态资源、异步等）
│   │   │   ├── controller/       # REST API 控制器
│   │   │   ├── entity/           # 数据库实体
│   │   │   ├── mapper/           # MyBatis-Plus Mapper
│   │   │   ├── service/          # 业务逻辑层
│   │   │   └── init/             # 启动初始化器（建表、种子数据）
│   │   └── worker/
│   │       ├── boss/             # Boss直聘自动化
│   │       ├── liepin/           # 猎聘自动化
│   │       ├── job51/            # 51job自动化
│   │       ├── zhilian/          # 智联招聘自动化
│   │       ├── manager/          # Playwright 引擎管理器
│   │       ├── service/          # 平台岗位查询服务
│   │       └── utils/            # 工具类（常量、Bot 等）
│   └── test/java/com/efw/
│       └── application/service/  # 单元测试
├── front/
│   ├── app/                      # Next.js App Router 页面
│   │   ├── boss/                 # Boss 配置页
│   │   ├── liepin/               # 猎聘配置页
│   │   ├── 51job/                # 51job 配置页
│   │   ├── zhilian/              # 智联招聘配置页
│   │   ├── env-config/           # 环境变量配置
│   │   ├── ai-config/            # AI 配置
│   │   ├── pipeline/             # 求职管道
│   │   ├── resumes/              # 简历管理
│   │   ├── interview/            # 面试准备
│   │   └── components/           # 通用组件
│   └── components/ui/            # shadcn/ui 组件库
├── db/
│   └── efw.db                    # SQLite 数据库（自动创建）
├── output/
│   └── resumes/                  # 生成的简历和上传文件
└── templates/
    └── states.yml                # 管道状态定义
```

---

## API 概览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/evaluation/evaluate` | POST | 执行 A-G 岗位评估 |
| `/api/evaluation/threshold` | GET | 获取评估阈值 |
| `/api/evaluation/archetypes` | GET | 获取所有岗位原型 |
| `/api/pipeline/entries` | GET | 获取管道条目列表 |
| `/api/pipeline/entries` | POST | 添加管道条目 |
| `/api/pipeline/stats` | GET | 获取统计数据 |
| `/api/pipeline/states` | GET | 获取规范状态列表 |
| `/api/resume/generate` | POST | 生成简历 |
| `/api/resume/upload` | POST | 上传简历文件 |
| `/api/resume/analyze` | POST | AI 分析简历文本 |
| `/api/resume/list` | GET | 获取简历列表 |
| `/api/interview/stories` | GET/POST | 面试故事 CRUD |
| `/api/interview/questions` | GET | 获取面试题 |
| `/api/interview/prepare` | POST | 生成面试文档 |
| `/api/ai/config` | GET/POST | AI 配置管理 |
| `/api/config` | GET/POST | 环境变量配置 |

---

## 开发指南

### 运行测试

```bash
JAVA_HOME=/opt/homebrew/opt/openjdk@21 ./gradlew test
```

### 项目命名规范

- 包名：`com.efw.*`
- 应用名：`EfwApplication` / `EFW`
- 数据库：`efw.db`

### 调试浏览器自动化

Chrome 调试端口：`7866`，可直接连接 DevTools 调试。

---

## License

[MIT](LICENSE)

## 致谢

- [loks666/get_jobs](https://github.com/loks666/get_jobs) — 原始项目
- Career-Ops — A-G 评估体系与管道管理设计
