FROM python:3.12-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first (cached layer)
COPY pyproject.toml .
COPY uv.lock* .
RUN uv sync --frozen --no-dev --no-editable 2>/dev/null || uv sync --no-dev --no-editable

# Copy application source and assets
COPY src/ src/
COPY prompts/ prompts/
COPY policies/ policies/
COPY alembic/ alembic/
COPY alembic.ini .

# Re-sync with source present so the package is fully installed into .venv
RUN uv sync --frozen --no-dev --no-editable 2>/dev/null || uv sync --no-dev --no-editable

# Create non-root user and hand over ownership of the app directory
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["/app/.venv/bin/uvicorn", "agent_review.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
