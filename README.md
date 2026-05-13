# easy_find_work (EFW)

一款集成多平台求职自动化工具，基于 Java 21 + Spring Boot 3 + Next.js 构建。

## 功能

- **多平台自动投递**：Boss直聘、猎聘、51job、智联招聘
- **A-G 评估引擎**：7 维岗位评分，智能筛选高质量岗位
- **求职管道管理**：投递状态跟踪、统计分析
- **简历管理**：AI 生成、PDF 上传解析、技能自动提取
- **面试准备**：STAR+L 故事库、面试题库
- **AI 驱动**：支持 DeepSeek / OpenAI / 兼容 API

## 快速开始

```bash
# 后端
./gradlew bootRun

# 前端（开发模式）
cd front && pnpm install && pnpm dev
```

访问 http://localhost:6866 使用 GUI。
