[English](#english) | [简体中文](#简体中文)

---

# English

![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-compose-blue)

# Agent Review

Policy-grounded automated code review agent.

Agent Review receives GitHub pull request webhooks, runs deterministic evidence collectors (Semgrep SAST, SonarQube, GitHub CI annotations, secrets scanning), normalizes and deduplicates findings, uses an LLM to prioritize and explain them, evaluates a YAML gate policy to produce a merge verdict, and posts structured feedback as GitHub Check Runs and PR Reviews.

It also supports full-repository baseline scans and standalone local directory scanning without any GitHub dependency.

## Features

- **Automated PR review** via GitHub App webhooks (open, synchronize, ready_for_review)
- **Baseline repository scanning** through the GitHub API for establishing code quality baselines
- **Standalone local scanning** of any directory, no GitHub account required
- **Multi-collector evidence pipeline**: Semgrep SAST, SonarQube, GitHub CI annotations, secrets scanning
- **LLM-powered reasoning** via [litellm](https://docs.litellm.ai/) (OpenAI, Google Gemini, GitHub Models, Anthropic, Azure, and more)
- **YAML gate policy** with blocking/advisory classification, per-repo overrides, and emergency bypass
- **Web dashboard** for browsing scan results with detailed finding breakdowns
- **CLI** for scripting, CI integration, and local development
- **Docker Compose** deployment with PostgreSQL 16

## Quick Start

```bash
git clone https://github.com/kylecui/code-review-agent.git
cd code-review-agent
cp .env.example .env
# Edit .env with your GitHub App credentials and LLM API key
docker compose up -d
```

Open a PR on an installed repository, or trigger a scan manually. View results at `/ui/scans`.

## Usage Modes

### 1. PR Review (automatic)

Install the GitHub App on your repositories. The agent reviews PRs automatically when they are opened or updated.

### 2. Baseline Scan (via GitHub API)

Scan an entire repository to establish a code quality baseline:

```bash
python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output markdown
```

### 3. Local Scan (standalone, no GitHub required)

Scan any local directory directly:

```bash
python -m agent_review scan-local \
  --path /code/myrepo \
  --output json
```

Output formats: `json`, `markdown`, `github-issue` (baseline only).

## LLM Providers

The agent uses [litellm](https://docs.litellm.ai/docs/providers) as its LLM abstraction. Swap providers by changing model strings and API keys.

| Provider | API Key Env Var | Classify Model | Synthesize Model |
|----------|----------------|----------------|------------------|
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` | `gpt-4o` |
| Google Gemini | `GEMINI_API_KEY` | `gemini/gemini-2.0-flash` | `gemini/gemini-2.5-pro` |
| GitHub Models | `GITHUB_API_KEY` | `github/gpt-4o-mini` | `github/gpt-4o` |

For other providers (Anthropic, Azure, Vertex AI, etc.), see the [litellm provider docs](https://docs.litellm.ai/docs/providers).

## Policy Configuration

Policies are YAML files in `policies/`. The gate controller evaluates each finding against blocking category patterns (e.g., `security.*`) and severity thresholds. Findings matching a blocking pattern or having HIGH/CRITICAL severity are classified as blocking; everything else is advisory.

Create per-repo overrides at `policies/{owner}/{repo}.yaml`. See [docs/user-guide.md](docs/user-guide.md) for full policy reference.

## Web UI

Navigate to `/ui/scans` on your deployed instance. The dashboard shows all scan runs with drill-down into individual findings, severity breakdowns, blocking/advisory classification explanations, and performance metrics.

<!-- TODO: Add screenshot -->

## Admin Dashboard

Agent Review includes a built-in admin dashboard for managing all aspects of the system.

### Features

- **Authentication**: Email/password login and GitHub OAuth
- **User Management**: Create, edit, activate/deactivate users with admin/viewer roles
- **Scan Management**: Browse scans with pagination and filters, view detailed findings, trigger new scans
- **Settings Management**: Modify LLM, collector, and limit settings at runtime without restarting
- **Policy Editor**: Edit YAML gate policies with syntax highlighting and validation, ETag conflict detection

### First-Time Setup

1. Navigate to your instance (e.g., `https://your-server.example.com`)
2. Register the first account — it automatically becomes the admin
3. Configure GitHub OAuth (optional) in `.env` for team access

### Access Control

| Role | Scans | Settings | Policies | Users |
|------|-------|----------|----------|-------|
| Admin (superuser) | View, Trigger, Cancel, Delete | View, Edit, Reset | View, Edit, Create, Delete | View, Create, Edit, Deactivate |
| Viewer | View only | — | — | — |

## Project Structure

```
src/agent_review/
  app.py              # FastAPI application factory
  config.py           # pydantic-settings configuration
  database.py         # Async SQLAlchemy engine and session factory
  models/             # ORM models (ReviewRun, Finding)
  schemas/            # Pydantic schemas
  api/                # API routers: health, scan, webhooks
  api/admin/          # Admin API routers (users, settings, policies, scans)
  auth/               # Authentication (JWT, OAuth, password hashing)
  frontend/           # React SPA (Vite + shadcn/ui)
  reporting/          # Output: JSON, Markdown, GitHub Issue
  scm/                # GitHub App auth, REST client
  classifier/         # File-pattern heuristic classifier
  collectors/         # Semgrep, SonarQube, GitHub CI, Secrets
  normalize/          # Findings normalizer and deduplicator
  reasoning/          # LLM client, prompt manager, synthesizer
  gate/               # YAML policy loader and gate controller
  pipeline/           # Pipeline runners and supersession logic
  observability/      # Structured logging and metrics
prompts/              # Jinja2 prompt templates
policies/             # YAML policy files
tests/                # Unit and integration tests (171 passing)
```

## Development

```bash
pip install uv
uv sync --dev
cp .env.example .env
make migrate    # Run database migrations
make serve      # Start dev server on port 8000
make lint       # Ruff check + format
make typecheck  # Mypy strict mode
make test       # Pytest with coverage
make check      # All of the above
```

## Documentation

- [User Guide](docs/user-guide.md) - Full setup, configuration, and operations reference
- [HOW-TO Guide](HOW-TO.md) - Step-by-step instructions for common tasks

## License

MIT

---

# 简体中文

![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![Docker](https://img.shields.io/badge/docker-compose-blue)

# Agent Review

基于策略的自动化代码审查代理。

Agent Review 接收 GitHub Pull Request 的 Webhook 事件，运行确定性的证据收集器（Semgrep SAST、SonarQube、GitHub CI 注解、密钥扫描），对发现结果进行归一化和去重，使用 LLM 进行优先级排序和解释，根据 YAML 策略生成合并决策，并以 GitHub Check Run 和 PR Review 的形式发布结构化反馈。

同时支持全仓库基线扫描，以及完全脱离 GitHub 的本地目录独立扫描。

## 功能特性

- **自动化 PR 审查** - 通过 GitHub App Webhook 自动触发（open、synchronize、ready_for_review）
- **仓库基线扫描** - 通过 GitHub API 对整个仓库进行扫描，建立代码质量基线
- **本地独立扫描** - 直接扫描任意本地目录，无需 GitHub 账号
- **多源证据收集** - Semgrep SAST、SonarQube、GitHub CI 注解、密钥扫描并行执行
- **LLM 智能分析** - 通过 [litellm](https://docs.litellm.ai/) 支持 OpenAI、Google Gemini、GitHub Models、Anthropic、Azure 等多种模型
- **YAML 策略引擎** - 阻断/建议分类、按仓库覆盖策略、紧急绕过机制
- **Web 仪表盘** - 浏览扫描结果，查看详细的发现分类和严重性分布
- **命令行工具** - 用于脚本集成、CI 流水线和本地开发
- **Docker Compose 部署** - 搭配 PostgreSQL 16，一键启动

## 快速开始

```bash
git clone https://github.com/kylecui/code-review-agent.git
cd code-review-agent
cp .env.example .env
# 编辑 .env，填入 GitHub App 凭据和 LLM API Key
docker compose up -d
```

在已安装 App 的仓库上发起 PR，或手动触发扫描。访问 `/ui/scans` 查看结果。

## 使用模式

### 1. PR 审查（自动）

将 GitHub App 安装到目标仓库。当 PR 被创建或更新时，代理自动进行审查。

### 2. 基线扫描（通过 GitHub API）

对整个仓库进行全量扫描，建立代码质量基线：

```bash
python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output markdown
```

### 3. 本地扫描（独立运行，无需 GitHub）

直接扫描本地目录：

```bash
python -m agent_review scan-local \
  --path /code/myrepo \
  --output json
```

输出格式：`json`、`markdown`、`github-issue`（仅基线扫描）。

## LLM 服务商

代理使用 [litellm](https://docs.litellm.ai/docs/providers) 作为 LLM 抽象层，切换服务商只需修改模型名称和 API Key。

| 服务商 | API Key 环境变量 | 分类模型 | 综合分析模型 |
|--------|-----------------|---------|-------------|
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` | `gpt-4o` |
| Google Gemini | `GEMINI_API_KEY` | `gemini/gemini-2.0-flash` | `gemini/gemini-2.5-pro` |
| GitHub Models | `GITHUB_API_KEY` | `github/gpt-4o-mini` | `github/gpt-4o` |

其他服务商（Anthropic、Azure、Vertex AI 等）请参考 [litellm 文档](https://docs.litellm.ai/docs/providers)。

## 策略配置

策略文件为 `policies/` 目录下的 YAML 文件。策略引擎根据阻断类别模式（如 `security.*`）和严重性阈值评估每个发现。匹配阻断模式或严重性为 HIGH/CRITICAL 的发现被归类为阻断项，其余为建议项。

按仓库覆盖策略：创建 `policies/{owner}/{repo}.yaml`。完整策略参考请见[用户指南](docs/user-guide.md)。

## Web 界面

在部署实例上访问 `/ui/scans`。仪表盘展示所有扫描记录，支持下钻查看单个发现的详情、严重性分布、阻断/建议分类说明和性能指标。

<!-- TODO: 添加截图 -->

## 管理仪表盘

Agent Review 内置管理仪表盘，用于管理系统的所有方面。

### 功能

- **身份认证**：邮箱/密码登录和 GitHub OAuth
- **用户管理**：创建、编辑、启用/停用用户，支持管理员/查看者角色
- **扫描管理**：分页浏览扫描记录，查看详细发现，触发新扫描
- **设置管理**：运行时修改 LLM、收集器和限制设置，无需重启
- **策略编辑器**：编辑 YAML 策略，支持语法高亮、验证和冲突检测

### 首次设置

1. 访问实例地址（如 `https://your-server.example.com`）
2. 注册第一个账号 — 自动成为管理员
3. 在 `.env` 中配置 GitHub OAuth（可选），方便团队访问

### 访问控制

| 角色 | 扫描 | 设置 | 策略 | 用户 |
|------|------|------|------|------|
| 管理员 | 查看、触发、取消、删除 | 查看、编辑、重置 | 查看、编辑、创建、删除 | 查看、创建、编辑、停用 |
| 查看者 | 仅查看 | — | — | — |

## 项目结构

```
src/agent_review/
  app.py              # FastAPI 应用工厂
  config.py           # pydantic-settings 配置管理
  database.py         # 异步 SQLAlchemy 引擎和会话工厂
  models/             # ORM 模型（ReviewRun、Finding）
  schemas/            # Pydantic 数据模式
  api/                # API 路由：健康检查、扫描、Webhook
  api/admin/          # Admin API 路由（用户、设置、策略、扫描）
  auth/               # 身份认证（JWT、OAuth、密码哈希）
  frontend/           # React SPA (Vite + shadcn/ui)
  reporting/          # 输出格式：JSON、Markdown、GitHub Issue
  scm/                # GitHub App 认证和 REST 客户端
  classifier/         # 文件模式启发式分类器
  collectors/         # 收集器：Semgrep、SonarQube、GitHub CI、Secrets
  normalize/          # 发现归一化和指纹去重
  reasoning/          # LLM 客户端、提示词管理、综合分析
  gate/               # YAML 策略加载和决策控制器
  pipeline/           # 流水线运行器和取代逻辑
  observability/      # 结构化日志和指标
prompts/              # Jinja2 提示词模板
policies/             # YAML 策略文件
tests/                # 单元测试和集成测试（171 个通过）
```

## 开发

```bash
pip install uv
uv sync --dev
cp .env.example .env
make migrate    # 运行数据库迁移
make serve      # 启动开发服务器（端口 8000）
make lint       # Ruff 检查 + 格式化
make typecheck  # Mypy 严格模式
make test       # Pytest 含覆盖率报告
make check      # 以上全部
```

## 文档

- [用户指南](docs/user-guide.md) - 完整的安装、配置和运维参考
- [HOW-TO 指南](HOW-TO.md) - 常见任务的分步操作说明

## 许可证

MIT
