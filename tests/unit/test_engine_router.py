from __future__ import annotations

from agent_review.pipeline.engine_router import (
    EngineRouter,
    detect_languages,
)
from agent_review.schemas.policy import EngineTierConfig, ScanTrackConfig


def test_tc_er_001_incremental_java_selects_l1_only_for_language_specific() -> None:
    router = EngineRouter()

    selection = router.select(scan_track="incremental", detected_languages={"java"})

    assert selection.collectors == [
        "semgrep",
        "gitleaks",
        "secrets",
        "sonar",
        "github_ci",
        "spotbugs",
    ]
    assert "codeql" not in selection.collectors
    assert selection.tier_breakdown["L1"] == [
        "semgrep",
        "gitleaks",
        "secrets",
        "sonar",
        "github_ci",
    ]
    assert selection.tier_breakdown["L2"] == ["spotbugs"]
    assert selection.tier_breakdown["L3"] == []


def test_tc_er_002_baseline_java_selects_spotbugs_and_codeql() -> None:
    router = EngineRouter()

    selection = router.select(scan_track="baseline", detected_languages={"java"})

    assert selection.collectors == ["semgrep", "gitleaks", "secrets", "sonar", "spotbugs", "codeql"]
    assert selection.tier_breakdown["L1"] == ["semgrep", "gitleaks", "secrets", "sonar"]
    assert selection.tier_breakdown["L2"] == ["spotbugs"]
    assert selection.tier_breakdown["L3"] == ["codeql"]


def test_tc_er_003_incremental_jsts_includes_eslint_security() -> None:
    router = EngineRouter()

    selection = router.select(
        scan_track="incremental", detected_languages={"javascript", "typescript"}
    )

    assert "eslint_security" in selection.collectors
    assert selection.tier_breakdown["L2"] == ["eslint_security"]
    assert "codeql" not in selection.collectors


def test_tc_er_004_baseline_go_includes_golangci_lint() -> None:
    router = EngineRouter()

    selection = router.select(scan_track="baseline", detected_languages={"go"})

    assert "golangci_lint" in selection.collectors
    assert selection.tier_breakdown["L2"] == ["golangci_lint"]
    assert "codeql" in selection.collectors


def test_tc_er_005_baseline_c_includes_cppcheck() -> None:
    router = EngineRouter()

    selection = router.select(scan_track="baseline", detected_languages={"c"})

    assert "cppcheck" in selection.collectors
    assert selection.tier_breakdown["L2"] == ["cppcheck"]


def test_tc_er_006_baseline_csharp_includes_roslyn() -> None:
    router = EngineRouter()

    selection = router.select(scan_track="baseline", detected_languages={"csharp"})

    assert "roslyn" in selection.collectors
    assert selection.tier_breakdown["L2"] == ["roslyn"]


def test_tc_er_007_baseline_lua_includes_luacheck_excludes_codeql() -> None:
    router = EngineRouter()

    selection = router.select(scan_track="baseline", detected_languages={"lua"})

    assert "luacheck" in selection.collectors
    assert "codeql" not in selection.collectors
    assert selection.tier_breakdown["L3"] == []


def test_tc_er_008_empty_language_set_selects_only_l1_per_track() -> None:
    router = EngineRouter()

    incremental = router.select(scan_track="incremental", detected_languages=set())
    baseline = router.select(scan_track="baseline", detected_languages=set())

    assert incremental.collectors == ["semgrep", "gitleaks", "secrets", "sonar", "github_ci"]
    assert incremental.tier_breakdown["L2"] == []
    assert incremental.tier_breakdown["L3"] == []
    assert baseline.collectors == ["semgrep", "gitleaks", "secrets", "sonar"]
    assert baseline.tier_breakdown["L2"] == []
    assert baseline.tier_breakdown["L3"] == []


def test_tc_er_009_policy_disables_l3_for_baseline() -> None:
    router = EngineRouter()
    engine_tiers = ScanTrackConfig(
        baseline=EngineTierConfig(l1_enabled=True, l2_enabled=True, l3_enabled=False)
    )

    selection = router.select(
        scan_track="baseline", detected_languages={"java"}, engine_tiers=engine_tiers
    )

    assert "spotbugs" in selection.collectors
    assert "codeql" not in selection.collectors
    assert selection.tier_breakdown["L3"] == []


def test_tc_er_010_policy_disables_l2() -> None:
    router = EngineRouter()
    engine_tiers = ScanTrackConfig(
        incremental=EngineTierConfig(l1_enabled=True, l2_enabled=False, l3_enabled=False),
        baseline=EngineTierConfig(l1_enabled=True, l2_enabled=False, l3_enabled=True),
    )

    incremental = router.select(
        scan_track="incremental", detected_languages={"java"}, engine_tiers=engine_tiers
    )
    baseline = router.select(
        scan_track="baseline", detected_languages={"java"}, engine_tiers=engine_tiers
    )

    assert incremental.collectors == ["semgrep", "gitleaks", "secrets", "sonar", "github_ci"]
    assert incremental.tier_breakdown["L2"] == []
    assert baseline.collectors == ["semgrep", "gitleaks", "secrets", "sonar", "codeql"]
    assert baseline.tier_breakdown["L2"] == []


def test_tc_er_011_mixed_languages_selects_all_corresponding_l2_collectors() -> None:
    router = EngineRouter()

    selection = router.select(
        scan_track="baseline", detected_languages={"java", "javascript", "go"}
    )

    assert "spotbugs" in selection.collectors
    assert "eslint_security" in selection.collectors
    assert "golangci_lint" in selection.collectors
    assert set(selection.tier_breakdown["L2"]) == {"spotbugs", "eslint_security", "golangci_lint"}
    assert len(selection.tier_breakdown["L2"]) == 3


def test_tc_er_012_detect_languages_maps_extensions_across_supported_languages() -> None:
    file_paths = [
        "src/Main.java",
        "web/page.jsp",
        "service/main.go",
        "tool/script.py",
        "native/a.c",
        "native/include/a.h",
        "native/a.cpp",
        "native/b.cc",
        "native/c.cxx",
        "dotnet/App.cs",
        "ui/main.js",
        "ui/component.jsx",
        "ui/module.mjs",
        "ui/bundle.cjs",
        "ui/main.ts",
        "ui/component.tsx",
        "ui/module.mts",
        "ui/bundle.cts",
        "game/mod.lua",
        "app/main.rb",
        "app/index.php",
        "sys/lib.rs",
        "mobile/Main.kt",
        "mobile/build.kts",
        "apple/App.swift",
    ]

    detected = detect_languages(file_paths)

    assert detected == {
        "java",
        "go",
        "python",
        "c",
        "cpp",
        "csharp",
        "javascript",
        "typescript",
        "lua",
        "ruby",
        "php",
        "rust",
        "kotlin",
        "swift",
    }


def test_tc_er_013_detect_languages_unknown_extension_returns_empty_set() -> None:
    file_paths = ["README.md", "config.toml", "assets/logo.png", "notes.txt"]

    detected = detect_languages(file_paths)

    assert detected == set()


def test_tc_er_014_detect_languages_mixed_known_unknown_returns_known_only() -> None:
    file_paths = ["src/main.py", "README.md", "frontend/app.tsx", "misc/file.unknown"]

    detected = detect_languages(file_paths)

    assert detected == {"python", "typescript"}
