[English](#english) | [简体中文](#简体中文)

---

# English

# Agent Review User Guide

Complete reference for installing, configuring, and operating the Agent Review code review agent.

## Prerequisites

- Python 3.12+
- Docker and Docker Compose (for production deployment)
- A GitHub account with admin access to target repositories (for PR review and baseline scans)
- An LLM API key (OpenAI, Google Gemini, GitHub Models, or any [litellm-supported provider](https://docs.litellm.ai/docs/providers))
- (Optional) Semgrep App token for SAST via the Semgrep API
- (Optional) SonarQube instance and API token

For standalone local scanning, only Python and an LLM API key are required.

## Installation

### Option A: Docker Compose (Recommended)

```bash
git clone https://github.com/kylecui/code-review-agent.git
cd code-review-agent
cp .env.example .env
# Edit .env with your configuration (see Environment Reference below)
docker compose up -d
```

This starts two services:
- **PostgreSQL 16** on port 5432
- **Agent Review app** on port 8000

### Option B: Local Development

```bash
git clone https://github.com/kylecui/code-review-agent.git
cd code-review-agent
pip install uv
uv sync --dev
cp .env.example .env
# Edit .env with your configuration
make migrate    # Run Alembic database migrations
make serve      # Start uvicorn on port 8000 with hot reload
```

Local development uses SQLite by default (`sqlite+aiosqlite:///./dev.db`).

## GitHub App Setup

Skip this section if you only need standalone local scanning.

### 1. Create the App

Go to **GitHub Settings > Developer Settings > GitHub Apps > New GitHub App**.

| Field | Value |
|-------|-------|
| App name | e.g., `My Code Reviewer` |
| Homepage URL | Your server URL |
| Webhook URL | `https://your-server.example.com/webhooks/github` |
| Webhook secret | Generate with `openssl rand -hex 32` |

### 2. Set Permissions

| Permission | Access |
|-----------|--------|
| Checks | Read & Write |
| Contents | Read |
| Pull requests | Read & Write |
| Secret scanning alerts | Read |

### 3. Subscribe to Events

Check **Pull request** under "Subscribe to events".

### 4. Generate Credentials

1. Note the **App ID** from the app settings page.
2. Under **Private keys**, click **Generate a private key**. Save the `.pem` file.
3. Go to **Install App** and install it on your target repositories.
4. Note the **Installation ID** from the URL after installation (e.g., `https://github.com/settings/installations/123456` means ID is `123456`).

## Environment Reference

All configuration is via environment variables with the `AGENT_REVIEW_` prefix.

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_REVIEW_DATABASE_URL` | `sqlite+aiosqlite:///./dev.db` | Database connection string. Use `postgresql+asyncpg://...` for production. |

### GitHub App

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_REVIEW_GITHUB_APP_ID` | `0` | GitHub App ID |
| `AGENT_REVIEW_GITHUB_PRIVATE_KEY` | `""` | Full contents of the `.pem` private key file |
| `AGENT_REVIEW_GITHUB_WEBHOOK_SECRET` | `""` | Must match the secret configured in the GitHub App |

### LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_REVIEW_LLM_CLASSIFY_MODEL` | `gpt-4o-mini` | Cheap model for file classification |
| `AGENT_REVIEW_LLM_SYNTHESIZE_MODEL` | `gpt-4o` | Strong model for findings synthesis |
| `AGENT_REVIEW_LLM_FALLBACK_MODEL` | `gpt-4o-mini` | Fallback when the primary model fails |
| `AGENT_REVIEW_LLM_MAX_TOKENS` | `4096` | Max tokens per LLM call |
| `AGENT_REVIEW_LLM_TEMPERATURE` | `1.0` | LLM temperature |
| `AGENT_REVIEW_LLM_COST_BUDGET_PER_RUN_CENTS` | `50` | Hard cap in cents per review run |

The agent uses [litellm](https://docs.litellm.ai/docs/providers) as its LLM abstraction. Set the appropriate API key environment variable for your provider:

| Provider | API Key Variable | Model Prefix | Example Models |
|----------|-----------------|-------------|----------------|
| OpenAI | `OPENAI_API_KEY` | (none) | `gpt-4o-mini`, `gpt-4o` |
| Google Gemini | `GEMINI_API_KEY` | `gemini/` | `gemini/gemini-2.0-flash`, `gemini/gemini-2.5-pro` |
| GitHub Models | `GITHUB_API_KEY` | `github/` | `github/gpt-4o-mini`, `github/gpt-4o` |
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic/` | `anthropic/claude-sonnet-4-20250514` |

For Azure, Vertex AI, Bedrock, and others, see the [litellm provider docs](https://docs.litellm.ai/docs/providers).

### Collectors

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_REVIEW_SONAR_HOST_URL` | `""` | SonarQube server URL |
| `AGENT_REVIEW_SONAR_TOKEN` | `""` | SonarQube API token |
| `AGENT_REVIEW_SEMGREP_APP_TOKEN` | `""` | Semgrep App token (for `app` mode) |
| `AGENT_REVIEW_SEMGREP_MODE` | `cli` | `app` (Semgrep API), `cli` (local binary), or `disabled` |
| `AGENT_REVIEW_SEMGREP_RULES_PATH` | `/opt/semgrep-rules` | Path to semgrep rules (for `cli` mode) |
| `AGENT_REVIEW_SEMGREP_SEVERITY_FILTER` | `["ERROR","WARNING"]` | Minimum semgrep severity levels to include |

### Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_REVIEW_MAX_INLINE_COMMENTS` | `25` | Max inline comments per review |
| `AGENT_REVIEW_MAX_DIFF_LINES` | `10000` | Skip review if diff exceeds this |

### Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_REVIEW_POLICY_DIR` | `./policies` | Path to policy YAML directory |
| `AGENT_REVIEW_PROMPTS_DIR` | `./prompts` | Path to Jinja2 prompt templates |

### Observability

| Variable | Default | Description |
|----------|---------|-------------|
| `AGENT_REVIEW_LOG_LEVEL` | `INFO` | Log level |
| `AGENT_REVIEW_LOG_FORMAT` | `console` | `json` for production, `console` for development |

## Usage

### Automatic PR Review

Once the GitHub App is installed and the server is running, PRs are reviewed automatically. The agent triggers on:

- `opened` - New PR created
- `synchronize` - New commits pushed to an existing PR
- `ready_for_review` - PR converted from draft to ready

The agent posts a **Check Run** (pass/fail in the PR checks tab) and a **PR Review** with inline comments on relevant lines.

### Baseline Scan (GitHub)

Scan an entire repository without waiting for a PR:

**Via API:**

```bash
curl -X POST https://your-server.example.com/api/scan \
  -H 'Content-Type: application/json' \
  -d '{"repo": "owner/repo", "installation_id": 123456}'
```

**Via CLI (local Python):**

```bash
python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output markdown
```

**Via CLI (Docker):**

```bash
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output markdown
```

#### Baseline CLI Options

| Flag | Required | Description |
|------|----------|-------------|
| `--repo` | Yes | Repository in `owner/name` format |
| `--installation-id` | Yes | GitHub App installation ID |
| `--branch` | No | Branch to scan (defaults to repo default branch) |
| `--ref` | No | Exact commit SHA (takes precedence over `--branch`) |
| `--output` | No | `json` (default), `markdown`, or `github-issue` |
| `--config` | No | Path to `.env` file for settings override |

### Local Scan (Standalone)

Scan any local directory without GitHub credentials:

```bash
python -m agent_review scan-local \
  --path /code/myrepo \
  --output json
```

This mode:
- Runs Semgrep directly on the local directory (requires `semgrep` CLI installed or Docker)
- Skips GitHub-dependent collectors (secrets scanning, GitHub CI)
- Stores results in the local database
- Requires only an LLM API key for the reasoning stage

#### Local Scan CLI Options

| Flag | Required | Description |
|------|----------|-------------|
| `--path` | Yes | Path to local directory |
| `--repo-name` | No | Repository name for reports (defaults to directory name) |
| `--output` | No | `json` (default) or `markdown` |
| `--config` | No | Path to `.env` file for settings override |

### Output Formats

| Format | Description | Best For |
|--------|-------------|----------|
| `json` | Machine-readable JSON with verdict, findings, metrics | CI pipelines, automation |
| `markdown` | Detailed report with executive summary, per-finding evidence, fix recommendations | Human review |
| `github-issue` | Publishes findings as a GitHub Issue with labels | Baseline scan tracking |

## Policy Reference

### File Location

- Default: `policies/default.policy.yaml`
- Per-repo override: `policies/{owner}/{repo}.yaml`

The agent checks for a repo-specific policy first, then falls back to the default.

### Structure

```yaml
version: 1

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

profiles:
  core_quality:               # Always active
    require_checks: []
    blocking_categories:
      - "security.*"          # fnmatch glob patterns
      - "quality.bug"
    escalate_categories:
      - "quality.code-smell"
    max_inline_comments: 25
  security_sensitive:         # Activated for security-related file changes
    require_checks:
      - semgrep
      - secrets
    blocking_categories:
      - "security.*"
      - "quality.bug"
      - "quality.vulnerability"
    escalate_categories: []
    max_inline_comments: 50
  workflow_security:          # Activated for CI/workflow file changes
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

### Collector Failure Modes

| Mode | Behavior |
|------|----------|
| `required` | Pipeline blocks if the collector fails |
| `degraded` | Review continues, failure is noted in the report |
| `optional` | Failures are silently ignored |

### Blocking vs. Advisory Classification

A finding is classified as **blocking** if either condition is true:

1. **Severity-based**: The finding has HIGH or CRITICAL severity.
2. **Policy-based**: The finding's category matches a `blocking_categories` glob pattern in any active profile (e.g., `security.sast` matches `security.*`).

All other findings are **advisory**.

### Verdicts

| Verdict | GitHub Action | Meaning |
|---------|--------------|---------|
| `PASS` | Approve | No issues found |
| `WARN` | Comment | Advisory findings only, no blockers |
| `REQUEST_CHANGES` | Request Changes | Blocking findings that must be addressed |
| `BLOCK` | Request Changes | Critical-severity blocking findings |
| `ESCALATE` | Comment + @mentions | Findings requiring team lead attention |

### Emergency Bypass

Add one of these labels to a PR to skip gate evaluation:
- `emergency-bypass`
- `hotfix`

The agent still runs collectors and posts findings as advisory, but will not block the merge.

## Web Dashboard

### URLs

| URL | Description |
|-----|-------------|
| `/ui/scans` | List of all scan runs (most recent first) |
| `/ui/scans/{run_id}` | Detail view for a specific scan |

### Detail Page

The scan detail page shows:

- **Run overview**: repository, scan kind, state, commit SHA, timestamps
- **Decision**: verdict, confidence, summary, blocking/advisory finding counts, escalation reasons
- **Blocking findings breakdown**:
  - *By severity*: findings with HIGH or CRITICAL severity
  - *By policy*: findings matching a blocking category pattern (shown in a collapsible section)
- **Advisory findings**: findings that don't match any blocking criteria
- **Classification**: change type, domains, risk level, applied profiles
- **Finding details**: severity badge, file location, evidence, impact, fix recommendations, reason for classification
- **Performance metrics**: per-stage timing, LLM cost, collector breakdown

## Pipeline Architecture

The agent processes each scan through a seven-stage pipeline:

### 1. Webhook Reception (PR mode only)

- Verifies HMAC-SHA256 signature
- Ignores bots, drafts, and unhandled actions
- Deduplicates by delivery header and by (repo, PR, head_sha)

### 2. Classification

Deterministic file-pattern heuristic classifies changed files into categories (security, workflow, migration, api, docs, test, general) and assigns:
- **Risk level**: critical, high, medium, or low
- **Policy profiles**: `core_quality` (always), plus `security_sensitive` and/or `workflow_security` as needed

### 3. Evidence Collection

Four collectors run in parallel:
- **Semgrep**: SAST scanning (API or local CLI)
- **SonarQube**: Code quality analysis (optional)
- **GitHub CI**: Check run annotations from existing CI
- **Secrets**: GitHub secret scanning alerts

### 4. Normalization

Raw findings are converted to a canonical schema, then deduplicated by fingerprint. When duplicates exist, the higher severity is kept.

### 5. LLM Reasoning

An LLM synthesizes findings: prioritizing by impact, grouping related issues, generating human-readable explanations. Three-tier strategy based on finding count (single call, chunked, or sampled). Falls back to deterministic synthesis if the LLM fails or the cost budget is exceeded.

### 6. Gate Decision

The gate controller evaluates findings against the active policy profiles and produces a verdict (PASS, WARN, REQUEST_CHANGES, BLOCK, or ESCALATE).

### 7. Publishing (PR mode only)

Creates a GitHub Check Run and a PR Review with structured summary and inline annotations.

### Supersession

When a new commit is pushed to a PR with an in-progress review, the agent supersedes all active reviews for that PR and starts fresh on the new HEAD.

## Deployment

### Exposing the Webhook Endpoint

GitHub must reach your webhook URL over HTTPS. Options:

- **ngrok** (testing): `ngrok http 8000`
- **Cloud VM** with reverse proxy (nginx, Caddy)
- **PaaS**: Cloud Run, Fly.io, Railway, Render

### Health Checks

```bash
curl http://localhost:8000/health   # Always returns {"status":"ok"}
curl http://localhost:8000/ready    # Verifies database connectivity
```

### Viewing Logs

- Docker: `docker compose logs -f app`
- Local: Logs print to console. Set `AGENT_REVIEW_LOG_FORMAT=console` for human-readable output.

### Resource Estimation

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 1 vCPU | 2 vCPU |
| Memory | 512 MB | 1 GB |
| Disk | 1 GB | 5 GB (includes semgrep rules) |
| Database | SQLite (dev) | PostgreSQL 16 (prod) |

LLM costs depend on the provider and model. With `gpt-4o-mini` for classification and `gpt-4o` for synthesis, expect roughly $0.01-$0.10 per review run depending on diff size.

## Troubleshooting

**Webhook not received**
Check that your webhook URL is publicly accessible. Verify delivery status in GitHub App settings: Settings > Developer Settings > your app > Advanced > Recent Deliveries.

**401 Unauthorized on webhook**
The webhook secret in `.env` does not match the GitHub App configuration. Regenerate and sync both.

**Pipeline stuck at COLLECTING**
A collector is timing out. Check `AGENT_REVIEW_SEMGREP_MODE` (set to `disabled` if you don't have a Semgrep token). Verify network access to external APIs.

**LLM errors or empty synthesis**
Verify the API key environment variable is set. If budget is too low, increase `AGENT_REVIEW_LLM_COST_BUDGET_PER_RUN_CENTS`. Check logs for litellm error messages.

**No review posted on the PR**
Confirm the GitHub App has Checks (Read & Write) and Pull requests (Read & Write) permissions. Verify the app is installed on the target repository. Check that the PR is not a draft and was not opened by a bot.

**Template directory not found**
Set `AGENT_REVIEW_PROMPTS_DIR` to the absolute path of the `prompts/` directory. In Docker, the default `./prompts` resolves relative to `WORKDIR /app`.

## Make Commands

```
make lint       # Ruff check with auto-fix + format
make typecheck  # Mypy strict mode
make test       # Pytest with coverage
make check      # All of the above
make serve      # Dev server on port 8000 with hot reload
make migrate    # Alembic database migrations
```

## Admin Dashboard

### First-Time Setup

After deployment, navigate to your instance URL. The login page appears. Register the first account — it is automatically promoted to admin (superuser).

### GitHub OAuth Configuration

To enable "Sign in with GitHub":

1. Go to your GitHub App settings > General
2. Under "Identifying and authorizing users", set:
   - **Callback URL**: `https://your-server.example.com/api/auth/github/callback`
3. Copy the Client ID and generate a Client Secret
4. Set in `.env`:
   ```
   AGENT_REVIEW_GITHUB_OAUTH_CLIENT_ID=your_client_id
   AGENT_REVIEW_GITHUB_OAUTH_CLIENT_SECRET=your_client_secret
   AGENT_REVIEW_OAUTH_REDIRECT_URI=https://your-server.example.com/api/auth/github/callback
   ```
5. Restart the application

### Scan Dashboard

- Navigate to **Scans** in the sidebar
- View all scan runs with filters for repository, state, and scan type
- Click any scan to see detailed findings grouped by blocking vs advisory
- Admins can trigger new baseline scans, cancel running scans, and delete completed scans

### Settings Management

- Navigate to **Settings** in the sidebar (admin only)
- Settings are grouped into: LLM Configuration, Collectors, Limits, Observability
- Edit any value and click Save to persist to the database
- Click "Reset" on any setting to revert to the environment default
- Changes take effect for new scans only; in-flight scans use their original settings

### Policy Editor

- Navigate to **Policies** in the sidebar (admin only)
- View all stored policies; click to edit in the Monaco YAML editor
- Create per-repository policy overrides (e.g., `owner/repo`)
- The editor validates YAML syntax and PolicyConfig schema on save
- ETag-based conflict detection prevents overwriting concurrent edits
- Use "Seed from Disk" to import policies from the `policies/` directory

### User Management

- Navigate to **Users** in the sidebar (admin only)
- View all users with their roles, status, and GitHub link
- Create new users with email/password and admin/viewer role
- Toggle user active status or superuser role
- Self-protection: you cannot remove your own admin role or deactivate yourself

---

# 简体中文

# Agent Review 用户指南

Agent Review 代码审查代理的安装、配置和运维完整参考。

## 前提条件

- Python 3.12+
- Docker 和 Docker Compose（生产部署）
- 拥有目标仓库管理员权限的 GitHub 账号（PR 审查和基线扫描需要）
- LLM API Key（OpenAI、Google Gemini、GitHub Models 或任何 [litellm 支持的服务商](https://docs.litellm.ai/docs/providers)）
- （可选）Semgrep App Token，用于通过 Semgrep API 进行 SAST 扫描
- （可选）SonarQube 实例和 API Token

如果只需要本地独立扫描，只需 Python 和 LLM API Key。

## 安装

### 方案 A：Docker Compose（推荐）

```bash
git clone https://github.com/kylecui/code-review-agent.git
cd code-review-agent
cp .env.example .env
# 编辑 .env，填入你的配置（参见下方「环境变量参考」）
docker compose up -d
```

启动两个服务：
- **PostgreSQL 16**，端口 5432
- **Agent Review 应用**，端口 8000

### 方案 B：本地开发

```bash
git clone https://github.com/kylecui/code-review-agent.git
cd code-review-agent
pip install uv
uv sync --dev
cp .env.example .env
# 编辑 .env
make migrate    # 运行数据库迁移
make serve      # 启动开发服务器，端口 8000，支持热重载
```

本地开发默认使用 SQLite（`sqlite+aiosqlite:///./dev.db`）。

## GitHub App 设置

如果只需要本地独立扫描，可跳过本节。

### 1. 创建 App

进入 **GitHub Settings > Developer Settings > GitHub Apps > New GitHub App**。

| 字段 | 值 |
|------|---|
| App name | 例如 `My Code Reviewer` |
| Homepage URL | 你的服务器地址 |
| Webhook URL | `https://your-server.example.com/webhooks/github` |
| Webhook secret | 用 `openssl rand -hex 32` 生成 |

### 2. 设置权限

| 权限 | 访问级别 |
|------|---------|
| Checks | 读写 |
| Contents | 只读 |
| Pull requests | 读写 |
| Secret scanning alerts | 只读 |

### 3. 订阅事件

勾选「Subscribe to events」下的 **Pull request**。

### 4. 生成凭据

1. 在 App 设置页面记录 **App ID**。
2. 在「Private keys」下点击 **Generate a private key**，保存 `.pem` 文件。
3. 进入 **Install App**，将其安装到目标仓库。
4. 安装后从 URL 中获取 **Installation ID**（如 `https://github.com/settings/installations/123456` 则 ID 为 `123456`）。

## 环境变量参考

所有配置通过 `AGENT_REVIEW_` 前缀的环境变量设置。

### 数据库

| 变量 | 默认值 | 说明 |
|------|-------|------|
| `AGENT_REVIEW_DATABASE_URL` | `sqlite+aiosqlite:///./dev.db` | 数据库连接字符串。生产环境使用 `postgresql+asyncpg://...` |

### GitHub App

| 变量 | 默认值 | 说明 |
|------|-------|------|
| `AGENT_REVIEW_GITHUB_APP_ID` | `0` | GitHub App ID |
| `AGENT_REVIEW_GITHUB_PRIVATE_KEY` | `""` | `.pem` 私钥文件的完整内容 |
| `AGENT_REVIEW_GITHUB_WEBHOOK_SECRET` | `""` | 必须与 GitHub App 中配置的 secret 一致 |

### LLM

| 变量 | 默认值 | 说明 |
|------|-------|------|
| `AGENT_REVIEW_LLM_CLASSIFY_MODEL` | `gpt-4o-mini` | 用于文件分类的轻量模型 |
| `AGENT_REVIEW_LLM_SYNTHESIZE_MODEL` | `gpt-4o` | 用于发现综合分析的强力模型 |
| `AGENT_REVIEW_LLM_FALLBACK_MODEL` | `gpt-4o-mini` | 主模型失败时的备选 |
| `AGENT_REVIEW_LLM_MAX_TOKENS` | `4096` | 每次 LLM 调用的最大 token 数 |
| `AGENT_REVIEW_LLM_TEMPERATURE` | `1.0` | LLM temperature |
| `AGENT_REVIEW_LLM_COST_BUDGET_PER_RUN_CENTS` | `50` | 每次审查的费用上限（美分） |

代理使用 [litellm](https://docs.litellm.ai/docs/providers) 作为 LLM 抽象层。根据服务商设置对应的 API Key：

| 服务商 | API Key 变量 | 模型前缀 | 示例模型 |
|-------|-------------|---------|---------|
| OpenAI | `OPENAI_API_KEY` | （无） | `gpt-4o-mini`、`gpt-4o` |
| Google Gemini | `GEMINI_API_KEY` | `gemini/` | `gemini/gemini-2.0-flash`、`gemini/gemini-2.5-pro` |
| GitHub Models | `GITHUB_API_KEY` | `github/` | `github/gpt-4o-mini`、`github/gpt-4o` |
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic/` | `anthropic/claude-sonnet-4-20250514` |

Azure、Vertex AI、Bedrock 等其他服务商请参考 [litellm 文档](https://docs.litellm.ai/docs/providers)。

### 收集器

| 变量 | 默认值 | 说明 |
|------|-------|------|
| `AGENT_REVIEW_SONAR_HOST_URL` | `""` | SonarQube 服务器地址 |
| `AGENT_REVIEW_SONAR_TOKEN` | `""` | SonarQube API Token |
| `AGENT_REVIEW_SEMGREP_APP_TOKEN` | `""` | Semgrep App Token（`app` 模式使用） |
| `AGENT_REVIEW_SEMGREP_MODE` | `cli` | `app`（Semgrep API）、`cli`（本地二进制）或 `disabled` |
| `AGENT_REVIEW_SEMGREP_RULES_PATH` | `/opt/semgrep-rules` | semgrep 规则路径（`cli` 模式使用） |
| `AGENT_REVIEW_SEMGREP_SEVERITY_FILTER` | `["ERROR","WARNING"]` | 包含的最低 semgrep 严重性级别 |

### 限制

| 变量 | 默认值 | 说明 |
|------|-------|------|
| `AGENT_REVIEW_MAX_INLINE_COMMENTS` | `25` | 每次审查的最大行内评论数 |
| `AGENT_REVIEW_MAX_DIFF_LINES` | `10000` | diff 超过此行数时跳过审查 |

### 路径

| 变量 | 默认值 | 说明 |
|------|-------|------|
| `AGENT_REVIEW_POLICY_DIR` | `./policies` | 策略 YAML 文件目录 |
| `AGENT_REVIEW_PROMPTS_DIR` | `./prompts` | Jinja2 提示词模板目录 |

### 可观测性

| 变量 | 默认值 | 说明 |
|------|-------|------|
| `AGENT_REVIEW_LOG_LEVEL` | `INFO` | 日志级别 |
| `AGENT_REVIEW_LOG_FORMAT` | `console` | 生产环境用 `json`，开发环境用 `console` |

## 使用方式

### 自动 PR 审查

GitHub App 安装并且服务运行后，PR 会被自动审查。触发事件：

- `opened` - 创建新 PR
- `synchronize` - 向已有 PR 推送新提交
- `ready_for_review` - PR 从草稿转为就绪状态

代理会发布 **Check Run**（在 PR 的 checks 标签页显示通过/失败）和 **PR Review**（含行内评论）。

### 基线扫描（GitHub）

无需等待 PR，直接扫描整个仓库：

**通过 API：**

```bash
curl -X POST https://your-server.example.com/api/scan \
  -H 'Content-Type: application/json' \
  -d '{"repo": "owner/repo", "installation_id": 123456}'
```

**通过 CLI（本地 Python）：**

```bash
python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output markdown
```

**通过 CLI（Docker）：**

```bash
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output markdown
```

#### 基线扫描 CLI 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--repo` | 是 | 仓库，格式为 `owner/name` |
| `--installation-id` | 是 | GitHub App Installation ID |
| `--branch` | 否 | 扫描分支（默认为仓库默认分支） |
| `--ref` | 否 | 精确的 commit SHA（优先于 `--branch`） |
| `--output` | 否 | `json`（默认）、`markdown` 或 `github-issue` |
| `--config` | 否 | `.env` 文件路径，用于覆盖配置 |

### 本地扫描（独立运行）

无需 GitHub 凭据，直接扫描本地目录：

```bash
python -m agent_review scan-local \
  --path /code/myrepo \
  --output json
```

本模式的特点：
- 直接在本地目录运行 Semgrep（需要安装 `semgrep` CLI 或使用 Docker）
- 跳过依赖 GitHub 的收集器（密钥扫描、GitHub CI）
- 结果存储在本地数据库
- 仅需 LLM API Key 用于推理阶段

#### 本地扫描 CLI 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `--path` | 是 | 本地目录路径 |
| `--repo-name` | 否 | 报告中的仓库名称（默认为目录名） |
| `--output` | 否 | `json`（默认）或 `markdown` |
| `--config` | 否 | `.env` 文件路径，用于覆盖配置 |

### 输出格式

| 格式 | 说明 | 适用场景 |
|------|------|---------|
| `json` | 机器可读的 JSON，包含决策、发现、指标 | CI 流水线、自动化 |
| `markdown` | 详细报告，含摘要、逐项证据和修复建议 | 人工审查 |
| `github-issue` | 以 GitHub Issue 形式发布发现，带标签 | 基线扫描跟踪 |

## 策略参考

### 文件位置

- 默认策略：`policies/default.policy.yaml`
- 按仓库覆盖：`policies/{owner}/{repo}.yaml`

代理优先查找仓库特定策略，找不到则使用默认策略。

### 结构

```yaml
version: 1

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

limits:
  max_inline_comments: 25
  max_summary_findings: 10
  max_diff_lines: 10000

exceptions:
  emergency_bypass_labels:
    - "emergency-bypass"
    - "hotfix"
```

### 收集器失败模式

| 模式 | 行为 |
|------|------|
| `required` | 收集器失败时流水线中断 |
| `degraded` | 继续审查，报告中注明失败 |
| `optional` | 静默忽略失败 |

### 阻断 vs. 建议分类

一个发现被归类为**阻断项**，需满足以下任一条件：

1. **基于严重性**：发现的严重性为 HIGH 或 CRITICAL。
2. **基于策略**：发现的类别匹配任何活跃 profile 中 `blocking_categories` 的通配符模式（如 `security.sast` 匹配 `security.*`）。

其他所有发现为**建议项**。

### 决策结果

| 决策 | GitHub 操作 | 含义 |
|------|-----------|------|
| `PASS` | 批准 | 未发现问题 |
| `WARN` | 评论 | 仅有建议项，无阻断项 |
| `REQUEST_CHANGES` | 请求修改 | 存在需要处理的阻断项 |
| `BLOCK` | 请求修改 | 存在 CRITICAL 严重性的阻断项 |
| `ESCALATE` | 评论 + @提及 | 需要团队负责人关注 |

### 紧急绕过

为 PR 添加以下标签可跳过策略评估：
- `emergency-bypass`
- `hotfix`

代理仍会运行收集器并以建议形式发布发现，但不会阻止合并。

## Web 仪表盘

### 访问地址

| 地址 | 说明 |
|------|------|
| `/ui/scans` | 所有扫描记录列表（按时间倒序） |
| `/ui/scans/{run_id}` | 单次扫描详情 |

### 详情页面

扫描详情页展示：

- **运行概览**：仓库、扫描类型、状态、commit SHA、时间戳
- **决策结果**：决策、置信度、摘要、阻断/建议发现数量、上报原因
- **阻断发现分组**：
  - *按严重性*：HIGH 或 CRITICAL 严重性的发现
  - *按策略*：匹配阻断类别模式的发现（可折叠展示）
- **建议发现**：不匹配任何阻断条件的发现
- **分类信息**：变更类型、领域、风险级别、激活的 profile
- **发现详情**：严重性标签、文件位置、证据、影响、修复建议、分类原因
- **性能指标**：各阶段耗时、LLM 成本、收集器详情

## 流水线架构

代理通过七个阶段处理每次扫描：

### 1. Webhook 接收（仅 PR 模式）

- 验证 HMAC-SHA256 签名
- 忽略 Bot、草稿和未处理的事件
- 按 delivery header 和 (repo, PR, head_sha) 去重

### 2. 分类

确定性的文件模式启发式方法将变更文件分类为不同类别（security、workflow、migration、api、docs、test、general），并分配：
- **风险级别**：critical、high、medium 或 low
- **策略 profile**：`core_quality`（始终激活），按需加上 `security_sensitive` 和/或 `workflow_security`

### 3. 证据收集

四个收集器并行运行：
- **Semgrep**：SAST 扫描（API 或本地 CLI）
- **SonarQube**：代码质量分析（可选）
- **GitHub CI**：从已有 CI 提取 Check Run 注解
- **Secrets**：GitHub 密钥扫描告警

### 4. 归一化

将各收集器的原始发现转换为统一格式，按指纹去重。存在重复时保留较高严重性。

### 5. LLM 推理

LLM 对发现进行综合分析：按影响排序、关联相关问题、生成可读的解释。根据发现数量采用三级策略（单次调用、分块处理或采样处理）。LLM 失败或超出费用预算时回退到确定性综合分析。

### 6. 策略决策

策略控制器根据活跃的 profile 评估发现，生成决策结果（PASS、WARN、REQUEST_CHANGES、BLOCK 或 ESCALATE）。

### 7. 发布（仅 PR 模式）

创建 GitHub Check Run 和 PR Review，包含结构化摘要和行内注解。

### 取代机制

当新提交推送到有正在进行审查的 PR 时，代理会取代该 PR 的所有活跃审查，并基于新的 HEAD 重新开始。

## 部署

### 暴露 Webhook 端点

GitHub 需要通过 HTTPS 访问你的 Webhook URL。方案：

- **ngrok**（测试用）：`ngrok http 8000`
- **云服务器** + 反向代理（nginx、Caddy）
- **PaaS**：Cloud Run、Fly.io、Railway、Render

### 健康检查

```bash
curl http://localhost:8000/health   # 始终返回 {"status":"ok"}
curl http://localhost:8000/ready    # 验证数据库连接
```

### 查看日志

- Docker：`docker compose logs -f app`
- 本地：日志输出到控制台。设置 `AGENT_REVIEW_LOG_FORMAT=console` 获取可读格式。

### 资源估算

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 1 vCPU | 2 vCPU |
| 内存 | 512 MB | 1 GB |
| 磁盘 | 1 GB | 5 GB（含 semgrep 规则） |
| 数据库 | SQLite（开发） | PostgreSQL 16（生产） |

LLM 成本取决于服务商和模型。使用 `gpt-4o-mini` 分类 + `gpt-4o` 综合分析时，每次审查约 $0.01-$0.10，视 diff 大小而定。

## 故障排查

**收不到 Webhook**
检查 Webhook URL 是否可从公网访问。在 GitHub App 设置中查看投递状态：Settings > Developer Settings > 你的 App > Advanced > Recent Deliveries。

**Webhook 返回 401 Unauthorized**
`.env` 中的 Webhook secret 与 GitHub App 配置不一致。重新生成并同步。

**流水线卡在 COLLECTING 状态**
某个收集器超时。检查 `AGENT_REVIEW_SEMGREP_MODE`（没有 Semgrep Token 时设为 `disabled`）。确认网络能访问外部 API。

**LLM 错误或综合分析为空**
确认 API Key 环境变量已设置。预算过低时增大 `AGENT_REVIEW_LLM_COST_BUDGET_PER_RUN_CENTS`。查看日志中的 litellm 错误信息。

**PR 上没有发布审查**
确认 GitHub App 有 Checks（读写）和 Pull requests（读写）权限。确认 App 已安装到目标仓库。检查 PR 不是草稿且不是 Bot 创建的。

**找不到模板目录**
设置 `AGENT_REVIEW_PROMPTS_DIR` 为 `prompts/` 目录的绝对路径。Docker 中默认 `./prompts` 相对于 `WORKDIR /app`。

## Make 命令

```
make lint       # Ruff 检查（自动修复）+ 格式化
make typecheck  # Mypy 严格模式
make test       # Pytest 含覆盖率
make check      # 以上全部
make serve      # 开发服务器，端口 8000，热重载
make migrate    # Alembic 数据库迁移
```

## 管理仪表盘

### 首次设置

部署完成后，访问实例 URL。登录页面会出现。注册第一个账号 — 自动升级为管理员（超级用户）。

### GitHub OAuth 配置

启用"使用 GitHub 登录"：

1. 前往 GitHub App 设置 > 通用
2. 在"识别和授权用户"下，设置：
   - **回调 URL**：`https://your-server.example.com/api/auth/github/callback`
3. 复制 Client ID 并生成 Client Secret
4. 在 `.env` 中设置：
   ```
   AGENT_REVIEW_GITHUB_OAUTH_CLIENT_ID=your_client_id
   AGENT_REVIEW_GITHUB_OAUTH_CLIENT_SECRET=your_client_secret
   AGENT_REVIEW_OAUTH_REDIRECT_URI=https://your-server.example.com/api/auth/github/callback
   ```
5. 重启应用

### 扫描仪表盘

- 点击侧栏中的**扫描**
- 查看所有扫描记录，支持按仓库、状态和扫描类型筛选
- 点击任意扫描查看详细发现，按阻断/建议分类分组
- 管理员可以触发新基线扫描、取消运行中的扫描、删除已完成的扫描

### 设置管理

- 点击侧栏中的**设置**（仅管理员）
- 设置分为：LLM 配置、收集器、限制、可观测性
- 编辑任意值并点击保存以持久化到数据库
- 点击"重置"可将设置恢复为环境变量默认值
- 更改仅对新扫描生效；进行中的扫描使用原始设置

### 策略编辑器

- 点击侧栏中的**策略**（仅管理员）
- 查看所有存储的策略；点击在 Monaco YAML 编辑器中编辑
- 创建按仓库覆盖的策略（如 `owner/repo`）
- 编辑器在保存时验证 YAML 语法和 PolicyConfig 模式
- 基于 ETag 的冲突检测防止覆盖并发编辑
- 使用"从磁盘导入"将 `policies/` 目录中的策略导入数据库

### 用户管理

- 点击侧栏中的**用户**（仅管理员）
- 查看所有用户的角色、状态和 GitHub 关联
- 创建新用户，设置邮箱/密码和管理员/查看者角色
- 切换用户活跃状态或超级用户角色
- 自我保护：不能移除自己的管理员角色或停用自己
