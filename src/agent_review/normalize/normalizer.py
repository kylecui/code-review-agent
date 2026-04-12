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
            fingerprint_source = self._as_str(raw.get("fingerprint"))
            fingerprint = (
                fingerprint_source
                if fingerprint_source
                else self._fingerprint(f"semgrep|{rule_id}|{path}|{line}")
            )

            evidence = [message]
            snippet = self._as_str(raw.get("snippet"))
            if snippet:
                evidence.append(snippet)
            cwe = raw.get("cwe")
            if isinstance(cwe, list) and cwe:
                evidence.append("CWE: " + ", ".join(str(c) for c in cwe))

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
                    impact="Potential security or code quality issue detected by static analysis.",
                    fix_recommendation=(
                        "Review the flagged code path and apply the corresponding "
                        "secure coding fix."
                    ),
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

            findings.append(
                FindingCreate(
                    finding_id=finding_id,
                    category=self._sonar_category(issue_type),
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
                    impact=(
                        "Potential maintainability, reliability, or security risk "
                        "identified by Sonar."
                    ),
                    fix_recommendation=(
                        "Address the Sonar issue by applying the recommended rule-compliant change."
                    ),
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
                    impact=(
                        "CI checks detected an issue that may affect build correctness or quality."
                    ),
                    fix_recommendation=(
                        "Investigate the related check output and update the code "
                        "or configuration accordingly."
                    ),
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
