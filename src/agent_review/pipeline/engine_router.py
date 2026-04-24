from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from agent_review.schemas.policy import ScanTrackConfig

# Language detection
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".java": "java",
    ".jsp": "java",
    ".go": "go",
    ".py": "python",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".cs": "csharp",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".lua": "lua",
    ".rb": "ruby",
    ".php": "php",
    ".rs": "rust",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
}


def detect_languages(file_paths: list[str]) -> set[str]:
    """Detect programming languages from file extensions."""
    languages: set[str] = set()
    for path in file_paths:
        suffix = Path(path).suffix.lower()
        lang = EXTENSION_TO_LANGUAGE.get(suffix)
        if lang:
            languages.add(lang)
    return languages


@dataclass(slots=True)
class EngineSelection:
    """Which engines to run for a given scan."""

    collectors: list[str]
    tier_breakdown: dict[str, list[str]]
    rationale: str


class EngineRouter:
    """Select engines based on scan track, detected languages, and policy."""

    # Universal collectors always run (regardless of language)
    UNIVERSAL_COLLECTORS: ClassVar[list[str]] = ["semgrep", "gitleaks", "secrets"]

    # Additional collectors for incremental (PR) scans
    INCREMENTAL_EXTRAS: ClassVar[list[str]] = ["sonar", "github_ci"]

    # Additional collectors for baseline (full) scans
    BASELINE_EXTRAS: ClassVar[list[str]] = ["sonar"]

    # Language → L2 collector mapping
    LANGUAGE_TO_L2: ClassVar[dict[str, list[str]]] = {
        "java": ["spotbugs"],
        "go": ["golangci_lint"],
        "c": ["cppcheck"],
        "cpp": ["cppcheck"],
        "csharp": ["roslyn"],
        "javascript": ["eslint_security"],
        "typescript": ["eslint_security"],
        "lua": ["luacheck"],
    }

    # L3 collectors (heavy, baseline-only by default)
    L3_COLLECTORS: ClassVar[list[str]] = ["codeql"]

    # Languages supported by CodeQL
    CODEQL_LANGUAGES: ClassVar[set[str]] = {
        "java",
        "go",
        "python",
        "c",
        "cpp",
        "csharp",
        "javascript",
        "typescript",
        "ruby",
    }

    def select(
        self,
        scan_track: Literal["incremental", "baseline"],
        detected_languages: set[str],
        engine_tiers: ScanTrackConfig | None = None,
    ) -> EngineSelection:
        """Determine which engines to run."""
        if engine_tiers is None:
            engine_tiers = ScanTrackConfig()

        tier_config = (
            engine_tiers.incremental if scan_track == "incremental" else engine_tiers.baseline
        )

        l1: list[str] = []
        l2: list[str] = []
        l3: list[str] = []

        # L1: universal + track extras
        if tier_config.l1_enabled:
            l1.extend(self.UNIVERSAL_COLLECTORS)
            if scan_track == "incremental":
                l1.extend(self.INCREMENTAL_EXTRAS)
            else:
                l1.extend(self.BASELINE_EXTRAS)

        # L2: language-specific
        if tier_config.l2_enabled:
            seen: set[str] = set()
            for lang in detected_languages:
                for collector in self.LANGUAGE_TO_L2.get(lang, []):
                    if collector not in seen:
                        l2.append(collector)
                        seen.add(collector)
            # ESLint is fast enough to include in incremental
            # (already handled by LANGUAGE_TO_L2)

        # L3: heavy analysis (baseline only by default)
        if tier_config.l3_enabled and detected_languages & self.CODEQL_LANGUAGES:
            # Only include CodeQL if detected languages are supported
            l3.extend(self.L3_COLLECTORS)

        all_collectors = l1 + l2 + l3
        # Deduplicate preserving order
        seen_final: set[str] = set()
        unique: list[str] = []
        for collector in all_collectors:
            if collector not in seen_final:
                unique.append(collector)
                seen_final.add(collector)

        rationale_parts: list[str] = []
        rationale_parts.append(f"track={scan_track}")
        rationale_parts.append(f"languages={sorted(detected_languages)}")
        rationale_parts.append(f"L1={'on' if tier_config.l1_enabled else 'off'}")
        rationale_parts.append(f"L2={'on' if tier_config.l2_enabled else 'off'}")
        rationale_parts.append(f"L3={'on' if tier_config.l3_enabled else 'off'}")

        return EngineSelection(
            collectors=unique,
            tier_breakdown={"L1": l1, "L2": l2, "L3": l3},
            rationale=", ".join(rationale_parts),
        )
