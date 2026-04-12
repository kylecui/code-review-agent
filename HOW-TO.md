# Agent Review: HOW-TO Guide

## Overview

Agent Review is a policy-grounded code review bot for GitHub. It receives pull request webhooks, runs deterministic evidence collectors (Semgrep, SonarQube, GitHub CI annotations, secrets scanning), normalizes and deduplicates findings, uses an LLM to prioritize and explain them, evaluates a gate policy to produce a merge verdict, and posts structured feedback as GitHub Check Runs and PR Reviews.

## Prerequisites

- Python 3.12+
- A GitHub account with admin access to the target repositories
- Docker and Docker Compose (for production deployment)
- An OpenAI API key (or any LLM provider supported by [litellm](https://docs.litellm.ai/))
- (Optional) A Semgrep App token for SAST scanning via the Semgrep API
- (Optional) A SonarQube instance and API token for quality analysis

## Step 1: Create a GitHub App

1. Go to **GitHub Settings > Developer Settings > GitHub Apps > New GitHub App**.
2. Fill in the basics:
   - **App name**: e.g. `My Code Reviewer`
   - **Homepage URL**: your server URL (e.g. `https://review.example.com`)
   - **Webhook URL**: `https://your-server.example.com/webhooks/github`
   - **Webhook secret**: generate a strong random string (e.g. `openssl rand -hex 32`)
3. Set **Repository permissions**:
   - **Checks**: Read & Write
   - **Contents**: Read
   - **Pull requests**: Read & Write
   - **Secret scanning alerts**: Read
4. Under **Subscribe to events**, check **Pull request**.
5. Click **Create GitHub App**.
6. On the app settings page, note the **App ID**.
7. Scroll to **Private keys** and click **Generate a private key**. Save the `.pem` file.
8. Go to **Install App** in the sidebar and install it on the repositories you want reviewed.

## Step 2: Configure Environment

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Full reference for `.env`:

```bash
# Database
AGENT_REVIEW_DATABASE_URL=sqlite+aiosqlite:///./dev.db  # For dev. Use PostgreSQL for prod.

# GitHub App (REQUIRED)
AGENT_REVIEW_GITHUB_APP_ID=123456                       # App ID from GitHub App settings
AGENT_REVIEW_GITHUB_PRIVATE_KEY="-----BEGIN RSA..."     # Full contents of the .pem file
AGENT_REVIEW_GITHUB_WEBHOOK_SECRET=your-webhook-secret  # Must match the secret in your GitHub App

# LLM (REQUIRED)
AGENT_REVIEW_LLM_CLASSIFY_MODEL=gpt-4o-mini             # Cheap model for file classification
AGENT_REVIEW_LLM_SYNTHESIZE_MODEL=gpt-4o                # Strong model for findings synthesis
AGENT_REVIEW_LLM_FALLBACK_MODEL=gpt-4o-mini             # Fallback if the primary model fails
AGENT_REVIEW_LLM_MAX_TOKENS=4096
AGENT_REVIEW_LLM_COST_BUDGET_PER_RUN_CENTS=50           # Hard cap: 50 cents per review run

# Collectors (OPTIONAL)
AGENT_REVIEW_SONAR_HOST_URL=https://sonar.example.com   # SonarQube server URL
AGENT_REVIEW_SONAR_TOKEN=squ_xxxxx                      # SonarQube API token
AGENT_REVIEW_SEMGREP_APP_TOKEN=xxx                      # Semgrep App token
AGENT_REVIEW_SEMGREP_MODE=app                            # "app" (Semgrep API), "cli" (local binary), or "disabled"

# Limits
AGENT_REVIEW_MAX_INLINE_COMMENTS=25                     # Max inline comments per review
AGENT_REVIEW_MAX_DIFF_LINES=10000                       # Skip review if diff exceeds this

# Policy
AGENT_REVIEW_POLICY_DIR=./policies                      # Path to policy YAML directory

# Observability
AGENT_REVIEW_LOG_LEVEL=INFO
AGENT_REVIEW_LOG_FORMAT=json                             # "json" for production, "console" for dev
```

You also need to set the LLM provider API key in the environment. The agent uses [litellm](https://docs.litellm.ai/docs/providers) as its LLM abstraction, so you can swap providers by changing the model strings and API key.

**OpenAI:**

```bash
export OPENAI_API_KEY=sk-...

# Model strings (default, no prefix needed):
AGENT_REVIEW_LLM_CLASSIFY_MODEL=gpt-4o-mini
AGENT_REVIEW_LLM_SYNTHESIZE_MODEL=gpt-4o
```

**Google Gemini (AI Studio):**

```bash
export GEMINI_API_KEY=your-gemini-api-key

# Model strings use the "gemini/" prefix:
AGENT_REVIEW_LLM_CLASSIFY_MODEL=gemini/gemini-2.0-flash
AGENT_REVIEW_LLM_SYNTHESIZE_MODEL=gemini/gemini-2.5-pro
```

**GitHub Models:**

Get a personal access token from [github.com/marketplace/models](https://github.com/marketplace/models).

```bash
export GITHUB_API_KEY=ghp_...

# Model strings use the "github/" prefix:
AGENT_REVIEW_LLM_CLASSIFY_MODEL=github/gpt-4o-mini
AGENT_REVIEW_LLM_SYNTHESIZE_MODEL=github/gpt-4o
```

For other providers (Anthropic, Azure, Vertex AI, etc.), see the [litellm provider docs](https://docs.litellm.ai/docs/providers).

## Step 3: Deploy

### Option A: Docker Compose (Recommended for Production)

```bash
cp .env.example .env
# Edit .env with your real values (App ID, private key, webhook secret, API keys)
docker compose up -d
```

This starts two services:
- **PostgreSQL 16** on port 5432
- **Agent Review app** on port 8000

The app connects to `postgresql+asyncpg://agent_review:agent_review_dev@db:5432/agent_review`. For a real production deployment, change the database password in `docker-compose.yml` and your `.env`.

### Option B: Local Development

```bash
git clone https://github.com/kylecui/code-review-agent.git
cd code-review-agent
pip install uv          # if not already installed
uv sync --dev
cp .env.example .env
# Edit .env with your values
make migrate            # Run Alembic database migrations
make serve              # Start uvicorn on port 8000 with hot reload
```

### Exposing the Webhook Endpoint

GitHub must be able to reach your webhook URL over HTTPS. Options:

- **ngrok** (quickest for testing): `ngrok http 8000`, then use the generated HTTPS URL as your webhook URL in the GitHub App settings.
- **Cloud VM** with a public IP behind a reverse proxy (nginx, Caddy).
- **Platform-as-a-Service**: Cloud Run, Fly.io, Railway, Render, etc.

## Step 4: Verify the Setup

```bash
# Health check (always returns ok)
curl http://localhost:8000/health
# {"status":"ok"}

# Readiness check (verifies database connectivity)
curl http://localhost:8000/ready
# {"status":"ready"}
```

Once both return successfully, open a pull request on one of the installed repositories. The agent will post a Check Run and a PR Review within a few seconds.

## Baseline Scanning (Full-Repository Scan)

You can scan an entire repository without waiting for a PR. This is useful for establishing a baseline of existing code quality issues.

### Via API

```bash
# Trigger a baseline scan
curl -X POST https://your-server.example.com/api/scan \
  -H 'Content-Type: application/json' \
  -d '{"repo": "owner/repo", "installation_id": 123456}'

# Response: {"status": "queued", "run_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"}

# Check scan status
curl https://your-server.example.com/api/scan/<run_id>
```

### Via CLI (Local)

```bash
python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output json          # json | markdown | github-issue
```

### Via CLI (Docker)

If running in Docker Compose, use `docker exec` to run the CLI inside the container:

```bash
# JSON report (machine-readable)
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output json

# Markdown report (detailed, human-readable)
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output markdown

# Publish as a GitHub Issue
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output github-issue

# Save the markdown report to a file
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --output markdown > report.md

# Scan a specific branch
docker exec code-review-agent-app-1 \
  python -m agent_review scan \
  --repo owner/repo \
  --installation-id 123456 \
  --branch develop \
  --output markdown
```

### CLI Options

| Flag | Required | Description |
|------|----------|-------------|
| `--repo` | Yes | Repository in `owner/name` format |
| `--installation-id` | Yes | GitHub App installation ID |
| `--branch` | No | Branch to scan (defaults to repo default branch) |
| `--ref` | No | Exact commit SHA (takes precedence over `--branch`) |
| `--output` | No | Output format: `json` (default), `markdown`, `github-issue` |
| `--config` | No | Path to `.env` file for settings override |

### Output Formats

- **json**: Machine-readable JSON with verdict, findings, metrics. Best for CI pipelines and automation.
- **markdown**: Full detailed report with executive summary, per-finding evidence/impact/fix recommendations, collector status, and performance metrics. Best for human review.
- **github-issue**: Publishes findings as a GitHub Issue on the repository with labels `code-review` and `baseline-scan`.

## Web UI

The agent includes a built-in web dashboard for viewing scan results in a browser.

### Accessing the Web UI

Navigate to `https://your-server.example.com/ui/scans` in your browser.

Available pages:

| URL | Description |
|-----|-------------|
| `/ui/scans` | List of all scan runs (most recent first, up to 100) |
| `/ui/scans/{run_id}` | Detail view for a specific scan run |

The detail page shows:
- **Run overview**: repository, kind, state, SHA, timestamps
- **Decision**: verdict, confidence, summary, blocking/advisory findings, escalation reasons
- **Classification**: change type, domains, risk level, applied profiles
- **Findings**: severity, location, evidence, impact, fix recommendations
- **Performance metrics**: per-stage timing, LLM cost, collector breakdown

## How It Works

The agent processes each PR through a seven-stage pipeline:

### 1. Webhook Reception

GitHub sends a `pull_request` event when a PR is opened, updated (synchronize), or marked ready for review. The agent:
- Verifies the HMAC-SHA256 signature against `AGENT_REVIEW_GITHUB_WEBHOOK_SECRET`.
- Ignores events from bots, draft PRs, and unhandled actions.
- Deduplicates by `X-GitHub-Delivery` header and by `(repo, pr_number, head_sha)`.

### 2. Classification

A deterministic file-pattern heuristic classifies changed files into categories: security, workflow, migration, api, docs, test, or general. Based on these categories, the classifier assigns:
- A **risk level**: critical, high, medium, or low.
- One or more **policy profiles**: `core_quality` (always), plus `security_sensitive` and/or `workflow_security` if applicable.

### 3. Evidence Collection

Four collectors run in parallel:
- **Semgrep**: SAST scanning via the Semgrep App API or local CLI.
- **SonarQube**: Code quality analysis via REST API.
- **GitHub CI**: Extracts check run annotations from existing CI pipelines.
- **Secrets**: Reads GitHub secret scanning alerts for the PR.

Semgrep and Secrets are always required. SonarQube is optional. GitHub CI runs in degraded mode (failures are tolerated but noted).

### 4. Normalization and Deduplication

Raw findings from all collectors are converted into a canonical schema with uniform fields (severity, category, file, line, message, etc.). Findings are then deduplicated by fingerprint. When duplicates are found, the higher severity is kept.

### 5. LLM Reasoning

An LLM synthesizes the normalized findings: prioritizing by impact, grouping related issues, and generating human-readable explanations. The system uses a three-tier strategy based on finding count:
- **Small** (few findings): processed in a single LLM call.
- **Medium**: chunked for the LLM.
- **Large**: summarized with sampling.

If the LLM call fails or the per-run cost budget is exceeded, the agent falls back to a deterministic synthesis that groups and ranks findings without LLM assistance.

### 6. Gate Decision

The gate controller evaluates findings against the active policy and produces one of five verdicts:

| Verdict | GitHub Action | Meaning |
|---------|--------------|---------|
| `PASS` | Approve | No issues found. |
| `WARN` | Comment | Advisory findings only, no blockers. |
| `REQUEST_CHANGES` | Request Changes | Blocking findings that must be addressed. |
| `BLOCK` | Request Changes | Critical-severity blocking findings. |
| `ESCALATE` | Comment + @mentions | Findings that require team lead attention. |

### 7. Publishing

The agent creates a GitHub Check Run (pass/fail status visible in the PR checks tab) and a PR Review with a structured summary and up to `max_inline_comments` inline annotations on the relevant lines.

## Customizing Policies

Policies are YAML files in the `policies/` directory. The default policy (`policies/default.policy.yaml`):

```yaml
version: 1
collectors:
  semgrep:
    failure_mode: required
    timeout_seconds: 120
    retries: 1
  secrets:
    failure_mode: required
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
    require_checks:
      - semgrep
      - secrets
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
      - sonar
    blocking_categories:
      - "security.*"
      - "quality.bug"
      - "quality.vulnerability"
    escalate_categories: []
    max_inline_comments: 50
  workflow_security:
    require_checks:
      - semgrep
      - secrets
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

### Policy Sections

- **collectors**: Defines each collector's failure behavior. `required` means the pipeline blocks if the collector fails. `degraded` means the review continues but notes the gap. `optional` means failures are silently ignored.
- **profiles**: Each profile maps to a set of `blocking_categories` and `escalate_categories` using fnmatch glob patterns (e.g. `security.*` matches `security.xss`, `security.sqli`, etc.). The classifier selects which profiles apply based on the changed files.
- **limits**: Global caps on inline comments, summary findings, and diff size.
- **exceptions**: PR labels that trigger emergency bypass.

### Per-Repository Overrides

Create a file at `policies/{owner}/{repo}.yaml` to override the default policy for a specific repository. For example, `policies/kylecui/my-app.yaml` applies to the `kylecui/my-app` repo. The agent checks for a repo-specific policy first and falls back to `policies/default.policy.yaml`.

## Emergency Bypass

Add one of these labels to a PR to skip gate evaluation:
- `emergency-bypass`
- `hotfix`

The agent still runs all collectors and posts findings as advisory comments (WARN verdict), but it will not block the merge. This is intended for urgent production fixes where speed is more important than a full review cycle.

## Supersession

When a new commit is pushed to a PR that already has an in-progress review, the agent supersedes all active reviews for that PR and starts fresh on the new HEAD. This prevents stale reviews from blocking merges and avoids wasting resources on outdated code.

## Available Make Commands

```
make lint       # Run ruff check with auto-fix + ruff format
make typecheck  # Run mypy in strict mode
make test       # Run pytest with coverage reporting
make check      # All of the above (lint + typecheck + test)
make serve      # Start uvicorn dev server on port 8000 with hot reload
make migrate    # Run Alembic database migrations (upgrade head)
```

## Admin Dashboard

### Access the Dashboard

After deployment, open your browser and navigate to `https://your-server.example.com`. If no users exist, register the first account — it automatically becomes the admin.

### Manage Users

1. Log in as admin
2. Go to **Users** in the sidebar
3. Click **Create User** to add team members
4. Set role: Admin (full access) or Viewer (scan viewing only)

### Change Runtime Settings

1. Go to **Settings** in the sidebar
2. Modify any operational setting (LLM model, token limits, collector mode, etc.)
3. Click **Save** — changes apply to new scans immediately
4. To revert: click **Reset** next to any setting

### Edit Gate Policies

1. Go to **Policies** in the sidebar
2. Click a policy name to open the YAML editor
3. Edit the policy and click **Save**
4. To create a per-repo override: click **Create Policy** and enter the repo name (e.g., `owner/repo`)

### Trigger a Baseline Scan from the Dashboard

1. Go to **Scans** in the sidebar
2. Click **Trigger Scan**
3. Enter the repository name and installation ID
4. The scan appears in the list with "pending" status

## Troubleshooting

**Webhook not received**
Check that your webhook URL is publicly accessible from the internet. Verify delivery status in the GitHub App settings: Settings > Developer Settings > your app > Advanced > Recent Deliveries. Failed deliveries show the HTTP status code and response body.

**401 Unauthorized on webhook**
The webhook secret in your `.env` (`AGENT_REVIEW_GITHUB_WEBHOOK_SECRET`) does not match the secret configured in your GitHub App. Regenerate and sync both.

**Pipeline stuck at COLLECTING**
A collector is timing out. Check `AGENT_REVIEW_SEMGREP_MODE` (set to `disabled` if you don't have a Semgrep token). Verify network access to the Semgrep and SonarQube APIs from your deployment environment.

**LLM errors or empty synthesis**
Verify that `OPENAI_API_KEY` (or your provider's key) is set in the environment. If the budget is too low, increase `AGENT_REVIEW_LLM_COST_BUDGET_PER_RUN_CENTS`. Check logs for litellm error messages.

**No review posted on the PR**
Confirm the GitHub App has **Checks** (Read & Write) and **Pull requests** (Read & Write) permissions. Verify the app is installed on the target repository. Check that the PR is not a draft and was not opened by a bot.

**Template directory not found**
If logs show `Template directory not found: .../prompts`, the `prompts/` directory is not visible from the working directory the app runs in. Set `AGENT_REVIEW_PROMPTS_DIR` to the absolute path of the `prompts/` directory inside the container (e.g. `/app/prompts`). In Docker, the default `./prompts` resolves relative to the `WORKDIR /app` so it should work out of the box. If you changed `WORKDIR`, update this setting accordingly.

**Viewing logs**
- Docker: `docker compose logs -f app`
- Local dev: logs print to the console. Set `AGENT_REVIEW_LOG_FORMAT=console` for human-readable output.

## Project Structure

```
src/agent_review/
├── app.py              # FastAPI application factory
├── config.py           # pydantic-settings configuration (all env vars)
├── database.py         # Async SQLAlchemy engine and session factory
├── models/             # ORM models (ReviewRun, Finding) and enums
├── schemas/            # Pydantic schemas (finding, decision, policy, webhook, etc.)
├── api/                # FastAPI routers: health, scan, and webhook endpoints
├── web/                # Web UI routes (Jinja2 SSR pages for scan results)
├── templates/          # HTML templates (base, scan list, scan detail)
├── reporting/          # Output formatters: JSON, Markdown, GitHub Issue
├── scm/                # GitHub App auth (JWT + installation tokens), REST client, projection
├── classifier/         # Deterministic file-pattern heuristic classifier
├── collectors/         # Evidence collectors: Semgrep, SonarQube, GitHub CI, Secrets
├── normalize/          # Findings normalizer and fingerprint-based deduplicator
├── reasoning/          # LLM client (litellm), Jinja2 prompt manager, synthesizer
├── gate/               # YAML policy loader and gate controller (verdict evaluation)
├── pipeline/           # Pipeline runner (orchestrates all stages) and supersession logic
├── observability/      # Structured logging (structlog) and per-run metrics
prompts/                # Jinja2 prompt templates (synthesize.j2, summarize.j2)
policies/               # YAML policy files (default + per-repo overrides)
tests/                  # Unit and integration tests (pytest, 165 tests)
```
