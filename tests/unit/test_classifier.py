from agent_review.classifier.classifier import Classifier


def test_security_only_files_high_risk_and_security_profile() -> None:
    classifier = Classifier()

    result = classifier.classify(
        changed_files=["src/auth/token_service.py", "src/security/crypto_utils.py"],
        pr_metadata={},
    )

    assert "core_quality" in result.profiles
    assert "security_sensitive" in result.profiles
    assert result.risk_level == "high"
    assert result.change_type == "security"


def test_docs_only_low_risk_core_quality_only() -> None:
    classifier = Classifier()

    result = classifier.classify(
        changed_files=["docs/architecture.md", "README.md"],
        pr_metadata={},
    )

    assert result.profiles == ["core_quality"]
    assert result.risk_level == "low"
    assert result.change_type == "docs"


def test_mixed_security_and_workflow_is_critical() -> None:
    classifier = Classifier()

    result = classifier.classify(
        changed_files=["src/auth/jwt_validator.py", ".github/workflows/ci.yml"],
        pr_metadata={},
    )

    assert result.risk_level == "critical"
    assert "core_quality" in result.profiles
    assert "security_sensitive" in result.profiles
    assert "workflow_security" in result.profiles


def test_workflow_files_add_workflow_security_profile() -> None:
    classifier = Classifier()

    result = classifier.classify(
        changed_files=["Dockerfile", "docker-compose.yml"],
        pr_metadata={},
    )

    assert "core_quality" in result.profiles
    assert "workflow_security" in result.profiles
    assert result.risk_level == "high"
    assert result.change_type == "config"


def test_empty_file_list_defaults_to_core_quality_and_low_risk() -> None:
    classifier = Classifier()

    result = classifier.classify(changed_files=[], pr_metadata={})

    assert result.profiles == ["core_quality"]
    assert result.risk_level == "low"
    assert result.change_type == "code"
    assert result.file_categories == {}


def test_change_type_derivations() -> None:
    classifier = Classifier()

    migration = classifier.classify(changed_files=["migrations/001_init.sql"], pr_metadata={})
    api = classifier.classify(changed_files=["src/api/routes/users.py"], pr_metadata={})
    tests = classifier.classify(changed_files=["tests/unit/test_x.py"], pr_metadata={})
    general = classifier.classify(changed_files=["src/core/engine.py"], pr_metadata={})

    assert migration.change_type == "config"
    assert api.change_type == "feature"
    assert tests.change_type == "test"
    assert general.change_type == "code"
