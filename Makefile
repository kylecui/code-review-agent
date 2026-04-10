.PHONY: lint typecheck test check serve migrate

lint:
	uv run ruff check src/ tests/ --fix
	uv run ruff format src/ tests/

typecheck:
	uv run mypy src/

test:
	uv run pytest --cov=agent_review --cov-report=term-missing -x

check: lint typecheck test

serve:
	uv run uvicorn agent_review.app:create_app --factory --reload --port 8000

migrate:
	uv run alembic upgrade head
