from __future__ import annotations

import hashlib
import re


class FingerprintGenerator:
    """Generate refactor-resilient fingerprints for findings."""

    def compute(self, rule_id: str, file_path: str, snippet: str, line: int) -> str:
        """
        Compute fingerprint with AST normalization.

        Strategy (cascading fallback):
        1. If snippet is non-empty: normalize it, then hash "rule_id|file_path|normalized_snippet"
        2. Fallback (empty snippet): hash "rule_id|file_path|line" (v0.1.0 compat)
        """
        if snippet.strip():
            canonical = f"{rule_id}|{file_path}|{self._normalize_snippet(snippet)}"
        else:
            canonical = f"{rule_id}|{file_path}|{line}"
        return self._hash(canonical)

    def _normalize_snippet(self, snippet: str) -> str:
        """
        Normalize code snippet for fingerprinting:
        - Strip leading/trailing whitespace per line
        - Collapse internal whitespace runs to single space
        - Remove single-line comments (// and #)
        - Remove blank lines
        - Do NOT lowercase (preserve case to avoid false merges)
        """
        normalized_lines: list[str] = []

        for raw_line in snippet.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped.startswith("//") or stripped.startswith("#"):
                continue

            without_inline_comment = stripped.split("//", 1)[0].strip()
            if not without_inline_comment:
                continue

            collapsed = re.sub(r"\s+", " ", without_inline_comment)
            normalized_lines.append(collapsed)

        return "\n".join(normalized_lines)

    def _hash(self, canonical: str) -> str:
        """Compute SHA-256 hex digest."""
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
