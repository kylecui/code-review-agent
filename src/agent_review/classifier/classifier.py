import re
from collections import Counter
from pathlib import Path

from agent_review.schemas.classification import Classification

_PATTERN_FLAGS = re.IGNORECASE

SECURITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"auth", _PATTERN_FLAGS),
    re.compile(r"crypto", _PATTERN_FLAGS),
    re.compile(r"secret", _PATTERN_FLAGS),
    re.compile(r"token", _PATTERN_FLAGS),
    re.compile(r"permission", _PATTERN_FLAGS),
    re.compile(r"acl", _PATTERN_FLAGS),
    re.compile(r"rbac", _PATTERN_FLAGS),
    re.compile(r"oauth", _PATTERN_FLAGS),
    re.compile(r"jwt", _PATTERN_FLAGS),
    re.compile(r"password", _PATTERN_FLAGS),
    re.compile(r"credential", _PATTERN_FLAGS),
    re.compile(r"key", _PATTERN_FLAGS),
    re.compile(r"cert", _PATTERN_FLAGS),
    re.compile(r"ssl", _PATTERN_FLAGS),
    re.compile(r"tls", _PATTERN_FLAGS),
    re.compile(r"pgp", _PATTERN_FLAGS),
    re.compile(r"encrypt", _PATTERN_FLAGS),
    re.compile(r"decrypt", _PATTERN_FLAGS),
    re.compile(r"hash", _PATTERN_FLAGS),
    re.compile(r"sign", _PATTERN_FLAGS),
    re.compile(r"verify", _PATTERN_FLAGS),
)

WORKFLOW_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.github/workflows/", _PATTERN_FLAGS),
    re.compile(r"Dockerfile$", _PATTERN_FLAGS),
    re.compile(r"docker-compose", _PATTERN_FLAGS),
    re.compile(r"Jenkinsfile$", _PATTERN_FLAGS),
    re.compile(r"\.gitlab-ci", _PATTERN_FLAGS),
    re.compile(r"\.circleci", _PATTERN_FLAGS),
)

MIGRATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"migrations/", _PATTERN_FLAGS),
    re.compile(r"alembic/", _PATTERN_FLAGS),
    re.compile(r"\.sql$", _PATTERN_FLAGS),
    re.compile(r"schema", _PATTERN_FLAGS),
    re.compile(r"flyway", _PATTERN_FLAGS),
)

API_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"routes/", _PATTERN_FLAGS),
    re.compile(r"api/", _PATTERN_FLAGS),
    re.compile(r"handlers/", _PATTERN_FLAGS),
    re.compile(r"endpoints/", _PATTERN_FLAGS),
    re.compile(r"views/", _PATTERN_FLAGS),
    re.compile(r"controllers/", _PATTERN_FLAGS),
)

DOCS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\.md$", _PATTERN_FLAGS),
    re.compile(r"docs/", _PATTERN_FLAGS),
    re.compile(r"README", _PATTERN_FLAGS),
    re.compile(r"CHANGELOG", _PATTERN_FLAGS),
    re.compile(r"LICENSE", _PATTERN_FLAGS),
    re.compile(r"\.rst$", _PATTERN_FLAGS),
    re.compile(r"docs/.+\.txt$", _PATTERN_FLAGS),
)

TEST_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"tests/", _PATTERN_FLAGS),
    re.compile(r"_test\.", _PATTERN_FLAGS),
    re.compile(r"test_", _PATTERN_FLAGS),
    re.compile(r"_spec\.", _PATTERN_FLAGS),
    re.compile(r"spec_", _PATTERN_FLAGS),
    re.compile(r"__tests__/", _PATTERN_FLAGS),
    re.compile(r"conftest\.", _PATTERN_FLAGS),
)

CATEGORY_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "security": SECURITY_PATTERNS,
    "workflow": WORKFLOW_PATTERNS,
    "migration": MIGRATION_PATTERNS,
    "api": API_PATTERNS,
    "docs": DOCS_PATTERNS,
    "test": TEST_PATTERNS,
}

CHANGE_TYPE_MAP: dict[str, str] = {
    "security": "security",
    "workflow": "config",
    "migration": "config",
    "api": "feature",
    "docs": "docs",
    "test": "test",
    "general": "code",
}

DOMAINS_MAP: dict[str, str] = {
    "security": "security",
    "workflow": "devops",
    "migration": "data",
    "api": "api",
    "docs": "documentation",
    "test": "testing",
}

DOMINANCE_ORDER: tuple[str, ...] = (
    "security",
    "workflow",
    "migration",
    "api",
    "docs",
    "test",
    "general",
)


class Classifier:
    def classify(self, changed_files: list[str], pr_metadata: dict[str, object]) -> Classification:
        _ = pr_metadata
        file_categories: dict[str, list[str]] = {}
        category_counts: Counter[str] = Counter()

        for file_path in changed_files:
            matched_categories: list[str] = []
            for category, patterns in CATEGORY_PATTERNS.items():
                if any(pattern.search(file_path) for pattern in patterns):
                    matched_categories.append(category)

            if not matched_categories:
                matched_categories.append("general")

            for category in matched_categories:
                file_categories.setdefault(category, []).append(file_path)
                category_counts[category] += 1

        dominant_category = self._dominant_category(category_counts)
        categories_hit = set(file_categories)

        has_security = "security" in categories_hit
        has_workflow = "workflow" in categories_hit
        has_migration = "migration" in categories_hit
        has_api = "api" in categories_hit

        if has_security and has_workflow:
            risk_level = "critical"
        elif has_security or has_workflow:
            risk_level = "high"
        elif has_migration or has_api:
            risk_level = "medium"
        else:
            risk_level = "low"

        domains = sorted(
            DOMAINS_MAP[category] for category in categories_hit if category in DOMAINS_MAP
        )

        profiles = ["core_quality"]
        if has_security:
            profiles.append("security_sensitive")
        if has_workflow:
            profiles.append("workflow_security")

        detected_languages = self._detect_languages(changed_files)

        return Classification(
            change_type=CHANGE_TYPE_MAP[dominant_category],
            domains=domains,
            risk_level=risk_level,
            profiles=profiles,
            file_categories=file_categories,
            detected_languages=detected_languages,
        )

    @staticmethod
    def _dominant_category(category_counts: Counter[str]) -> str:
        if not category_counts:
            return "general"

        max_count = max(category_counts.values())
        for category in DOMINANCE_ORDER:
            if category_counts.get(category, 0) == max_count:
                return category
        return "general"

    @staticmethod
    def _detect_languages(changed_files: list[str]) -> list[str]:
        from agent_review.pipeline.engine_router import EXTENSION_TO_LANGUAGE

        languages: set[str] = set()
        for file_path in changed_files:
            suffix = Path(file_path).suffix.lower()
            lang = EXTENSION_TO_LANGUAGE.get(suffix)
            if lang:
                languages.add(lang)
        return sorted(languages)
