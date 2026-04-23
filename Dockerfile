# Stage 1: Build frontend
FROM node:22-slim AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# Stage 2: Python application
FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git curl cppcheck lua5.3 luarocks && rm -rf /var/lib/apt/lists/*

# Optional tools: spotbugs, golangci-lint, roslyn, codeql, eslint
RUN curl -sSfL https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_8.21.2_linux_x64.tar.gz | tar -xz -C /usr/local/bin gitleaks

RUN luarocks install luacheck

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY uv.lock* .
RUN uv sync --frozen --no-dev --no-editable 2>/dev/null || uv sync --no-dev --no-editable

RUN git clone --depth 1 https://github.com/semgrep/semgrep-rules /opt/semgrep-rules

COPY src/ src/
COPY prompts/ prompts/
COPY policies/ policies/
COPY alembic/ alembic/
COPY alembic.ini .

RUN uv sync --frozen --no-dev --no-editable 2>/dev/null || uv sync --no-dev --no-editable

RUN uv pip install --no-cache-dir semgrep

COPY --from=frontend-build /app/frontend/dist /app/static

RUN useradd --create-home appuser && chown -R appuser:appuser /app

USER appuser

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "agent_review.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
