# Agent Review 用户手册

> **版本**：0.1.0  
> **适用对象**：运维人员、开发者、平台管理员  
> **许可证**：MIT

---

## 目录

- [第一章：项目概述](#第一章项目概述)
- [第二章：部署指南](#第二章部署指南)
- [第三章：GitHub App 配置](#第三章github-app-配置)
- [第四章：环境变量参考](#第四章环境变量参考)
- [第五章：使用指南](#第五章使用指南)
- [第六章：策略配置](#第六章策略配置)
- [第七章：管理后台](#第七章管理后台)
- [第八章：Web 仪表盘](#第八章web-仪表盘)
- [第九章：流水线架构详解](#第九章流水线架构详解)
- [第十章：运维指南](#第十章运维指南)
- [第十一章：二次开发指南](#第十一章二次开发指南)
- [第十二章：LLM 服务商配置](#第十二章llm-服务商配置)
- [附录](#附录)

---

# 第一章：项目概述

## 1.1 产品简介

Agent Review 是一个**基于策略的自动化代码审查代理**。
它接收 GitHub Pull Request 的 Webhook 事件。
它运行确定性的证据收集器（Semgrep SAST、SonarQube、GitHub CI 注解、密钥扫描）。
它对发现结果做归一化和去重。
它使用大语言模型（LLM）进行优先级排序和解释。
它根据 YAML 策略生成合并决策。
它通过 GitHub Check Run 和 PR Review 发布结构化反馈。

Agent Review 还支持两种补充模式：
- **全仓库基线扫描**：通过 GitHub API 扫描整个仓库，用于建立代码质量基线
- **本地独立扫描**：直接扫描任意本地目录，不依赖 GitHub 账号

## 1.2 核心特性

| 特性 | 说明 |
|------|------|
| **自动 PR 审查** | 通过 GitHub App Webhook 自动触发（open、synchronize、ready_for_review） |
| **仓库基线扫描** | 通过 GitHub API 对整个仓库进行全量扫描 |
| **本地独立扫描** | 直接扫描任意本地目录，无需 GitHub 账号 |
| **多源证据收集** | Semgrep SAST、SonarQube、GitHub CI 注解、密钥扫描并行执行 |
| **LLM 智能分析** | 通过 litellm 支持 OpenAI、Google Gemini、GitHub Models、Anthropic 等 |
| **YAML 策略引擎** | 阻断/建议分类、按仓库覆盖策略、紧急绕过机制 |
| **Web 仪表盘** | 浏览扫描结果，查看详细的发现分类和严重性分布 |
| **命令行工具** | 用于脚本集成、CI 流水线和本地开发 |
| **管理后台** | 用户管理、运行时设置、策略编辑器、扫描管理 |
| **Docker Compose 部署** | 搭配 PostgreSQL 16，一键启动 |

## 1.3 系统架构概览

Agent Review 使用**七阶段流水线**处理每次代码审查：

```
SCM Event (PR opened / synchronize / ready_for_review)
  → 1. Webhook 接收（签名验证、去重、Bot/草稿过滤）
  → 2. 文件分类（文件模式匹配 → 类别、风险级别、Profile）
  → 3. 证据收集（Semgrep + SonarQube + GitHub CI + Secrets 并行）
  → 4. 归一化（统一 Schema + 指纹去重）
  → 5. LLM 推理（优先级排序 + 解释 + 降级处理）
  → 6. 策略决策（Profile 评估 → PASS/WARN/REQUEST_CHANGES/BLOCK/ESCALATE）
  → 7. 结果发布（GitHub Check Run + PR Review + 行内评论）
```

## 1.4 设计原则

1. **推理与执行分离**：LLM 负责分类、优先级排序、解释和修复建议。CI/策略系统负责是否允许合并。
2. **确定性工具优先**：系统优先使用 linter、类型检查器、测试框架、Semgrep、SonarQube 生成证据。LLM 仅在证据之上推理。
3. **按 Profile 审查**：认证模块变更与文档变更面临的风险不同，因此不应共用一条审查路径。
4. **结构化发现**：每个发现都包含类别、严重性、置信度、证据、影响和修复建议。
5. **低噪声输出**：如果评论数量多但信息密度低，审查结果会被忽略。因此系统偏向高信号输出。

## 1.5 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | Python 3.12+, FastAPI, Uvicorn, Gunicorn |
| **数据库** | PostgreSQL 16（生产）/ SQLite（开发），SQLAlchemy async, Alembic |
| **前端** | React 19, Vite 6, TailwindCSS 4, shadcn/ui, TanStack Router + Query, Monaco Editor |
| **LLM 抽象** | litellm（支持 OpenAI、Gemini、Anthropic、Azure、GitHub Models 等） |
| **证据收集** | Semgrep（SAST）, SonarQube, GitHub CI Annotations, GitHub Secrets Scanning |
| **认证** | JWT, GitHub OAuth (Authlib), Argon2/bcrypt 密码哈希 (pwdlib) |
| **可观测性** | structlog 结构化日志 |
| **包管理** | uv (Python), npm (Node.js) |
| **代码质量** | Ruff (lint + format), Mypy (strict), Pytest + pytest-cov |

---

# 第二章：部署指南

## 2.1 前提条件

### 通用要求

| 要求 | 说明 |
|------|------|
| Python | 3.12 或更高版本 |
| LLM API Key | 至少一个 LLM 服务商的 API Key（OpenAI、Gemini、Anthropic 等） |

### PR 审查和基线扫描（需要 GitHub）

| 要求 | 说明 |
|------|------|
| GitHub 账号 | 具有目标仓库管理员权限 |
| GitHub App | 已创建并安装（参见第三章） |

### 生产部署

| 要求 | 说明 |
|------|------|
| Docker | Docker Engine 20.10+ |
| Docker Compose | v2 或更高 |

### 可选依赖

| 依赖 | 说明 |
|------|------|
| Semgrep App Token | 通过 Semgrep API 进行 SAST 扫描 |
| SonarQube 实例 | 代码质量分析 |
| ngrok | 本地测试 Webhook 时暴露端点 |

> **仅需本地扫描？** 你只需要 Python 3.12+ 和 LLM API Key。

## 2.2 Docker Compose 生产部署（推荐）

### 步骤

```bash
# 1. 克隆仓库
git clone https://github.com/kylecui/code-review-agent.git
cd code-review-agent

# 2. 复制并编辑配置文件
cp .env.example .env
# 编辑 .env，填入 GitHub App 凭据、LLM API Key 等

# 3. 启动服务
docker compose up -d
```

### 服务说明

`docker-compose.yml` 定义了两个服务：

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| `db` | `postgres:16-alpine` | 5432 | PostgreSQL 数据库，带健康检查 |
| `app` | 本地构建 | 8000 | Agent Review 应用（自动等待数据库就绪） |

默认应用连接字符串：`postgresql+asyncpg://agent_review:agent_review_dev@db:5432/agent_review`

### Docker 构建过程

Dockerfile 采用多阶段构建：

1. **前端构建阶段**：使用 `node:22-slim`，执行 `npm ci` 和 `npm run build`
2. **Python 应用阶段**：使用 `python:3.12-slim`
   - 安装 `uv` 包管理器
   - 安装 Python 依赖
   - 克隆 Semgrep 社区规则到 `/opt/semgrep-rules`
   - 安装 `semgrep` CLI
   - 复制前端构建产物到 `/app/static`
   - 以非 root 用户 `appuser` 运行

### 生产部署注意事项

- **数据库密码**：修改 `docker-compose.yml` 中 `POSTGRES_PASSWORD` 为强密码，并同步更新 `.env` 中的 `AGENT_REVIEW_DATABASE_URL`
- **SECRET_KEY**：修改 `AGENT_REVIEW_SECRET_KEY` 为随机强密码（用于 JWT 和会话加密）
- **HTTPS**：生产环境必须通过反向代理（如 nginx、Caddy）提供 HTTPS
- **数据持久化**：PostgreSQL 数据通过 Docker volume `pgdata` 持久化

## 2.3 本地开发部署

```bash
# 1. 克隆仓库
git clone https://github.com/kylecui/code-review-agent.git
cd code-review-agent

# 2. 安装 uv（如未安装）
pip install uv

# 3. 安装依赖
uv sync --dev

# 4. 复制并编辑配置文件
cp .env.example .env

# 5. 运行数据库迁移
make migrate

# 6. 启动开发服务器
make serve
```

开发模式下有以下行为：
- 默认使用 SQLite 数据库（`sqlite+aiosqlite:///./dev.db`）
- Uvicorn 运行在 `http://localhost:8000`，支持热重载
- 不需要 Docker

### 前端开发

```bash
cd frontend

# 安装依赖
npm ci

# 启动开发服务器
npm run dev

# 类型检查
npm run type-check

# Lint
npm run lint

# 构建生产版本
npm run build

# 生成 API 客户端（从 openapi.json）
npm run generate-api
```

## 2.4 Webhook 端点暴露

GitHub 需要通过 HTTPS 访问你的 Webhook URL `https://your-server.example.com/webhooks/github`。

### 方案一：ngrok（快速测试）

```bash
ngrok http 8000
# 使用生成的 HTTPS URL 作为 GitHub App 的 Webhook URL
```

### 方案二：云服务器 + 反向代理

在公网 IP 的服务器上，使用 nginx 或 Caddy 作为反向代理：

```nginx
# nginx 示例
server {
    listen 443 ssl;
    server_name review.example.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 方案三：PaaS 平台

支持的平台：Cloud Run、Fly.io、Railway、Render 等。

## 2.5 资源估算

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 1 vCPU | 2 vCPU |
| 内存 | 512 MB | 1 GB |
| 磁盘 | 1 GB | 5 GB（含 Semgrep 规则） |
| 数据库 | SQLite（开发） | PostgreSQL 16（生产） |

### LLM 成本估算

使用 `gpt-4o-mini`（分类）+ `gpt-4o`（综合分析）时，每次审查约 **$0.01 - $0.10**，具体取决于 diff 大小。你可以通过 `AGENT_REVIEW_LLM_COST_BUDGET_PER_RUN_CENTS` 设置单次审查费用上限。

## 2.6 健康检查

部署完成后，验证服务状态：

```bash
# 存活检查（始终返回 ok）
curl http://localhost:8000/health
# 响应：{"status":"ok"}

# 就绪检查（验证数据库连接）
curl http://localhost:8000/ready
# 响应：{"status":"ready"}
```

两个端点都返回成功后，服务即处于就绪状态。

---

# 第三章：GitHub App 配置

> 如果只需要本地独立扫描，可跳过本章。

## 3.1 创建 GitHub App

1. 进入 **GitHub Settings > Developer Settings > GitHub Apps > New GitHub App**
2. 填写基本信息：

| 字段 | 值 |
|------|---|
| App name | 例如 `My Code Reviewer` |
| Homepage URL | 你的服务器地址（如 `https://review.example.com`） |
| Webhook URL | `https://your-server.example.com/webhooks/github` |
| Webhook secret | 用 `openssl rand -hex 32` 生成一个强随机字符串 |

## 3.2 设置权限

| 权限 | 访问级别 | 用途 |
|------|---------|------|
| Checks | **读写** | 创建 Check Run（审查结果状态） |
| Contents | **只读** | 读取仓库代码内容 |
| Pull requests | **读写** | 创建 PR Review 和行内评论 |
| Secret scanning alerts | **只读** | 读取密钥扫描告警 |

## 3.3 订阅事件

在「Subscribe to events」下勾选 **Pull request**。

## 3.4 生成凭据

1. 点击 **Create GitHub App**
2. 在 App 设置页面记录 **App ID**
3. 滚动到「Private keys」，点击 **Generate a private key**，保存下载的 `.pem` 文件
4. 进入 **Install App** 侧边栏，将 App 安装到目标仓库
5. 安装后从 URL 获取 **Installation ID**
   - 例如：`https://github.com/settings/installations/123456` → Installation ID 为 `123456`

## 3.5 配置环境变量

将获取的凭据填入 `.env` 文件：

```bash
AGENT_REVIEW_GITHUB_APP_ID=123456
AGENT_REVIEW_GITHUB_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----
...（.pem 文件的完整内容）...
-----END RSA PRIVATE KEY-----"
AGENT_REVIEW_GITHUB_WEBHOOK_SECRET=你生成的webhook-secret
```

---

# 第四章：环境变量参考

所有配置都通过 `AGENT_REVIEW_` 前缀环境变量设置。
配置加载优先级为：`.env` 文件 → 系统环境变量。

## 4.1 数据库

| 变量 | 默认值 | 说明 | 必填 |
|------|-------|------|:----:|
| `AGENT_REVIEW_DATABASE_URL` | `sqlite+aiosqlite:///./dev.db` | 数据库连接字符串。生产环境使用 `postgresql+asyncpg://user:pass@host:5432/dbname` | 是 |

## 4.2 GitHub App

| 变量 | 默认值 | 说明 | 必填 |
|------|-------|------|:----:|
| `AGENT_REVIEW_GITHUB_APP_ID` | `0` | GitHub App ID | PR/基线扫描需要 |
| `AGENT_REVIEW_GITHUB_PRIVATE_KEY` | `""` | `.pem` 私钥文件的完整内容 | PR/基线扫描需要 |
| `AGENT_REVIEW_GITHUB_WEBHOOK_SECRET` | `""` | Webhook Secret，必须与 GitHub App 中配置的一致 | PR审查需要 |
| `AGENT_REVIEW_SECRET_KEY` | `change-me-in-production` | 应用密钥，用于 JWT 签名和会话加密。**生产环境必须修改** | 是 |
| `AGENT_REVIEW_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT 访问令牌过期时间（分钟） | 否 |

## 4.3 GitHub OAuth（可选）

| 变量 | 默认值 | 说明 | 必填 |
|------|-------|------|:----:|
| `AGENT_REVIEW_GITHUB_OAUTH_CLIENT_ID` | `""` | GitHub OAuth Client ID | OAuth 需要 |
| `AGENT_REVIEW_GITHUB_OAUTH_CLIENT_SECRET` | `""` | GitHub OAuth Client Secret | OAuth 需要 |
| `AGENT_REVIEW_OAUTH_REDIRECT_URI` | `""` | OAuth 回调 URL，如 `https://your-server/api/auth/github/callback` | OAuth 需要 |

## 4.4 LLM 配置

| 变量 | 默认值 | 说明 | 必填 |
|------|-------|------|:----:|
| `AGENT_REVIEW_LLM_CLASSIFY_MODEL` | `gpt-4o-mini` | 用于文件分类的轻量模型 | 是 |
| `AGENT_REVIEW_LLM_SYNTHESIZE_MODEL` | `gpt-4o` | 用于发现综合分析的强力模型 | 是 |
| `AGENT_REVIEW_LLM_FALLBACK_MODEL` | `gpt-4o-mini` | 主模型失败时的备选模型 | 否 |
| `AGENT_REVIEW_LLM_MAX_TOKENS` | `4096` | 每次 LLM 调用的最大 token 数 | 否 |
| `AGENT_REVIEW_LLM_TEMPERATURE` | `1.0` | LLM temperature 参数 | 否 |
| `AGENT_REVIEW_LLM_COST_BUDGET_PER_RUN_CENTS` | `50` | 每次审查运行的费用上限（美分） | 否 |

### LLM 服务商 API Key

根据使用的服务商设置对应的 API Key 环境变量：

| 服务商 | API Key 变量 | 模型前缀 | 模型示例 |
|--------|-------------|---------|---------|
| OpenAI | `OPENAI_API_KEY` | （无） | `gpt-4o-mini`、`gpt-4o` |
| Google Gemini | `GEMINI_API_KEY` | `gemini/` | `gemini/gemini-2.0-flash`、`gemini/gemini-2.5-pro` |
| GitHub Models | `GITHUB_API_KEY` | `github/` | `github/gpt-4o-mini`、`github/gpt-4o` |
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic/` | `anthropic/claude-sonnet-4-20250514` |

> Azure、Vertex AI、Bedrock 等其他服务商请参考 [litellm 文档](https://docs.litellm.ai/docs/providers)。

## 4.5 收集器

| 变量 | 默认值 | 说明 | 必填 |
|------|-------|------|:----:|
| `AGENT_REVIEW_SONAR_HOST_URL` | `""` | SonarQube 服务器地址 | SonarQube 需要 |
| `AGENT_REVIEW_SONAR_TOKEN` | `""` | SonarQube API Token | SonarQube 需要 |
| `AGENT_REVIEW_SEMGREP_APP_TOKEN` | `""` | Semgrep App Token（`app` 模式使用） | app 模式需要 |
| `AGENT_REVIEW_SEMGREP_MODE` | `cli` | Semgrep 运行模式：`app`（API）、`cli`（本地）、`disabled`（禁用） | 否 |
| `AGENT_REVIEW_SEMGREP_RULES_PATH` | `/opt/semgrep-rules` | Semgrep 规则路径（`cli` 模式使用）。Docker 镜像内自动包含社区规则 | 否 |
| `AGENT_REVIEW_SEMGREP_SEVERITY_FILTER` | `["ERROR","WARNING"]` | 包含的 Semgrep 严重性级别过滤器 | 否 |

## 4.6 限制

| 变量 | 默认值 | 说明 | 必填 |
|------|-------|------|:----:|
| `AGENT_REVIEW_MAX_INLINE_COMMENTS` | `25` | 每次审查的最大行内评论数 | 否 |
| `AGENT_REVIEW_MAX_DIFF_LINES` | `10000` | diff 超过此行数时跳过审查 | 否 |

## 4.7 路径

| 变量 | 默认值 | 说明 | 必填 |
|------|-------|------|:----:|
| `AGENT_REVIEW_POLICY_DIR` | `./policies` | 策略 YAML 文件目录 | 否 |
| `AGENT_REVIEW_PROMPTS_DIR` | `./prompts` | Jinja2 提示词模板目录 | 否 |
| `AGENT_REVIEW_FRONTEND_DIR` | `./static` | 前端 SPA 静态文件目录 | 否 |
| `AGENT_REVIEW_UPLOAD_DIR` | `/tmp/agent_review_uploads` | 文件上传临时目录 | 否 |
| `AGENT_REVIEW_UPLOAD_MAX_BYTES` | `209715200` | 上传文件大小限制（200 MB） | 否 |

## 4.8 CORS

| 变量 | 默认值 | 说明 | 必填 |
|------|-------|------|:----:|
| `AGENT_REVIEW_CORS_ORIGINS` | `[]` | 允许的跨域来源列表（逗号分隔）。为空则禁用 CORS | 否 |

## 4.9 可观测性

| 变量 | 默认值 | 说明 | 必填 |
|------|-------|------|:----:|
| `AGENT_REVIEW_LOG_LEVEL` | `INFO` | 日志级别（DEBUG、INFO、WARNING、ERROR） | 否 |
| `AGENT_REVIEW_LOG_FORMAT` | `console` | 日志格式：`json`（生产环境推荐）、`console`（开发环境） | 否 |

---

# 第五章：使用指南

Agent Review 提供三种使用模式：自动 PR 审查、基线扫描、本地扫描。

## 5.1 自动 PR 审查

### 工作原理

安装 GitHub App 且服务运行后，PR 会自动进入审查。
代理在以下事件触发：

| 事件 | 触发时机 |
|------|---------|
| `opened` | 创建新 PR |
| `synchronize` | 向已有 PR 推送新提交 |
| `ready_for_review` | PR 从草稿转为就绪状态 |

以下情况会被自动忽略：
- Bot 创建的 PR
- 草稿状态的 PR（除非是 `ready_for_review` 事件）
- 重复的 Webhook 投递（按 `X-GitHub-Delivery` 去重）
- 相同 (repo, pr_number, head_sha) 的重复运行

### 审查输出

代理会产生两种 GitHub 反馈：

1. **Check Run**：在 PR 的 Checks 标签页显示通过/失败状态
2. **PR Review**：包含结构化摘要和行内评论（最多 `MAX_INLINE_COMMENTS` 条）

### 取代机制

当新提交推送到正在审查的 PR 时，代理会**自动取代**该 PR 的所有活跃审查，并基于新的 HEAD 重新开始。
因此，过时审查不会阻塞合并，也不会继续消耗资源。

## 5.2 基线扫描（通过 GitHub API）

基线扫描用于对整个仓库进行全量扫描。
它的目的，是在不等待 PR 的情况下建立代码质量基线。

### 通过 API 触发

```bash
curl -X POST https://your-server.example.com/api/scan \
  -H 'Content-Type: application/json' \
  -d '{"repo": "owner/repo", "installation_id": 123456}'
```

响应：

```json
{"status": "queued", "run_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"}
```

查询扫描状态：

```bash
curl https://your-server.example.com/api/scan/<run_id>
```

### 通过 CLI 触发（本地 Python）

```bash
python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output markdown
```

### 通过 CLI 触发（Docker）

```bash
# JSON 报告（机器可读）
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output json

# Markdown 报告（人工可读）
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output markdown

# 发布为 GitHub Issue
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output github-issue

# 扫描指定分支
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --branch develop \
  --output markdown

# 保存报告到文件
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output markdown > report.md
```

### CLI 参数

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `--repo` | 是 | 仓库，格式为 `owner/name` |
| `--installation-id` | 是 | GitHub App Installation ID |
| `--branch` | 否 | 扫描分支（默认为仓库默认分支） |
| `--ref` | 否 | 精确的 commit SHA（优先于 `--branch`） |
| `--output` | 否 | 输出格式：`json`（默认）、`markdown`、`github-issue` |
| `--config` | 否 | `.env` 文件路径，用于覆盖默认配置 |

## 5.3 本地扫描（无需 GitHub）

本地扫描可以直接扫描任意本地目录，不需要 GitHub 凭据。

```bash
python -m agent_review scan-local \
  --path /code/myrepo \
  --output json
```

### 本地扫描特点

- 直接在本地目录运行 Semgrep（需要安装 `semgrep` CLI 或使用 Docker）
- **跳过** GitHub 依赖的收集器（密钥扫描、GitHub CI）
- 结果存储在本地数据库
- 仅需 LLM API Key 用于推理阶段

### CLI 参数

| 参数 | 必填 | 说明 |
|------|:----:|------|
| `--path` | 是 | 本地目录路径 |
| `--repo-name` | 否 | 报告中的仓库名称（默认为目录名） |
| `--output` | 否 | 输出格式：`json`（默认）、`markdown` |
| `--config` | 否 | `.env` 文件路径，用于覆盖默认配置 |

## 5.4 输出格式

| 格式 | 说明 | 适用场景 |
|------|------|---------|
| `json` | 机器可读的 JSON，包含决策、发现列表、性能指标 | CI 流水线、自动化处理 |
| `markdown` | 详细报告，含执行摘要、逐项证据、影响分析、修复建议、收集器状态、性能指标 | 人工审查、团队分享 |
| `github-issue` | 以 GitHub Issue 形式发布到仓库，自动添加 `code-review` 和 `baseline-scan` 标签 | 基线扫描跟踪（仅基线扫描） |

---

# 第六章：策略配置

策略是 Agent Review 的核心控制机制。
系统通过 YAML 文件定义审查行为。

## 6.1 策略文件位置

| 文件 | 说明 |
|------|------|
| `policies/default.policy.yaml` | 默认策略，适用于所有仓库 |
| `policies/{owner}/{repo}.yaml` | 按仓库覆盖策略 |

代理优先查找仓库特定策略。
如果未命中，则使用默认策略。

## 6.2 完整策略结构

```yaml
version: 1

# 收集器配置
collectors:
  semgrep:
    failure_mode: degraded    # required | degraded | optional
    timeout_seconds: 600
    retries: 0
  secrets:
    failure_mode: degraded
    timeout_seconds: 60
    retries: 0
  sonar:
    failure_mode: optional
    timeout_seconds: 180
    retries: 1
  github_ci:
    failure_mode: degraded
    timeout_seconds: 120
    retries: 0

# 审查 Profile
profiles:
  core_quality:               # 始终激活
    require_checks: []
    blocking_categories:
      - "security.*"          # fnmatch 通配符模式
      - "quality.bug"
    escalate_categories:
      - "quality.code-smell"
    max_inline_comments: 25

  security_sensitive:         # 安全相关文件变更时激活
    require_checks:
      - semgrep
      - secrets
    blocking_categories:
      - "security.*"
      - "quality.bug"
      - "quality.vulnerability"
    escalate_categories: []
    max_inline_comments: 50

  workflow_security:          # CI/工作流文件变更时激活
    require_checks: []
    blocking_categories:
      - "security.*"
    escalate_categories:
      - "quality.*"
    max_inline_comments: 15

# 全局限制
limits:
  max_inline_comments: 25
  max_summary_findings: 10
  max_diff_lines: 10000

# 紧急例外
exceptions:
  emergency_bypass_labels:
    - "emergency-bypass"
    - "hotfix"
```

## 6.3 collectors 段：收集器配置

每个收集器可以配置三个属性：

| 属性 | 说明 |
|------|------|
| `failure_mode` | 收集器失败时的行为 |
| `timeout_seconds` | 超时时间（秒） |
| `retries` | 失败重试次数 |

### 失败模式

| 模式 | 行为 |
|------|------|
| `required` | 收集器失败时**中断流水线**，审查失败 |
| `degraded` | 收集器失败时**继续审查**，在报告中注明缺失的收集器 |
| `optional` | 收集器失败时**静默忽略**，不影响审查 |

## 6.4 profiles 段：审查 Profile

Profile 定义了不同场景下的审查规则。
分类器会根据变更文件自动选择需要激活的 Profile：

| Profile | 激活条件 |
|---------|---------|
| `core_quality` | **始终激活** |
| `security_sensitive` | 变更涉及安全相关文件（auth/、permission、policy、roles 等） |
| `workflow_security` | 变更涉及 CI/工作流文件（.github/workflows、.gitlab-ci.yml 等） |

每个 Profile 可配置：

| 属性 | 说明 |
|------|------|
| `require_checks` | 该 Profile 要求必须成功的收集器列表 |
| `blocking_categories` | 匹配这些模式的发现为**阻断项** |
| `escalate_categories` | 匹配这些模式的发现需要**上报** |
| `max_inline_comments` | 该 Profile 的最大行内评论数 |

### fnmatch 通配符模式

`blocking_categories` 和 `escalate_categories` 使用 Python `fnmatch` 模式匹配：

| 模式 | 匹配 | 不匹配 |
|------|------|--------|
| `security.*` | `security.xss`、`security.sqli`、`security.sast` | `quality.bug` |
| `quality.bug` | `quality.bug` | `quality.code-smell` |
| `quality.*` | `quality.bug`、`quality.vulnerability`、`quality.code-smell` | `security.xss` |

## 6.5 阻断 vs. 建议分类

一个发现被归类为**阻断项**，只需满足以下**任一**条件：

1. **基于严重性**：发现的严重性为 `HIGH` 或 `CRITICAL`
2. **基于策略**：发现的类别匹配任何活跃 Profile 中 `blocking_categories` 的通配符模式

不满足上述条件的发现均为**建议项**。

## 6.6 决策结果

| 决策 | GitHub 操作 | 含义 |
|------|-----------|------|
| `PASS` | Approve（批准） | 未发现问题 |
| `WARN` | Comment（评论） | 仅有建议项，无阻断项 |
| `REQUEST_CHANGES` | Request Changes（请求修改） | 存在需要处理的阻断项 |
| `BLOCK` | Request Changes（请求修改） | 存在 CRITICAL 严重性的阻断项 |
| `ESCALATE` | Comment + @mentions（评论 + 提及） | 发现需要团队负责人关注的问题 |

## 6.7 紧急绕过

为 PR 添加以下标签可以跳过策略评估：

- `emergency-bypass`
- `hotfix`

代理仍会运行所有收集器，并以**建议**形式发布发现（WARN 决策）。
另一方面，它**不会阻止合并**。
该机制适用于紧急生产修复。

## 6.8 按仓库覆盖策略

创建 `policies/{owner}/{repo}.yaml` 文件以覆盖特定仓库的策略。

例如，为 `kylecui/my-app` 仓库创建覆盖策略：

```bash
mkdir -p policies/kylecui
# 创建 policies/kylecui/my-app.yaml
```

策略优先级：仓库特定策略 > 默认策略。

---

# 第七章：管理后台

Agent Review 内置管理仪表盘。
它覆盖用户管理、设置管理、策略编辑和扫描管理。

## 7.1 首次设置

1. 部署完成后，在浏览器中访问实例地址（如 `https://your-server.example.com`）
2. 注册第一个账号 — **自动升级为管理员**（超级用户）
3. 使用注册的邮箱和密码登录

## 7.2 身份认证

### 邮箱/密码登录

直接使用注册的邮箱和密码登录管理后台。

### GitHub OAuth 登录（可选）

启用「使用 GitHub 登录」功能：

1. 前往 GitHub App 设置 > 通用
2. 在「Identifying and authorizing users」下设置：
   - **Callback URL**：`https://your-server.example.com/api/auth/github/callback`
3. 复制 **Client ID** 并生成 **Client Secret**
4. 在 `.env` 中设置：

```bash
AGENT_REVIEW_GITHUB_OAUTH_CLIENT_ID=your_client_id
AGENT_REVIEW_GITHUB_OAUTH_CLIENT_SECRET=your_client_secret
AGENT_REVIEW_OAUTH_REDIRECT_URI=https://your-server.example.com/api/auth/github/callback
```

5. 重启应用

### JWT 令牌

认证使用 JWT（JSON Web Token）。
令牌过期时间由 `AGENT_REVIEW_ACCESS_TOKEN_EXPIRE_MINUTES` 控制（默认 60 分钟）。

## 7.3 用户管理

> 仅管理员可访问

### 访问控制矩阵

| 操作 | Admin（管理员） | Viewer（查看者） |
|------|:-:|:-:|
| 查看扫描 | ✅ | ✅ |
| 触发扫描 | ✅ | ❌ |
| 取消/删除扫描 | ✅ | ❌ |
| 查看设置 | ✅ | ❌ |
| 编辑设置 | ✅ | ❌ |
| 重置设置 | ✅ | ❌ |
| 查看策略 | ✅ | ❌ |
| 编辑/创建/删除策略 | ✅ | ❌ |
| 查看用户 | ✅ | ❌ |
| 创建/编辑/停用用户 | ✅ | ❌ |

### 操作说明

1. 点击侧栏 **Users**（用户）
2. 查看所有用户的角色、状态和 GitHub 关联
3. **创建用户**：点击 Create User，填入邮箱/密码，选择角色（Admin 或 Viewer）
4. **切换状态**：启用/停用用户的活跃状态
5. **修改角色**：切换用户的超级用户角色

### 自我保护机制

管理员不能：
- 移除自己的管理员角色
- 停用自己的账号

## 7.4 扫描管理

> 管理员可完全操作，查看者仅能查看

1. 点击侧栏 **Scans**（扫描）
2. 查看所有扫描记录，支持按仓库、状态和扫描类型筛选
3. 点击任意扫描查看详细发现，按阻断/建议分类分组
4. **触发新扫描**：点击 Trigger Scan，输入仓库名称和 Installation ID
5. **取消运行中的扫描**：在扫描列表中操作
6. **删除已完成的扫描**：在扫描列表中操作

## 7.5 设置管理

> 仅管理员可访问

1. 点击侧栏 **Settings**（设置）
2. 设置分为以下分组：
   - **LLM 配置**：分类模型、综合分析模型、备选模型、max tokens、temperature、费用预算
   - **收集器**：Semgrep 模式、SonarQube 配置
   - **限制**：行内评论数、diff 行数上限
   - **可观测性**：日志级别、日志格式
3. 编辑任意值并点击 **Save** 以持久化到数据库
4. 点击 **Reset** 可将设置恢复为环境变量默认值
5. ⚠️ 更改仅对**新扫描**生效；进行中的扫描使用其原始设置

## 7.6 策略编辑器

> 仅管理员可访问

1. 点击侧栏 **Policies**（策略）
2. 查看所有存储的策略；点击策略名打开 **Monaco YAML 编辑器**
3. **编辑策略**：在编辑器中修改 YAML，点击 Save
   - 编辑器自动验证 YAML 语法
   - 保存时校验 PolicyConfig Schema
4. **创建仓库覆盖策略**：点击 Create Policy，输入仓库名（如 `owner/repo`）
5. **从磁盘导入**：使用 Seed from Disk 将 `policies/` 目录中的策略导入数据库

### ETag 冲突检测

策略编辑器使用 ETag 机制，避免并发编辑相互覆盖。
如果另一个管理员在你编辑期间修改了同一策略，保存时会收到冲突提示。

---

# 第八章：Web 仪表盘

## 8.1 访问地址

| 地址 | 说明 |
|------|------|
| `/ui/scans` | 所有扫描记录列表（按时间倒序） |
| `/ui/scans/{run_id}` | 单次扫描详情 |

## 8.2 扫描列表页

展示所有扫描记录，包含：
- 仓库名称
- 扫描类型（PR / Baseline）
- 运行状态
- Head SHA
- 创建时间

## 8.3 扫描详情页

详情页展示以下信息：

### 运行概览
- 仓库名称
- 扫描类型（PR / Baseline）
- 运行状态（Pending → Classifying → Collecting → Normalizing → Reasoning → Deciding → Publishing → Completed）
- Commit SHA
- 创建/更新/完成时间戳

### 决策结果
- **决策**：PASS / WARN / REQUEST_CHANGES / BLOCK / ESCALATE
- **置信度**
- **摘要**
- **阻断发现数量 / 建议发现数量**
- **上报原因**（如有）

### 阻断发现分组
- **按严重性**：HIGH 或 CRITICAL 严重性的发现
- **按策略**：匹配阻断类别模式的发现（可折叠展示）

### 建议发现
- 不满足任何阻断条件的发现

### 分类信息
- 变更类型
- 涉及领域
- 风险级别
- 激活的 Profile

### 发现详情
每个发现包含：
- 严重性标签（CRITICAL / HIGH / MEDIUM / LOW / INFO）
- 文件位置（文件名:行号）
- 证据
- 影响说明
- 修复建议
- 分类原因（为什么被标记为阻断/建议）

### 性能指标
- 各阶段耗时（分类、收集、归一化、推理、决策、发布）
- LLM 成本
- 收集器详情

---

# 第九章：流水线架构详解

## 9.1 阶段一：Webhook 接收

### 触发条件

只处理 `pull_request` 类型的 Webhook 事件，支持以下 action：
- `opened` — 新 PR 创建
- `synchronize` — 已有 PR 推送新提交
- `ready_for_review` — PR 从草稿转为就绪

### 安全验证

使用 `X-Hub-Signature-256` header 中的 HMAC-SHA256 签名验证 Webhook 真实性。

### 自动过滤

| 过滤条件 | 处理 |
|---------|------|
| 非 pull_request 事件 | 忽略 |
| 不支持的 action | 忽略 |
| Bot 发送者 | 忽略 |
| 草稿 PR（非 ready_for_review） | 忽略 |
| 重复 delivery（按 `X-GitHub-Delivery`） | 忽略 |
| 重复运行（按 repo + PR + head_sha） | 忽略 |

### 取代机制

接收到新 Webhook 后，先取代该 PR 上所有活跃的旧运行（标记为 `SUPERSEDED`），再创建新运行。

## 9.2 阶段二：文件分类

系统使用确定性的文件模式启发式分类器。
分类依据是变更文件的路径和名称。

### 分类输出

| 输出 | 说明 |
|------|------|
| **类别** | security, workflow, migration, api, docs, test, general |
| **风险级别** | critical, high, medium, low |
| **策略 Profile** | `core_quality`（始终）+ `security_sensitive` 和/或 `workflow_security`（按需） |

### 分类规则示例

| 文件模式 | 分类 | Profile |
|---------|------|---------|
| `auth/`、`permission`、`policy`、`roles` | security | core_quality + security_sensitive |
| `.github/workflows`、`.gitlab-ci.yml` | workflow | core_quality + workflow_security |
| `migrations/`、`schema` | migration | core_quality |
| `*.md`、`docs/` | docs | core_quality |
| `tests/`、`*_test.*` | test | core_quality |
| 其他 | general | core_quality |

## 9.3 阶段三：证据收集

四个收集器会**并行运行**：

| 收集器 | 说明 | 模式 |
|--------|------|------|
| **Semgrep** | SAST 静态分析扫描 | `app`（API）/ `cli`（本地）/ `disabled` |
| **SonarQube** | 代码质量分析 | 可选（配置了 URL 和 Token 才启用） |
| **GitHub CI** | 从已有 CI 流水线提取 Check Run 注解 | 降级模式（失败不影响审查） |
| **Secrets** | 读取 GitHub 密钥扫描告警 | 降级模式 |

### 收集器接口

所有收集器都继承自 `AbstractCollector`。
每个收集器都必须实现 `collect(context) -> CollectorResult` 方法：

```python
class AbstractCollector(ABC):
    name: ClassVar[str]
    
    @abstractmethod
    async def collect(self, context: CollectorContext) -> CollectorResult:
        ...
```

`CollectorContext` 包含仓库名、head SHA、变更文件列表、GitHub 客户端等上下文信息。

`CollectorResult` 包含收集器名称、状态（success/failure/timeout/skipped）、原始发现列表、耗时和错误信息。

## 9.4 阶段四：归一化和去重

### 归一化

将各收集器的原始发现转换为统一的 Finding Schema：

| 字段 | 说明 |
|------|------|
| `finding_id` | 发现唯一标识 |
| `category` | 类别（如 `security.sast`、`quality.bug`） |
| `severity` | 严重性：CRITICAL / HIGH / MEDIUM / LOW / INFO |
| `confidence` | 置信度：HIGH / MEDIUM / LOW |
| `blocking` | 是否为阻断项 |
| `file_path` | 文件路径 |
| `line_start` / `line_end` | 行号范围 |
| `source_tools` | 来源工具列表 |
| `rule_id` | 规则 ID |
| `title` | 标题 |
| `evidence` | 证据列表 |
| `impact` | 影响说明 |
| `fix_recommendation` | 修复建议 |
| `test_recommendation` | 测试建议 |
| `fingerprint` | 指纹（用于去重） |
| `disposition` | 状态：new / existing / fixed |

### 去重

系统按 `fingerprint` 去重。
如果出现重复，保留严重性更高的记录。

## 9.5 阶段五：LLM 推理

LLM 对归一化后的发现进行综合分析，输出包括：

1. **优先级排序**：按实际影响排序（不仅看严重性标签）
2. **关联分组**：将相关发现分组
3. **误报识别**：标记证据不足的发现
4. **可读解释**：为每个发现生成人类可读的解释和修复建议

### 三级处理策略

根据发现数量采用不同策略：

| 数量 | 策略 | 说明 |
|------|------|------|
| 少量 | 单次调用 | 所有发现在一次 LLM 调用中处理 |
| 中等 | 分块处理 | 将发现分组后多次调用 |
| 大量 | 采样处理 | 抽样代表性发现后汇总 |

### 降级处理

当出现以下情况时，系统会自动降级为**确定性综合分析**（不使用 LLM）：

- LLM 调用失败
- 超出每次运行的费用预算（`COST_BUDGET_PER_RUN_CENTS`）
- LLM 返回格式异常

确定性综合分析会按类别和严重性分组排序发现。
这种模式不提供 LLM 解释。

### 提示词模板

提示词模板存放在 `prompts/` 目录，使用 Jinja2 语法：

- `synthesize.j2` — 综合分析提示词（发现优先级排序、分组、解释）
- `summarize.j2` — 摘要提示词（生成 PR 评论摘要）

## 9.6 阶段六：策略决策

策略控制器会根据活跃 Profile 评估所有发现，并生成最终决策：

1. 加载策略文件（仓库特定 > 默认）
2. 对每个发现判断是否匹配 `blocking_categories` 或严重性为 HIGH/CRITICAL
3. 检查紧急绕过标签
4. 综合所有 Profile 的评估结果，输出最终决策

## 9.7 阶段七：结果发布

仅 PR 模式下执行：

1. **创建 Check Run**：在 PR 的 Checks 标签页创建通过/失败状态
2. **创建 PR Review**：使用 `summarize.j2` 模板生成结构化摘要评论

## 9.8 运行状态流转

```
PENDING → CLASSIFYING → COLLECTING → NORMALIZING → REASONING → DECIDING → PUBLISHING → COMPLETED
    ↓          ↓            ↓            ↓            ↓           ↓           ↓
  FAILED     FAILED       FAILED       FAILED       FAILED      FAILED      FAILED
    ↓          ↓            ↓            ↓            ↓           ↓           ↓
SUPERSEDED SUPERSEDED  SUPERSEDED   SUPERSEDED   SUPERSEDED  SUPERSEDED  SUPERSEDED
```

终态（不可再转换）：`COMPLETED`、`FAILED`、`SUPERSEDED`

---

# 第十章：运维指南

## 10.1 日志管理

### Docker 环境

```bash
# 查看实时日志
docker compose logs -f app

# 查看最近 100 行日志
docker compose logs --tail 100 app

# 查看数据库日志
docker compose logs -f db
```

### 本地开发

日志默认输出到控制台。
你可以设置 `AGENT_REVIEW_LOG_FORMAT=console` 以获取可读格式。

### 日志格式

| 格式 | 说明 | 适用场景 |
|------|------|---------|
| `json` | 结构化 JSON 日志，每行一个 JSON 对象 | 生产环境，便于日志聚合 |
| `console` | 人类可读的格式化输出 | 开发环境 |

### 日志级别

支持标准级别：`DEBUG`、`INFO`、`WARNING`、`ERROR`。生产环境推荐 `INFO`。

## 10.2 数据库管理

### Alembic 迁移

```bash
# 运行所有待执行的迁移
make migrate
# 等同于：uv run alembic upgrade head

# 查看迁移历史
uv run alembic history

# 回退到上一个版本
uv run alembic downgrade -1
```

### 数据库选择

| 数据库 | 连接字符串 | 适用场景 |
|--------|-----------|---------|
| SQLite | `sqlite+aiosqlite:///./dev.db` | 开发、测试、单机本地扫描 |
| PostgreSQL | `postgresql+asyncpg://user:pass@host:5432/dbname` | 生产环境 |

### 数据库表

| 表名 | 说明 |
|------|------|
| `review_runs` | 审查运行记录（状态、决策、指标等） |
| `findings` | 发现记录（严重性、类别、证据、修复建议等） |
| `users` | 用户账号（邮箱、密码哈希、角色、GitHub 关联） |
| `app_configs` | 运行时设置（管理后台修改的配置） |
| `policy_stores` | 策略存储（管理后台编辑的策略） |

### 备份建议

- PostgreSQL：使用 `pg_dump` 定期备份
- 重要数据：`review_runs`、`findings`（审查历史）、`users`（账号）
- 策略文件建议同时保留在 Git 仓库中（`policies/` 目录）

## 10.3 监控建议

### 健康检查

建议在监控系统中定期检查以下端点：

| 端点 | 说明 | 检查间隔 |
|------|------|---------|
| `GET /health` | 存活检查（始终返回 ok） | 30 秒 |
| `GET /ready` | 就绪检查（验证数据库连接） | 60 秒 |

### 关键监控指标

- 审查运行状态分布（Completed vs Failed vs Superseded）
- 平均审查耗时
- LLM 成本趋势
- 收集器失败率
- Webhook 投递成功率（在 GitHub App 设置中查看）

## 10.4 常见故障排查

### 收不到 Webhook

**现象**：PR 创建后代理没有响应。

**排查步骤**：
1. 检查 Webhook URL 是否可从公网访问
2. 在 GitHub App 设置中查看投递状态：Settings > Developer Settings > 你的 App > Advanced > Recent Deliveries
3. 查看失败投递的 HTTP 状态码和响应内容
4. 确认服务正在运行：`curl http://localhost:8000/health`

### Webhook 返回 401 Unauthorized

**原因**：`.env` 中的 `AGENT_REVIEW_GITHUB_WEBHOOK_SECRET` 与 GitHub App 配置不一致。

**解决**：重新生成 secret 并同步更新两端配置。

### 流水线卡在 COLLECTING 状态

**原因**：某个收集器超时。

**排查步骤**：
1. 检查 `AGENT_REVIEW_SEMGREP_MODE`（没有 Semgrep Token 时设为 `disabled`）
2. 确认网络能访问 Semgrep 和 SonarQube 的外部 API
3. 检查收集器超时配置（策略文件中的 `timeout_seconds`）

### LLM 错误或综合分析为空

**排查步骤**：
1. 确认 API Key 环境变量已正确设置
2. 如预算过低，增大 `AGENT_REVIEW_LLM_COST_BUDGET_PER_RUN_CENTS`
3. 检查日志中的 litellm 错误信息
4. 验证模型名称是否正确（注意前缀：gemini/、github/、anthropic/）

### PR 上没有发布审查

**排查步骤**：
1. 确认 GitHub App 有 **Checks**（读写）和 **Pull requests**（读写）权限
2. 确认 App 已安装到目标仓库
3. 检查 PR 不是草稿且不是 Bot 创建的
4. 查看日志中是否有 PUBLISHING 阶段的错误

### 找不到模板目录

**现象**：日志显示 `Template directory not found: .../prompts`

**解决**：
- 设置 `AGENT_REVIEW_PROMPTS_DIR` 为 `prompts/` 目录的绝对路径
- Docker 中默认 `./prompts` 相对于 `WORKDIR /app`，通常无需修改
- 如修改了 `WORKDIR`，需要同步更新此设置

### 数据库连接失败

**现象**：`/ready` 端点返回错误。

**排查步骤**：
1. 确认 `AGENT_REVIEW_DATABASE_URL` 格式正确
2. Docker 环境下确认 `db` 服务已启动并通过健康检查
3. 检查数据库用户名/密码是否正确
4. 运行 `make migrate` 确认迁移已执行

## 10.5 性能调优建议

| 方面 | 建议 |
|------|------|
| **LLM 成本** | 使用轻量模型（gpt-4o-mini）进行分类，仅综合分析使用强力模型 |
| **审查速度** | 调低 `MAX_DIFF_LINES` 跳过超大 PR |
| **评论噪声** | 调低 `MAX_INLINE_COMMENTS` 减少评论数量 |
| **收集器超时** | 在策略文件中调整 `timeout_seconds` |
| **内存** | 大型仓库扫描可能需要更多内存，建议 1 GB+ |

---

# 第十一章：二次开发指南

## 11.1 开发环境搭建

### 后端

```bash
# 安装 uv（Python 包管理器）
pip install uv

# 安装所有依赖（包括开发依赖）
uv sync --dev

# 复制配置
cp .env.example .env

# 运行数据库迁移
make migrate

# 启动开发服务器（端口 8000，热重载）
make serve
```

### 前端

```bash
cd frontend

# 安装依赖（需要 Node.js 22+）
npm ci

# 启动 Vite 开发服务器
npm run dev

# 从 OpenAPI spec 生成 API 客户端
npm run generate-api
```

### Make 命令

| 命令 | 说明 |
|------|------|
| `make lint` | Ruff 检查（自动修复）+ 格式化 |
| `make typecheck` | Mypy 严格模式类型检查 |
| `make test` | Pytest 含覆盖率报告 |
| `make check` | 以上全部（lint + typecheck + test） |
| `make serve` | 启动开发服务器（端口 8000，热重载） |
| `make migrate` | 运行 Alembic 数据库迁移 |

## 11.2 项目结构

### 后端模块

```
src/agent_review/
├── app.py              # FastAPI 应用工厂，路由注册，中间件配置
├── config.py           # pydantic-settings 配置管理（所有环境变量）
├── crypto.py           # 加密工具
├── database.py         # 异步 SQLAlchemy 引擎和会话工厂
├── models/             # ORM 模型
│   ├── _base.py        # SQLAlchemy 声明式基类
│   ├── enums.py        # 枚举类型（ReviewState, Verdict, FindingSeverity 等）
│   ├── review_run.py   # ReviewRun 模型（审查运行记录）
│   ├── finding.py      # Finding 模型（发现记录）
│   ├── user.py         # User 模型（用户账号）
│   ├── app_config.py   # AppConfig 模型（运行时设置）
│   └── policy_store.py # PolicyStore 模型（策略存储）
├── schemas/            # Pydantic 数据 Schema
├── api/                # FastAPI 路由
│   ├── health.py       # 健康检查（/health, /ready）
│   ├── scan.py         # 扫描 API（/api/scan）
│   ├── webhooks.py     # Webhook 处理（/webhooks/github）
│   ├── auth.py         # 认证 API（/api/auth/*）
│   ├── dependencies.py # FastAPI 依赖注入
│   └── admin/          # 管理 API
│       ├── users.py    # 用户管理
│       ├── settings.py # 设置管理
│       ├── policies.py # 策略管理
│       └── scans.py    # 扫描管理
├── auth/               # 认证模块
│   ├── dependencies.py # 认证依赖（获取当前用户、验证管理员）
│   ├── oauth.py        # GitHub OAuth
│   ├── password.py     # 密码哈希（Argon2/bcrypt）
│   └── token.py        # JWT 令牌
├── classifier/         # 文件分类器
│   └── classifier.py   # 文件模式启发式分类
├── collectors/         # 证据收集器
│   ├── base.py         # 抽象基类（AbstractCollector）
│   ├── registry.py     # 收集器注册表
│   ├── semgrep.py      # Semgrep SAST 收集器
│   ├── sonar.py        # SonarQube 收集器
│   ├── github_ci.py    # GitHub CI 注解收集器
│   └── secrets.py      # 密钥扫描收集器
├── normalize/          # 归一化
│   └── normalizer.py   # 发现归一化和指纹去重
├── reasoning/          # LLM 推理
│   ├── llm_client.py   # litellm 客户端封装
│   ├── synthesizer.py  # 发现综合分析
│   └── __init__.py     # PromptManager（Jinja2 模板管理）
├── gate/               # 策略决策
│   └── policy_loader.py # YAML 策略加载和决策控制器
├── pipeline/           # 流水线
│   ├── runner.py       # PR 审查流水线运行器
│   ├── baseline_runner.py  # 基线扫描运行器
│   ├── local_runner.py     # 本地扫描运行器
│   ├── analysis.py     # 分析核心逻辑（分类→收集→归一化→推理→决策）
│   └── supersession.py # 取代逻辑
├── reporting/          # 输出报告
│   ├── json_report.py  # JSON 格式
│   ├── markdown_report.py  # Markdown 格式
│   ├── github_issue.py # GitHub Issue 格式
│   └── db_report.py    # 数据库存储
├── scm/                # 源代码管理集成
│   ├── github_auth.py  # GitHub App JWT 认证 + Installation Token
│   ├── github_client.py    # GitHub REST API 客户端
│   └── github_projection.py # 决策到 GitHub 操作的映射
└── observability/      # 可观测性
    └── __init__.py     # structlog 配置、PipelineLogger、RunMetrics
```

### 其他目录

```
prompts/                # Jinja2 提示词模板
├── synthesize.j2       # 综合分析提示词
└── summarize.j2        # 摘要提示词

policies/               # YAML 策略文件
└── default.policy.yaml # 默认策略

alembic/                # 数据库迁移
├── env.py
└── versions/           # 迁移版本文件

frontend/               # React SPA 前端
├── src/                # 源代码
├── package.json        # 依赖和脚本
├── vite.config.ts      # Vite 构建配置
├── openapi.json        # OpenAPI 规范（用于生成 API 客户端）
└── openapi-ts.config.ts # API 客户端生成配置

scripts/                # 工具脚本
└── export_openapi.py   # 导出 OpenAPI 规范

tests/                  # 测试
├── conftest.py         # pytest 配置和 fixtures
├── factories.py        # 测试数据工厂
├── fixtures/           # 测试固件数据
├── unit/               # 单元测试
└── integration/        # 集成测试
```

### 前端技术栈

| 技术 | 用途 |
|------|------|
| React 19 | UI 框架 |
| Vite 6 | 构建工具 |
| TailwindCSS 4 | 样式框架 |
| shadcn/ui (class-variance-authority) | UI 组件库 |
| TanStack Router | 客户端路由 |
| TanStack Query | 服务端状态管理 |
| Monaco Editor (@monaco-editor/react) | YAML 策略编辑器 |
| @hey-api/client-fetch | 从 OpenAPI 生成的类型安全 API 客户端 |
| Lucide React | 图标库 |

## 11.3 核心扩展点

### 添加新收集器

1. 在 `src/agent_review/collectors/` 创建新文件（如 `my_collector.py`）
2. 继承 `AbstractCollector`，实现 `collect` 方法：

```python
from agent_review.collectors.base import (
    AbstractCollector,
    CollectorContext,
    CollectorResult,
)

class MyCollector(AbstractCollector):
    name = "my_collector"
    
    async def collect(self, context: CollectorContext) -> CollectorResult:
        # 1. 使用 context.repo, context.head_sha, context.changed_files 等
        # 2. 调用外部工具/API 收集证据
        # 3. 返回 CollectorResult
        return CollectorResult(
            collector_name=self.name,
            status="success",
            raw_findings=[...],
            duration_ms=100,
        )
```

3. 在 `registry.py` 中注册新收集器
4. 在策略 YAML 的 `collectors` 段添加配置

### 自定义策略 Profile

在策略 YAML 的 `profiles` 段添加新 Profile：

```yaml
profiles:
  my_custom_profile:
    require_checks:
      - semgrep
    blocking_categories:
      - "my_category.*"
    escalate_categories: []
    max_inline_comments: 30
```

同时需要在分类器中添加激活条件。

### 自定义 LLM 提示词模板

修改 `prompts/` 目录下的 Jinja2 模板：

- `synthesize.j2` — 控制 LLM 如何分析和排序发现
- `summarize.j2` — 控制 PR 评论摘要的格式和内容

模板使用 Jinja2 语法，可访问审查上下文变量（repo、pr_number、findings 等）。

### 添加新的输出格式

在 `src/agent_review/reporting/` 创建新的报告格式化器，参考现有实现：
- `json_report.py` — JSON 格式
- `markdown_report.py` — Markdown 格式
- `github_issue.py` — GitHub Issue 格式

### 自定义分类规则

修改 `src/agent_review/classifier/classifier.py` 中的文件模式匹配规则，添加新的文件模式和对应的类别/风险级别/Profile。

### 添加新 API 端点

1. 在 `src/agent_review/api/` 创建新路由文件
2. 在 `app.py` 的 `create_app()` 中注册路由：

```python
from agent_review.api.my_router import router as my_router
app.include_router(my_router, prefix="/api/my-feature")
```

## 11.4 数据库模型

### ReviewRun（审查运行）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `repo` | String | 仓库名（owner/name） |
| `run_kind` | Enum | 运行类型：PR / BASELINE |
| `pr_number` | Integer? | PR 号（仅 PR 模式） |
| `head_sha` | String(40) | Head commit SHA |
| `base_sha` | String(40)? | Base commit SHA |
| `installation_id` | Integer? | GitHub App Installation ID |
| `attempt` | Integer | 尝试次数（默认 1） |
| `state` | Enum | 运行状态（参见状态流转图） |
| `superseded_by` | UUID? | 被哪个运行取代（自引用外键） |
| `trigger_event` | Enum? | 触发事件：opened / synchronize / ready_for_review |
| `delivery_id` | String? | X-GitHub-Delivery（唯一约束，用于去重） |
| `classification` | JSON? | 分类结果 |
| `decision` | JSON? | 决策结果 |
| `metrics` | JSON? | 性能指标 |
| `error` | String? | 错误信息 |
| `run_logs` | JSON? | 运行日志 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |
| `completed_at` | DateTime? | 完成时间 |

### Finding（发现）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `review_run_id` | UUID | 关联的 ReviewRun（外键） |
| `finding_id` | String | 发现标识 |
| `category` | String | 类别（如 security.sast） |
| `severity` | Enum | CRITICAL / HIGH / MEDIUM / LOW / INFO |
| `confidence` | Enum | HIGH / MEDIUM / LOW |
| `blocking` | Boolean | 是否为阻断项 |
| `file_path` | String | 文件路径 |
| `line_start` | Integer | 起始行号 |
| `line_end` | Integer? | 结束行号 |
| `source_tools` | JSON | 来源工具列表 |
| `rule_id` | String? | 规则 ID |
| `title` | String | 标题 |
| `evidence` | JSON | 证据列表 |
| `impact` | String | 影响说明 |
| `fix_recommendation` | String | 修复建议 |
| `test_recommendation` | String? | 测试建议 |
| `fingerprint` | String | 指纹（用于去重） |
| `disposition` | Enum | new / existing / fixed |
| `created_at` | DateTime | 创建时间 |

### User（用户）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 主键 |
| `email` | String | 邮箱（唯一） |
| `hashed_password` | String | 密码哈希 |
| `full_name` | String? | 全名 |
| `is_active` | Boolean | 是否激活 |
| `is_superuser` | Boolean | 是否超级用户 |
| `github_id` | Integer? | GitHub 用户 ID |
| `github_login` | String? | GitHub 用户名 |
| `created_at` | DateTime | 创建时间 |
| `updated_at` | DateTime | 更新时间 |

### Alembic 迁移

```bash
# 创建新迁移
uv run alembic revision --autogenerate -m "描述"

# 运行迁移
uv run alembic upgrade head

# 回退
uv run alembic downgrade -1

# 查看历史
uv run alembic history
```

## 11.5 代码质量工具

### Ruff

代码检查和格式化工具，配置在 `pyproject.toml`：

```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH", "RUF"]
```

启用的规则集：
- `E`/`F`/`W`：pycodestyle 和 pyflakes
- `I`：import 排序
- `N`：命名规范
- `UP`：Python 升级建议
- `B`：bugbear（常见陷阱）
- `A`：内置名称遮蔽
- `SIM`：简化建议
- `TCH`：类型检查导入优化
- `RUF`：Ruff 自有规则

### Mypy

严格模式类型检查：

```toml
[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
```

### Pytest

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

运行测试：`make test`（含覆盖率报告）。

### pre-commit

项目配置了 `.pre-commit-config.yaml`，在提交前自动运行代码检查。

安装：

```bash
uv run pre-commit install
```

## 11.6 API 端点参考

### 公共端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/health` | 存活检查 |
| `GET` | `/ready` | 就绪检查（验证数据库） |
| `POST` | `/api/scan` | 触发基线扫描（返回 202 + run_id） |
| `GET` | `/api/scan/{run_id}` | 查询扫描状态 |
| `POST` | `/webhooks/github` | GitHub Webhook 接收端点 |

### 认证端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/register` | 注册新用户 |
| `POST` | `/api/auth/login` | 邮箱/密码登录 |
| `GET` | `/api/auth/me` | 获取当前用户信息 |
| `GET` | `/api/auth/github/authorize` | GitHub OAuth 授权跳转 |
| `GET` | `/api/auth/github/callback` | GitHub OAuth 回调 |

### 管理端点（需要管理员权限）

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/admin/users` | 获取用户列表 |
| `POST` | `/api/admin/users` | 创建用户 |
| `PATCH` | `/api/admin/users/{id}` | 更新用户 |
| `GET` | `/api/admin/settings` | 获取运行时设置 |
| `PUT` | `/api/admin/settings/{key}` | 更新设置 |
| `DELETE` | `/api/admin/settings/{key}` | 重置设置 |
| `GET` | `/api/admin/policies` | 获取策略列表 |
| `POST` | `/api/admin/policies` | 创建策略 |
| `GET` | `/api/admin/policies/{name}` | 获取策略详情 |
| `PUT` | `/api/admin/policies/{name}` | 更新策略 |
| `DELETE` | `/api/admin/policies/{name}` | 删除策略 |
| `GET` | `/api/admin/scans` | 获取扫描列表 |
| `POST` | `/api/admin/scans` | 触发扫描 |
| `DELETE` | `/api/admin/scans/{id}` | 删除扫描 |

### CI/CD 工作流

项目包含 GitHub Actions CI 工作流（`.github/workflows/ci.yml`），在 push 到 main 和 PR 时自动运行：

**后端检查**：
1. Ruff lint 检查
2. Ruff 格式检查
3. Mypy 类型检查
4. Pytest 测试（含覆盖率）

**前端检查**：
1. ESLint 检查
2. TypeScript 类型检查
3. Vite 构建

---

# 第十二章：LLM 服务商配置

## 12.1 litellm 抽象层

Agent Review 使用 [litellm](https://docs.litellm.ai/) 作为 LLM 抽象层。
litellm 提供统一 API 接口，支持 100+ LLM 服务商。
因此，切换服务商时通常只需要修改模型名称和 API Key。

## 12.2 配置方法

### 步骤

1. 设置服务商的 API Key 环境变量
2. 设置模型名称（注意前缀规则）

### OpenAI

```bash
# .env
export OPENAI_API_KEY=sk-...

# 模型名称（无前缀）
AGENT_REVIEW_LLM_CLASSIFY_MODEL=gpt-4o-mini
AGENT_REVIEW_LLM_SYNTHESIZE_MODEL=gpt-4o
```

### Google Gemini (AI Studio)

```bash
# .env
export GEMINI_API_KEY=your-gemini-api-key

# 模型名称（gemini/ 前缀）
AGENT_REVIEW_LLM_CLASSIFY_MODEL=gemini/gemini-2.0-flash
AGENT_REVIEW_LLM_SYNTHESIZE_MODEL=gemini/gemini-2.5-pro
```

### GitHub Models

从 [github.com/marketplace/models](https://github.com/marketplace/models) 获取 Personal Access Token。

```bash
# .env
export GITHUB_API_KEY=ghp_...

# 模型名称（github/ 前缀）
AGENT_REVIEW_LLM_CLASSIFY_MODEL=github/gpt-4o-mini
AGENT_REVIEW_LLM_SYNTHESIZE_MODEL=github/gpt-4o
```

### Anthropic

```bash
# .env
export ANTHROPIC_API_KEY=sk-ant-...

# 模型名称（anthropic/ 前缀）
AGENT_REVIEW_LLM_CLASSIFY_MODEL=anthropic/claude-haiku-4-20250514
AGENT_REVIEW_LLM_SYNTHESIZE_MODEL=anthropic/claude-sonnet-4-20250514
```

### 其他服务商

Azure、Vertex AI、Bedrock 等其他服务商请参考 [litellm 文档](https://docs.litellm.ai/docs/providers)。

## 12.3 双模型策略

Agent Review 使用双模型策略来平衡成本和质量：

| 用途 | 环境变量 | 推荐 | 说明 |
|------|---------|------|------|
| **分类** | `LLM_CLASSIFY_MODEL` | 轻量模型 | 文件分类，调用频繁，需要快速响应 |
| **综合分析** | `LLM_SYNTHESIZE_MODEL` | 强力模型 | 发现分析和解释，需要高质量输出 |
| **备选** | `LLM_FALLBACK_MODEL` | 轻量模型 | 主模型失败时的降级方案 |

## 12.4 成本控制

| 机制 | 说明 |
|------|------|
| `LLM_COST_BUDGET_PER_RUN_CENTS` | 每次审查运行的费用上限（美分），超出后降级为确定性分析 |
| 轻量分类模型 | 使用便宜模型进行高频分类操作 |
| 三级处理策略 | 大量发现时采用采样而非全量处理 |
| 确定性降级 | LLM 失败时自动切换到不需要 LLM 的分析模式 |

## 12.5 降级策略

当 LLM 不可用时，系统仍可继续运行：

1. **主模型失败** → 自动尝试 `FALLBACK_MODEL`
2. **备选模型也失败** → 降级为确定性综合分析
3. **超出费用预算** → 降级为确定性综合分析

确定性综合分析会按类别和严重性对发现分组和排序。
它不提供 LLM 解释。
但它仍会产出完整审查报告。

---

# 附录

## 附录 A：完整环境变量速查表

| 变量 | 默认值 | 说明 |
|------|-------|------|
| `AGENT_REVIEW_DATABASE_URL` | `sqlite+aiosqlite:///./dev.db` | 数据库连接字符串 |
| `AGENT_REVIEW_GITHUB_APP_ID` | `0` | GitHub App ID |
| `AGENT_REVIEW_GITHUB_PRIVATE_KEY` | `""` | .pem 私钥内容 |
| `AGENT_REVIEW_GITHUB_WEBHOOK_SECRET` | `""` | Webhook Secret |
| `AGENT_REVIEW_SECRET_KEY` | `change-me-in-production` | 应用密钥 |
| `AGENT_REVIEW_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT 过期时间 |
| `AGENT_REVIEW_GITHUB_OAUTH_CLIENT_ID` | `""` | OAuth Client ID |
| `AGENT_REVIEW_GITHUB_OAUTH_CLIENT_SECRET` | `""` | OAuth Client Secret |
| `AGENT_REVIEW_OAUTH_REDIRECT_URI` | `""` | OAuth 回调 URL |
| `AGENT_REVIEW_LLM_CLASSIFY_MODEL` | `gpt-4o-mini` | 分类模型 |
| `AGENT_REVIEW_LLM_SYNTHESIZE_MODEL` | `gpt-4o` | 综合分析模型 |
| `AGENT_REVIEW_LLM_FALLBACK_MODEL` | `gpt-4o-mini` | 备选模型 |
| `AGENT_REVIEW_LLM_MAX_TOKENS` | `4096` | 最大 token 数 |
| `AGENT_REVIEW_LLM_TEMPERATURE` | `1.0` | Temperature |
| `AGENT_REVIEW_LLM_COST_BUDGET_PER_RUN_CENTS` | `50` | 费用上限（美分） |
| `AGENT_REVIEW_SONAR_HOST_URL` | `""` | SonarQube 地址 |
| `AGENT_REVIEW_SONAR_TOKEN` | `""` | SonarQube Token |
| `AGENT_REVIEW_SEMGREP_APP_TOKEN` | `""` | Semgrep Token |
| `AGENT_REVIEW_SEMGREP_MODE` | `cli` | Semgrep 模式 |
| `AGENT_REVIEW_SEMGREP_RULES_PATH` | `/opt/semgrep-rules` | Semgrep 规则路径 |
| `AGENT_REVIEW_SEMGREP_SEVERITY_FILTER` | `["ERROR","WARNING"]` | 严重性过滤 |
| `AGENT_REVIEW_MAX_INLINE_COMMENTS` | `25` | 最大行内评论数 |
| `AGENT_REVIEW_MAX_DIFF_LINES` | `10000` | 最大 diff 行数 |
| `AGENT_REVIEW_POLICY_DIR` | `./policies` | 策略目录 |
| `AGENT_REVIEW_PROMPTS_DIR` | `./prompts` | 提示词目录 |
| `AGENT_REVIEW_FRONTEND_DIR` | `./static` | 前端目录 |
| `AGENT_REVIEW_UPLOAD_DIR` | `/tmp/agent_review_uploads` | 上传目录 |
| `AGENT_REVIEW_UPLOAD_MAX_BYTES` | `209715200` | 上传限制 |
| `AGENT_REVIEW_CORS_ORIGINS` | `[]` | CORS 来源 |
| `AGENT_REVIEW_LOG_LEVEL` | `INFO` | 日志级别 |
| `AGENT_REVIEW_LOG_FORMAT` | `console` | 日志格式 |

## 附录 B：策略 YAML 模板

### 默认策略模板

```yaml
version: 1

collectors:
  semgrep:
    failure_mode: degraded
    timeout_seconds: 600
    retries: 0
  secrets:
    failure_mode: degraded
    timeout_seconds: 60
    retries: 0
  sonar:
    failure_mode: optional
    timeout_seconds: 180
    retries: 1
  github_ci:
    failure_mode: degraded
    timeout_seconds: 120
    retries: 0

profiles:
  core_quality:
    require_checks: []
    blocking_categories:
      - "security.*"
      - "quality.bug"
    escalate_categories:
      - "quality.code-smell"
    max_inline_comments: 25
  security_sensitive:
    require_checks:
      - semgrep
      - secrets
    blocking_categories:
      - "security.*"
      - "quality.bug"
      - "quality.vulnerability"
    escalate_categories: []
    max_inline_comments: 50
  workflow_security:
    require_checks: []
    blocking_categories:
      - "security.*"
    escalate_categories:
      - "quality.*"
    max_inline_comments: 15

limits:
  max_inline_comments: 25
  max_summary_findings: 10
  max_diff_lines: 10000

exceptions:
  emergency_bypass_labels:
    - "emergency-bypass"
    - "hotfix"
```

### 严格安全策略示例

```yaml
version: 1

collectors:
  semgrep:
    failure_mode: required    # Semgrep 必须成功
    timeout_seconds: 600
    retries: 1
  secrets:
    failure_mode: required    # 密钥扫描必须成功
    timeout_seconds: 60
    retries: 0
  sonar:
    failure_mode: degraded
    timeout_seconds: 180
    retries: 1
  github_ci:
    failure_mode: degraded
    timeout_seconds: 120
    retries: 0

profiles:
  core_quality:
    require_checks:
      - semgrep
      - secrets
    blocking_categories:
      - "security.*"
      - "quality.bug"
      - "quality.vulnerability"
    escalate_categories:
      - "quality.code-smell"
    max_inline_comments: 50

limits:
  max_inline_comments: 50
  max_summary_findings: 20
  max_diff_lines: 5000

exceptions:
  emergency_bypass_labels:
    - "emergency-bypass"
```

## 附录 C：CLI 命令速查

```bash
# 基线扫描（GitHub）
python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --branch main \
  --output markdown

# 本地扫描
python -m agent_review scan-local \
  --path /code/myrepo \
  --output json

# Docker 内执行基线扫描
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output markdown

# 开发命令
make lint       # 代码检查 + 格式化
make typecheck  # 类型检查
make test       # 运行测试
make check      # 以上全部
make serve      # 启动开发服务器
make migrate    # 数据库迁移
```

## 附录 D：API 端点速查

| 方法 | 路径 | 认证 | 说明 |
|------|------|:----:|------|
| GET | `/health` | 否 | 存活检查 |
| GET | `/ready` | 否 | 就绪检查 |
| POST | `/api/scan` | 否 | 触发扫描 |
| GET | `/api/scan/{id}` | 否 | 查询扫描状态 |
| POST | `/webhooks/github` | HMAC | Webhook 接收 |
| POST | `/api/auth/register` | 否 | 注册 |
| POST | `/api/auth/login` | 否 | 登录 |
| GET | `/api/auth/me` | JWT | 当前用户 |
| GET | `/api/auth/github/authorize` | 否 | OAuth 跳转 |
| GET | `/api/auth/github/callback` | 否 | OAuth 回调 |
| GET | `/api/admin/users` | Admin | 用户列表 |
| POST | `/api/admin/users` | Admin | 创建用户 |
| PATCH | `/api/admin/users/{id}` | Admin | 更新用户 |
| GET | `/api/admin/settings` | Admin | 设置列表 |
| PUT | `/api/admin/settings/{key}` | Admin | 更新设置 |
| DELETE | `/api/admin/settings/{key}` | Admin | 重置设置 |
| GET | `/api/admin/policies` | Admin | 策略列表 |
| POST | `/api/admin/policies` | Admin | 创建策略 |
| GET | `/api/admin/policies/{name}` | Admin | 策略详情 |
| PUT | `/api/admin/policies/{name}` | Admin | 更新策略 |
| DELETE | `/api/admin/policies/{name}` | Admin | 删除策略 |
| GET | `/api/admin/scans` | Admin | 扫描列表 |
| POST | `/api/admin/scans` | Admin | 触发扫描 |
| DELETE | `/api/admin/scans/{id}` | Admin | 删除扫描 |

## 附录 E：常见问题 FAQ

**Q: 只想使用本地扫描，需要配置 GitHub App 吗？**

A: 不需要。
本地扫描只需要 Python 3.12+ 和 LLM API Key。
你可以设置 `AGENT_REVIEW_SEMGREP_MODE=cli`，并确保已安装 semgrep CLI。

**Q: 支持哪些 LLM 服务商？**

A: 系统通过 litellm 支持 100+ 服务商。
具体来说，包括 OpenAI、Google Gemini、Anthropic、Azure OpenAI、AWS Bedrock、GitHub Models 等。
完整列表请参考 [litellm 文档](https://docs.litellm.ai/docs/providers)。

**Q: LLM 调用失败会怎样？**

A: 系统会先尝试 `FALLBACK_MODEL`。
如果仍失败，就会降级为确定性综合分析。
在降级模式下不使用 LLM，但仍输出完整报告。

**Q: 如何降低 LLM 成本？**

A: 你可以使用轻量模型（如 gpt-4o-mini）做分类。
同时应当设置合理的 `COST_BUDGET_PER_RUN_CENTS`。
另一方面，可以降低 `MAX_DIFF_LINES` 以跳过超大 PR。

**Q: 如何添加新的代码分析工具？**

A: 需要实现 `AbstractCollector` 接口，并注册到 registry。
具体步骤见第十一章「添加新收集器」。

**Q: 紧急修复时如何跳过审查？**

A: 为 PR 添加 `emergency-bypass` 或 `hotfix` 标签。
审查仍会运行，但不会阻止合并。

**Q: 支持 GitLab 吗？**

A: 当前版本仅支持 GitHub。
GitLab 支持已进入设计规划，但尚未实现。

**Q: 如何迁移数据库从 SQLite 到 PostgreSQL？**

A: 需要把 `AGENT_REVIEW_DATABASE_URL` 改为 PostgreSQL 连接字符串，然后运行 `make migrate`。
需要注意，SQLite 数据不会自动迁移。
你应当手动导出并导入。

**Q: 首次注册的用户一定是管理员吗？**

A: 是的。
系统中的第一个注册用户会自动成为超级用户（管理员）。

**Q: 运行时修改设置需要重启吗？**

A: 不需要。
通过管理后台修改的设置会持久化到数据库。
新扫描会自动使用新设置。
进行中的扫描不受影响。

## 附录 F：术语表

| 术语 | 说明 |
|------|------|
| **Finding** | 发现，代码审查中检测到的一个问题 |
| **Blocking** | 阻断项，必须修复才能合并的发现 |
| **Advisory** | 建议项，建议修复但不阻止合并的发现 |
| **Verdict** | 决策，审查的最终结论（PASS/WARN/REQUEST_CHANGES/BLOCK/ESCALATE） |
| **Collector** | 收集器，负责收集代码证据的组件 |
| **Profile** | 策略 Profile，定义审查规则的集合 |
| **Gate** | 策略门，根据策略和发现做出决策的控制器 |
| **Supersession** | 取代，新提交时自动取代旧审查的机制 |
| **Baseline Scan** | 基线扫描，对整个仓库的全量扫描 |
| **Check Run** | GitHub Check Run，在 PR 检查标签页显示的状态 |
| **PR Review** | Pull Request Review，包含评论的 PR 审查 |
| **litellm** | LLM 抽象层库，提供统一接口调用多种 LLM 服务商 |
| **Semgrep** | 静态分析安全测试（SAST）工具 |
| **SonarQube** | 代码质量分析平台 |
| **fnmatch** | Python 文件名模式匹配（支持 * 通配符） |
| **ETag** | HTTP 缓存标识，用于策略编辑器的冲突检测 |
| **Webhook** | GitHub 发送的事件通知 HTTP 请求 |
| **Installation ID** | GitHub App 安装在特定组织/仓库后的唯一标识 |
| **JWT** | JSON Web Token，用于身份认证的令牌格式 |
| **Alembic** | SQLAlchemy 的数据库迁移工具 |
