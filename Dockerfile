FROM python:3.12-slim AS base

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY uv.lock* .

RUN uv sync --frozen --no-dev --no-editable 2>/dev/null || uv sync --no-dev

COPY src/ src/
COPY prompts/ prompts/
COPY policies/ policies/
COPY alembic/ alembic/
COPY alembic.ini .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "agent_review.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
