from __future__ import annotations

# pyright: reportMissingTypeStubs=false
import hashlib

from agent_review.normalize.fingerprint import FingerprintGenerator


class _TestableFingerprintGenerator(FingerprintGenerator):
    def normalize_snippet(self, snippet: str) -> str:
        return self._normalize_snippet(snippet)


def test_tc_fp_001_compute_with_snippet_normalizes_whitespace() -> None:
    generator = FingerprintGenerator()
    snippet_a = """
    def  run( ):
        return   value
    """
    snippet_b = "def run( ):\n    return value"

    fingerprint_a = generator.compute("R001", "src/app.py", snippet_a, 10)
    fingerprint_b = generator.compute("R001", "src/app.py", snippet_b, 10)

    assert fingerprint_a == fingerprint_b


def test_tc_fp_002_compute_with_snippet_strips_single_line_comments() -> None:
    generator = FingerprintGenerator()
    snippet_with_comments = """
    # module comment
    value = 1  // inline comment
    // full line comment
    result = value + 2
    """
    snippet_without_comments = """
    value = 1
    result = value + 2
    """

    fingerprint_with_comments = generator.compute("R002", "src/math.py", snippet_with_comments, 12)
    fingerprint_without_comments = generator.compute(
        "R002", "src/math.py", snippet_without_comments, 12
    )

    assert fingerprint_with_comments == fingerprint_without_comments


def test_tc_fp_003_compute_without_snippet_falls_back_to_line_based_fingerprint() -> None:
    generator = FingerprintGenerator()
    expected = hashlib.sha256(b"R003|src/main.py|77").hexdigest()

    fingerprint = generator.compute("R003", "src/main.py", "   ", 77)

    assert fingerprint == expected


def test_tc_fp_004_compute_is_deterministic_for_same_input() -> None:
    generator = FingerprintGenerator()

    first = generator.compute("R004", "src/a.py", "x = 1", 4)
    second = generator.compute("R004", "src/a.py", "x = 1", 4)

    assert first == second


def test_tc_fp_005_compute_differs_for_different_rule_ids() -> None:
    generator = FingerprintGenerator()

    fingerprint_a = generator.compute("R005-A", "src/shared.py", "x = y", 3)
    fingerprint_b = generator.compute("R005-B", "src/shared.py", "x = y", 3)

    assert fingerprint_a != fingerprint_b


def test_tc_fp_006_compute_differs_for_different_file_paths() -> None:
    generator = FingerprintGenerator()

    fingerprint_a = generator.compute("R006", "src/a.py", "total = amount", 8)
    fingerprint_b = generator.compute("R006", "src/b.py", "total = amount", 8)

    assert fingerprint_a != fingerprint_b


def test_tc_fp_007_normalize_snippet_collapses_multiple_spaces() -> None:
    generator = _TestableFingerprintGenerator()
    snippet = "value    =      one\t\t+    two"

    normalized = generator.normalize_snippet(snippet)

    assert normalized == "value = one + two"


def test_tc_fp_008_normalize_snippet_removes_blank_lines() -> None:
    generator = _TestableFingerprintGenerator()
    snippet = "\n\nfirst = 1\n\n\nsecond = 2\n\n"

    normalized = generator.normalize_snippet(snippet)

    assert normalized == "first = 1\nsecond = 2"


def test_tc_fp_009_normalize_snippet_preserves_case() -> None:
    generator = _TestableFingerprintGenerator()
    snippet = "Value = ComputeResult(Arg)"

    normalized = generator.normalize_snippet(snippet)

    assert normalized == "Value = ComputeResult(Arg)"


def test_tc_fp_010_backward_compat_empty_snippet_uses_v010_formula() -> None:
    generator = FingerprintGenerator()
    rule_id = "R010"
    file_path = "pkg/module.py"
    line = 101
    expected = hashlib.sha256(f"{rule_id}|{file_path}|{line}".encode()).hexdigest()

    fingerprint = generator.compute(rule_id, file_path, "", line)

    assert fingerprint == expected
