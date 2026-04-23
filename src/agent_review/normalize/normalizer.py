from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from agent_review.models.enums import FindingConfidence, FindingSeverity
from agent_review.schemas.finding import FindingCreate

if TYPE_CHECKING:
    from agent_review.collectors.base import CollectorResult

_SEMGREP_SEVERITY_MAP: dict[str, FindingSeverity] = {
    "CRITICAL": FindingSeverity.CRITICAL,
    "ERROR": FindingSeverity.HIGH,
    "WARNING": FindingSeverity.MEDIUM,
    "INFO": FindingSeverity.LOW,
    "INVENTORY": FindingSeverity.INFO,
    "EXPERIMENT": FindingSeverity.INFO,
}

_SONAR_SEVERITY_MAP: dict[str, FindingSeverity] = {
    "BLOCKER": FindingSeverity.CRITICAL,
    "CRITICAL": FindingSeverity.HIGH,
    "MAJOR": FindingSeverity.MEDIUM,
    "MINOR": FindingSeverity.LOW,
    "INFO": FindingSeverity.INFO,
}

_GITHUB_CI_SEVERITY_MAP: dict[str, FindingSeverity] = {
    "failure": FindingSeverity.HIGH,
    "warning": FindingSeverity.MEDIUM,
    "notice": FindingSeverity.LOW,
}

# SARIF-based collectors share a common severity map (SARIF level → internal)
_SARIF_SEVERITY_MAP: dict[str, FindingSeverity] = {
    "ERROR": FindingSeverity.HIGH,
    "WARNING": FindingSeverity.MEDIUM,
    "INFO": FindingSeverity.LOW,
}

# ESLint severity integers: 2=error, 1=warning
_ESLINT_SEVERITY_MAP: dict[int, FindingSeverity] = {
    2: FindingSeverity.MEDIUM,  # promoted to HIGH for security/* rules
    1: FindingSeverity.LOW,
}

# Luacheck code-prefix → severity
_LUACHECK_SEVERITY_MAP: dict[str, FindingSeverity] = {
    "E0": FindingSeverity.HIGH,
    "W0": FindingSeverity.MEDIUM,
    "W1": FindingSeverity.LOW,
    "W2": FindingSeverity.MEDIUM,
    "W3": FindingSeverity.INFO,
    "W4": FindingSeverity.LOW,
    "W5": FindingSeverity.LOW,
    "W6": FindingSeverity.INFO,
}


class FindingsNormalizer:
    def normalize(self, results: list[CollectorResult]) -> list[FindingCreate]:
        findings: list[FindingCreate] = []
        for result in results:
            if result.status != "success" or result.error is not None:
                continue

            if result.collector_name == "semgrep":
                findings.extend(self._normalize_semgrep(result))
            elif result.collector_name == "sonar":
                findings.extend(self._normalize_sonar(result))
            elif result.collector_name == "github_ci":
                findings.extend(self._normalize_github_ci(result))
            elif result.collector_name == "secrets":
                findings.extend(self._normalize_secrets(result))
            elif result.collector_name == "gitleaks":
                findings.extend(self._normalize_gitleaks(result))
            elif result.collector_name == "spotbugs":
                findings.extend(self._normalize_spotbugs(result))
            elif result.collector_name == "golangci_lint":
                findings.extend(self._normalize_golangci_lint(result))
            elif result.collector_name == "cppcheck":
                findings.extend(self._normalize_cppcheck(result))
            elif result.collector_name == "eslint_security":
                findings.extend(self._normalize_eslint_security(result))
            elif result.collector_name == "roslyn":
                findings.extend(self._normalize_roslyn(result))
            elif result.collector_name == "luacheck":
                findings.extend(self._normalize_luacheck(result))
        return findings

    def _normalize_semgrep(self, result: CollectorResult) -> list[FindingCreate]:
        findings: list[FindingCreate] = []
        for raw in result.raw_findings:
            rule_id = self._as_str(raw.get("rule_id"), default="unknown-rule")
            path = self._as_str(raw.get("path"), default="unknown-file")
            line = self._as_int(raw.get("line"), default=1)
            end_line_val = raw.get("end_line")
            end_line = self._as_int(end_line_val, default=line) if end_line_val else None
            severity = _SEMGREP_SEVERITY_MAP.get(
                self._as_str(raw.get("severity")).upper(), FindingSeverity.MEDIUM
            )
            message = self._as_str(raw.get("message"), default="Semgrep finding")

            raw_confidence = self._as_str(raw.get("confidence")).upper()
            confidence = (
                FindingConfidence.HIGH
                if raw_confidence == "HIGH"
                else FindingConfidence.MEDIUM
                if raw_confidence == "MEDIUM"
                else FindingConfidence.LOW
                if raw_confidence == "LOW"
                else FindingConfidence.HIGH
            )

            raw_category = self._as_str(raw.get("category"))
            category = (
                self._semgrep_category_from_metadata(raw_category)
                if raw_category
                else self._semgrep_category(rule_id)
            )

            finding_id = f"semgrep:{rule_id}:{path}:{line}"
            fingerprint = self._fingerprint(f"semgrep|{rule_id}|{path}|{line}")

            evidence = [message]
            snippet = self._as_str(raw.get("snippet"))
            if snippet:
                evidence.append(snippet)
            cwe = raw.get("cwe")
            cwe_tag = ""
            if isinstance(cwe, list) and cwe:
                evidence.append("CWE: " + ", ".join(str(c) for c in cwe))
                cwe_tag = " (" + ", ".join(str(c) for c in cwe) + ")"

            impact = self._derive_semgrep_impact(category, rule_id, cwe_tag)

            findings.append(
                FindingCreate(
                    finding_id=finding_id,
                    category=category,
                    severity=severity,
                    confidence=confidence,
                    blocking=self._is_blocking(severity),
                    file_path=path,
                    line_start=line,
                    line_end=end_line,
                    source_tools=[result.collector_name],
                    rule_id=rule_id,
                    title=f"Semgrep: {rule_id}",
                    evidence=evidence,
                    impact=impact,
                    fix_recommendation=message,
                    fingerprint=fingerprint,
                )
            )
        return findings

    def _normalize_sonar(self, result: CollectorResult) -> list[FindingCreate]:
        findings: list[FindingCreate] = []
        for raw in result.raw_findings:
            key = self._as_str(raw.get("key"), default="unknown-key")
            rule = self._as_str(raw.get("rule"), default="unknown-rule")
            component = self._as_str(raw.get("component"), default="unknown-file")
            line = self._as_int(raw.get("line"), default=1)
            severity = _SONAR_SEVERITY_MAP.get(
                self._as_str(raw.get("severity")).upper(), FindingSeverity.MEDIUM
            )
            issue_type = self._as_str(raw.get("type")).upper()
            message = self._as_str(raw.get("message"), default="Sonar finding")

            finding_id = f"sonar:{key}"
            fingerprint = self._fingerprint(f"sonar|{rule}|{component}|{line}")

            sonar_category = self._sonar_category(issue_type)
            impact = self._derive_sonar_impact(sonar_category, rule)

            findings.append(
                FindingCreate(
                    finding_id=finding_id,
                    category=sonar_category,
                    severity=severity,
                    confidence=FindingConfidence.MEDIUM,
                    blocking=self._is_blocking(severity),
                    file_path=component,
                    line_start=line,
                    line_end=None,
                    source_tools=[result.collector_name],
                    rule_id=rule,
                    title=f"Sonar: {rule}",
                    evidence=[message],
                    impact=impact,
                    fix_recommendation=message,
                    fingerprint=fingerprint,
                )
            )
        return findings

    def _normalize_github_ci(self, result: CollectorResult) -> list[FindingCreate]:
        findings: list[FindingCreate] = []
        for raw in result.raw_findings:
            check_name = self._as_str(raw.get("check_name"), default="unknown-check")
            status = self._as_str(raw.get("status")).lower()
            path = self._as_str(raw.get("path"), default="unknown-file")
            start_line = self._as_int(raw.get("start_line"), default=1)
            end_line_value = self._as_int(raw.get("end_line"), default=start_line)
            annotation_level = self._as_str(raw.get("annotation_level")).lower()
            message = self._as_str(raw.get("message"), default="CI annotation")
            title = self._as_str(raw.get("title"), default=f"{check_name} annotation")

            severity = _GITHUB_CI_SEVERITY_MAP.get(annotation_level)
            if severity is None:
                severity = _GITHUB_CI_SEVERITY_MAP.get(status, FindingSeverity.MEDIUM)

            finding_id = f"github_ci:{check_name}:{path}:{start_line}:{end_line_value}:{title}"
            fingerprint = self._fingerprint(
                f"github_ci|{check_name}|{path}|{start_line}|{end_line_value}|{title}"
            )

            ci_impact = f"CI check '{check_name}' reported a {annotation_level}-level issue."

            findings.append(
                FindingCreate(
                    finding_id=finding_id,
                    category="quality.ci-annotation",
                    severity=severity,
                    confidence=FindingConfidence.LOW,
                    blocking=self._is_blocking(severity),
                    file_path=path,
                    line_start=start_line,
                    line_end=end_line_value,
                    source_tools=[result.collector_name],
                    rule_id=check_name,
                    title=title,
                    evidence=[message],
                    impact=ci_impact,
                    fix_recommendation=message,
                    fingerprint=fingerprint,
                )
            )
        return findings

    def _normalize_secrets(self, result: CollectorResult) -> list[FindingCreate]:
        findings: list[FindingCreate] = []
        for raw in result.raw_findings:
            number = self._as_int(raw.get("number"), default=0)
            state = self._as_str(raw.get("state"), default="open")
            secret_type = self._as_str(raw.get("secret_type"), default="secret")
            html_url = self._as_str(raw.get("html_url"), default="")
            created_at = self._as_str(raw.get("created_at"), default="")

            finding_id = f"secrets:{number}"
            fingerprint = self._fingerprint(f"secrets|{number}|{secret_type}|{state}")

            evidence = [f"{secret_type} secret scanning alert"]
            if html_url:
                evidence.append(html_url)
            if created_at:
                evidence.append(f"created_at={created_at}")

            findings.append(
                FindingCreate(
                    finding_id=finding_id,
                    category="security.secret-detection",
                    severity=FindingSeverity.CRITICAL,
                    confidence=FindingConfidence.HIGH,
                    blocking=True,
                    file_path="repository",
                    line_start=1,
                    line_end=None,
                    source_tools=[result.collector_name],
                    rule_id=secret_type,
                    title=f"Secret detected: {secret_type}",
                    evidence=evidence,
                    impact=(
                        "Exposed credentials can result in unauthorized access and "
                        "immediate compromise."
                    ),
                    fix_recommendation=(
                        "Rotate the exposed secret immediately and remove it from version history."
                    ),
                    fingerprint=fingerprint,
                )
            )
        return findings

    def _normalize_sarif_based(
        self,
        result: CollectorResult,
        tool_label: str,
        default_category: str,
    ) -> list[FindingCreate]:
        findings: list[FindingCreate] = []
        for raw in result.raw_findings:
            rule_id = self._as_str(raw.get("rule_id"), default="unknown-rule")
            path = self._as_str(raw.get("path"), default="unknown-file")
            line = self._as_int(raw.get("line"), default=1)
            end_line_val = raw.get("end_line")
            end_line = self._as_int(end_line_val, default=line) if end_line_val else None
            severity = _SARIF_SEVERITY_MAP.get(
                self._as_str(raw.get("severity")).upper(), FindingSeverity.MEDIUM
            )
            message = self._as_str(raw.get("message"), default=f"{tool_label} finding")
            snippet = self._as_str(raw.get("snippet"))
            precision = self._as_str(raw.get("precision")).lower()

            raw_category = self._as_str(raw.get("category")).lower()
            if raw_category in ("security", "security.sast"):
                category = "security.sast"
            elif raw_category and raw_category != "unknown":
                category = f"quality.{raw_category}"
            else:
                category = default_category

            cwe = raw.get("cwe")
            cwe_tag = ""
            evidence = [message]
            if snippet:
                evidence.append(snippet)
            if isinstance(cwe, list) and cwe:
                evidence.append("CWE: " + ", ".join(str(c) for c in cwe))
                cwe_tag = " (" + ", ".join(str(c) for c in cwe) + ")"

            confidence = (
                FindingConfidence.HIGH
                if precision == "high"
                else FindingConfidence.MEDIUM
                if precision == "medium"
                else FindingConfidence.LOW
            )

            finding_id = f"{result.collector_name}:{rule_id}:{path}:{line}"
            fingerprint = self._fingerprint(f"{result.collector_name}|{rule_id}|{path}|{line}")

            if category.startswith("security"):
                impact = f"Security issue detected by {tool_label} rule '{rule_id}'{cwe_tag}."
            else:
                impact = f"Code quality issue detected by {tool_label} rule '{rule_id}'."

            findings.append(
                FindingCreate(
                    finding_id=finding_id,
                    category=category,
                    severity=severity,
                    confidence=confidence,
                    blocking=self._is_blocking(severity),
                    file_path=path,
                    line_start=line,
                    line_end=end_line,
                    source_tools=[result.collector_name],
                    rule_id=rule_id,
                    title=f"{tool_label}: {rule_id}",
                    evidence=evidence,
                    impact=impact,
                    fix_recommendation=message,
                    fingerprint=fingerprint,
                )
            )
        return findings

    def _normalize_gitleaks(self, result: CollectorResult) -> list[FindingCreate]:
        findings: list[FindingCreate] = []
        for raw in result.raw_findings:
            rule_id = self._as_str(raw.get("rule_id"), default="unknown-secret")
            path = self._as_str(raw.get("path"), default="unknown-file")
            line = self._as_int(raw.get("line"), default=1)
            end_line_val = raw.get("end_line")
            end_line = self._as_int(end_line_val, default=line) if end_line_val else None
            message = self._as_str(raw.get("message"), default="Secret detected by Gitleaks")
            snippet = self._as_str(raw.get("snippet"))

            severity = _SARIF_SEVERITY_MAP.get(
                self._as_str(raw.get("severity")).upper(), FindingSeverity.HIGH
            )

            finding_id = f"gitleaks:{rule_id}:{path}:{line}"
            fingerprint = self._fingerprint(f"gitleaks|{rule_id}|{path}|{line}")

            evidence = [message]
            if snippet:
                evidence.append(snippet)

            findings.append(
                FindingCreate(
                    finding_id=finding_id,
                    category="security.secret-detection",
                    severity=severity,
                    confidence=FindingConfidence.HIGH,
                    blocking=self._is_blocking(severity),
                    file_path=path,
                    line_start=line,
                    line_end=end_line,
                    source_tools=[result.collector_name],
                    rule_id=rule_id,
                    title=f"Gitleaks: {rule_id}",
                    evidence=evidence,
                    impact="Hardcoded secret detected. Exposed credentials can lead to "
                    "unauthorized access.",
                    fix_recommendation="Remove the secret from source code and rotate "
                    "the credential immediately.",
                    fingerprint=fingerprint,
                )
            )
        return findings

    def _normalize_spotbugs(self, result: CollectorResult) -> list[FindingCreate]:
        return self._normalize_sarif_based(result, "SpotBugs", "quality.static-analysis")

    def _normalize_golangci_lint(self, result: CollectorResult) -> list[FindingCreate]:
        return self._normalize_sarif_based(result, "golangci-lint", "quality.static-analysis")

    def _normalize_cppcheck(self, result: CollectorResult) -> list[FindingCreate]:
        return self._normalize_sarif_based(result, "Cppcheck", "quality.static-analysis")

    def _normalize_eslint_security(self, result: CollectorResult) -> list[FindingCreate]:
        findings: list[FindingCreate] = []
        for raw in result.raw_findings:
            rule_id = self._as_str(raw.get("rule_id"), default="unknown-rule")
            path = self._as_str(raw.get("path"), default="unknown-file")
            line = self._as_int(raw.get("line"), default=1)
            end_line_val = raw.get("end_line")
            end_line = self._as_int(end_line_val, default=line) if end_line_val else None
            message = self._as_str(raw.get("message"), default="ESLint finding")

            raw_severity = raw.get("severity")
            int_sev = raw_severity if isinstance(raw_severity, int) else 1
            is_security_rule = rule_id.startswith("security/") or rule_id.startswith(
                "no-unsanitized/"
            )

            if int_sev == 2 and is_security_rule:
                severity = FindingSeverity.HIGH
            else:
                severity = _ESLINT_SEVERITY_MAP.get(int_sev, FindingSeverity.LOW)

            category = "security.sast" if is_security_rule else "quality.static-analysis"

            finding_id = f"eslint_security:{rule_id}:{path}:{line}"
            fingerprint = self._fingerprint(f"eslint_security|{rule_id}|{path}|{line}")

            if is_security_rule:
                impact = f"Security issue detected by ESLint rule '{rule_id}'."
            else:
                impact = f"Code quality issue detected by ESLint rule '{rule_id}'."

            findings.append(
                FindingCreate(
                    finding_id=finding_id,
                    category=category,
                    severity=severity,
                    confidence=FindingConfidence.MEDIUM,
                    blocking=self._is_blocking(severity),
                    file_path=path,
                    line_start=line,
                    line_end=end_line,
                    source_tools=[result.collector_name],
                    rule_id=rule_id,
                    title=f"ESLint: {rule_id}",
                    evidence=[message],
                    impact=impact,
                    fix_recommendation=message,
                    fingerprint=fingerprint,
                )
            )
        return findings

    def _normalize_roslyn(self, result: CollectorResult) -> list[FindingCreate]:
        return self._normalize_sarif_based(result, "Roslyn", "quality.static-analysis")

    def _normalize_luacheck(self, result: CollectorResult) -> list[FindingCreate]:
        findings: list[FindingCreate] = []
        for raw in result.raw_findings:
            rule_id = self._as_str(raw.get("rule_id"), default="unknown")
            path = self._as_str(raw.get("path"), default="unknown-file")
            line = self._as_int(raw.get("line"), default=1)
            message = self._as_str(raw.get("message"), default="Luacheck finding")

            code_prefix = rule_id[:2] if len(rule_id) >= 2 else ""
            severity = _LUACHECK_SEVERITY_MAP.get(code_prefix, FindingSeverity.LOW)
            category = "quality.syntax-error" if code_prefix == "E0" else "quality.static-analysis"

            finding_id = f"luacheck:{rule_id}:{path}:{line}"
            fingerprint = self._fingerprint(f"luacheck|{rule_id}|{path}|{line}")

            findings.append(
                FindingCreate(
                    finding_id=finding_id,
                    category=category,
                    severity=severity,
                    confidence=FindingConfidence.MEDIUM,
                    blocking=self._is_blocking(severity),
                    file_path=path,
                    line_start=line,
                    line_end=None,
                    source_tools=[result.collector_name],
                    rule_id=rule_id,
                    title=f"Luacheck: {rule_id}",
                    evidence=[message],
                    impact=f"Lua code issue detected by Luacheck ({rule_id}).",
                    fix_recommendation=message,
                    fingerprint=fingerprint,
                )
            )
        return findings

    @staticmethod
    def _semgrep_category(rule_id: str) -> str:
        lowered = rule_id.lower()
        if any(token in lowered for token in ("secret", "auth", "crypto", "sql", "xss", "csrf")):
            return "security.sast"
        return "quality.static-analysis"

    @staticmethod
    def _semgrep_category_from_metadata(raw_category: str) -> str:
        lowered = raw_category.lower()
        if lowered == "security":
            return "security.sast"
        if lowered == "correctness":
            return "quality.bug"
        if lowered in ("performance", "best-practice", "maintainability"):
            return "quality.static-analysis"
        return f"quality.{lowered}" if lowered else "quality.static-analysis"

    @staticmethod
    def _sonar_category(issue_type: str) -> str:
        mapping = {
            "VULNERABILITY": "security.vulnerability",
            "BUG": "quality.bug",
            "CODE_SMELL": "quality.code-smell",
        }
        return mapping.get(issue_type, "quality.issue")

    @staticmethod
    def _derive_semgrep_impact(category: str, rule_id: str, cwe_tag: str) -> str:
        lowered = rule_id.lower()
        if category.startswith("security"):
            # Extract the vulnerability type from the rule_id path
            # e.g. "python.django.security.injection.sql-injection" -> "sql-injection"
            parts = lowered.split(".")
            vuln_type = parts[-1] if parts else lowered
            vuln_readable = vuln_type.replace("-", " ").replace("_", " ")
            return (
                f"Security risk: {vuln_readable} vulnerability detected by rule "
                f"'{rule_id}'{cwe_tag}."
            )
        if "bug" in category or "correctness" in category:
            return f"Potential bug detected by rule '{rule_id}'."
        return f"Code quality issue detected by rule '{rule_id}'."

    @staticmethod
    def _derive_sonar_impact(sonar_category: str, rule: str) -> str:
        if "vulnerability" in sonar_category:
            return f"Security vulnerability identified by Sonar rule '{rule}'."
        if "bug" in sonar_category:
            return f"Potential bug identified by Sonar rule '{rule}'."
        if "code-smell" in sonar_category:
            return f"Maintainability issue (code smell) identified by Sonar rule '{rule}'."
        return f"Code quality issue identified by Sonar rule '{rule}'."

    @staticmethod
    def _is_blocking(severity: FindingSeverity) -> bool:
        return severity in {FindingSeverity.CRITICAL, FindingSeverity.HIGH}

    @staticmethod
    def _fingerprint(canonical: str) -> str:
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _as_str(value: object, default: str = "") -> str:
        if value is None:
            return default
        return str(value)

    @staticmethod
    def _as_int(value: object, default: int) -> int:
        if isinstance(value, int):
            return value if value > 0 else default
        return default
