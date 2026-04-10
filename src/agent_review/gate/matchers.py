from __future__ import annotations

from fnmatch import fnmatch


def matches_any_pattern(value: str, patterns: list[str]) -> bool:
    return any(fnmatch(value, pattern) for pattern in patterns)
