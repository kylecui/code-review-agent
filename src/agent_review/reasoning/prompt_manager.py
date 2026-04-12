from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, TemplateNotFound


class TemplateNotFoundError(Exception):
    pass


class PromptManager:
    def __init__(self, template_dir: Path | None = None):
        resolved_dir = template_dir or Path("./prompts")
        if not resolved_dir.exists() or not resolved_dir.is_dir():
            raise TemplateNotFoundError(f"Template directory not found: {resolved_dir}")
        self._environment = Environment(
            loader=FileSystemLoader(str(resolved_dir)),
            autoescape=True,
        )

    def render(self, template_name: str, **context: object) -> str:
        sanitized_context = self._sanitize_context(context)
        try:
            template = self._environment.get_template(template_name)
        except TemplateNotFound as exc:
            raise TemplateNotFoundError(f"Template not found: {template_name}") from exc
        return template.render(**sanitized_context)

    def _sanitize_context(self, context: dict[str, object]) -> dict[str, object]:
        sanitized: dict[str, object] = {}
        for key, value in context.items():
            sanitized[key] = self._sanitize_value(value)
        return sanitized

    def _sanitize_value(self, value: object) -> object:
        if isinstance(value, str):
            if len(value) > 100_000:
                return f"{value[:100_000]}[TRUNCATED]"
            return value
        if isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._sanitize_value(item) for key, item in value.items()}
        return value
