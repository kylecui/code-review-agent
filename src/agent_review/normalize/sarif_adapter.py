from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_review.observability import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class SarifFinding:
    """Intermediate representation from SARIF result."""

    rule_id: str
    path: str
    line: int
    end_line: int | None
    severity: str  # SARIF level mapped to: ERROR, WARNING, INFO
    message: str
    snippet: str
    fingerprint: str
    category: str
    cwe: list[str]
    precision: str
    tool_name: str


class SarifAdapter:
    """Converts SARIF v2.1.0 JSON to list of raw_findings dicts."""

    def parse_file(self, sarif_path: Path) -> list[dict[str, object]]:
        try:
            with sarif_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except Exception as exc:
            logger.warning("failed_to_read_sarif_file", path=str(sarif_path), error=str(exc))
            return []

        if not isinstance(data, dict):
            logger.warning(
                "invalid_sarif_root", path=str(sarif_path), root_type=type(data).__name__
            )
            return []
        return self.parse_json(data)

    def parse_json(self, sarif_data: dict[str, object]) -> list[dict[str, object]]:
        try:
            runs_value = sarif_data.get("runs")
            if runs_value is not None and not isinstance(runs_value, list):
                logger.warning("invalid_sarif_runs", runs_type=type(runs_value).__name__)
                return []

            runs = self._extract_runs(sarif_data)
            findings: list[dict[str, object]] = []
            for run in runs:
                for finding in self._extract_results(run):
                    findings.append(
                        {
                            "rule_id": finding.rule_id,
                            "path": finding.path,
                            "line": finding.line,
                            "end_line": finding.end_line,
                            "severity": finding.severity,
                            "message": finding.message,
                            "snippet": finding.snippet,
                            "fingerprint": finding.fingerprint,
                            "category": finding.category,
                            "cwe": finding.cwe,
                            "precision": finding.precision,
                            "tool_name": finding.tool_name,
                        }
                    )
            return findings
        except Exception as exc:
            logger.warning("failed_to_parse_sarif", error=str(exc))
            return []

    def _extract_runs(self, sarif: dict[str, Any]) -> list[dict[str, Any]]:
        runs = sarif.get("runs")
        if not isinstance(runs, list):
            return []
        return [run for run in runs if isinstance(run, dict)]

    def _extract_results(self, run: dict[str, Any]) -> list[SarifFinding]:
        tool_name = self._extract_tool_name(run)
        results = run.get("results")
        if not isinstance(results, list):
            return []

        findings: list[SarifFinding] = []
        for result in results:
            if not isinstance(result, dict):
                continue

            result_with_run = dict(result)
            result_with_run["_run"] = run

            rule = self._resolve_rule(run, result_with_run)
            rule_id_value = result_with_run.get("ruleId") or rule.get("id")
            rule_id = str(rule_id_value) if rule_id_value is not None else "unknown-rule"
            if result_with_run.get("ruleId") is None:
                result_with_run["ruleId"] = rule_id

            path, line, end_line = self._extract_location(result_with_run)
            level = result_with_run.get("level")
            severity = self._map_severity(str(level) if level is not None else "note")

            message_obj = result_with_run.get("message")
            message = ""
            if isinstance(message_obj, dict):
                text_value = message_obj.get("text")
                if isinstance(text_value, str):
                    message = text_value
            if not message:
                message = "SARIF finding"

            snippet = self._extract_snippet(result_with_run)
            fingerprint = self._extract_fingerprint(result_with_run)

            properties: dict[str, Any] = {}
            raw_properties = rule.get("properties")
            if isinstance(raw_properties, dict):
                properties = raw_properties
            category_value = properties.get("category")
            category = (
                str(category_value)
                if isinstance(category_value, str) and category_value
                else "unknown"
            )
            cwe = self._extract_cwe(rule)
            precision_value = properties.get("precision")
            precision = (
                str(precision_value)
                if isinstance(precision_value, str) and precision_value
                else "unknown"
            )

            findings.append(
                SarifFinding(
                    rule_id=rule_id,
                    path=path,
                    line=line,
                    end_line=end_line,
                    severity=severity,
                    message=message,
                    snippet=snippet,
                    fingerprint=fingerprint,
                    category=category,
                    cwe=cwe,
                    precision=precision,
                    tool_name=tool_name,
                )
            )
        return findings

    def _resolve_rule(self, run: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        tool_raw = run.get("tool")
        tool: dict[str, Any] = tool_raw if isinstance(tool_raw, dict) else {}
        driver_raw = tool.get("driver")
        driver: dict[str, Any] = driver_raw if isinstance(driver_raw, dict) else {}
        driver_rules = self._as_rule_list(driver.get("rules"))

        rule_index = result.get("ruleIndex")
        if isinstance(rule_index, int) and 0 <= rule_index < len(driver_rules):
            return driver_rules[rule_index]

        result_rule_id = result.get("ruleId")
        result_rule_id_text = str(result_rule_id) if result_rule_id is not None else ""
        if result_rule_id_text:
            driver_match = self._find_rule_by_id(driver_rules, result_rule_id_text)
            if driver_match:
                return driver_match

        extensions = tool.get("extensions")
        if isinstance(extensions, list):
            for extension in extensions:
                if not isinstance(extension, dict):
                    continue
                extension_rules = self._as_rule_list(extension.get("rules"))
                if not extension_rules:
                    continue
                if isinstance(rule_index, int) and 0 <= rule_index < len(extension_rules):
                    return extension_rules[rule_index]
                if result_rule_id_text:
                    extension_match = self._find_rule_by_id(extension_rules, result_rule_id_text)
                    if extension_match:
                        return extension_match

        return {}

    def _extract_location(self, result: dict[str, Any]) -> tuple[str, int, int | None]:
        locations = result.get("locations")
        if not isinstance(locations, list) or not locations:
            return "unknown", 0, None

        first_location = locations[0]
        if not isinstance(first_location, dict):
            return "unknown", 0, None

        physical_location_raw = first_location.get("physicalLocation")
        if not isinstance(physical_location_raw, dict):
            return "unknown", 0, None
        physical_location: dict[str, Any] = physical_location_raw

        artifact_location_raw = physical_location.get("artifactLocation")
        artifact_location: dict[str, Any] = (
            artifact_location_raw if isinstance(artifact_location_raw, dict) else {}
        )
        uri_value = artifact_location.get("uri")
        raw_path = str(uri_value) if isinstance(uri_value, str) and uri_value else "unknown"

        uri_base_id = artifact_location.get("uriBaseId")
        run = result.get("_run")
        if isinstance(run, dict) and isinstance(uri_base_id, str) and raw_path != "unknown":
            raw_path = self._resolve_path_with_base_id(run, raw_path, uri_base_id)

        region_raw = physical_location.get("region")
        region: dict[str, Any] = region_raw if isinstance(region_raw, dict) else {}
        line_value = region.get("startLine")
        line = line_value if isinstance(line_value, int) else 0

        end_line_value = region.get("endLine")
        end_line = end_line_value if isinstance(end_line_value, int) else None

        return raw_path, line, end_line

    def _extract_snippet(self, result: dict[str, Any]) -> str:
        locations = result.get("locations")
        if not isinstance(locations, list) or not locations:
            return ""

        first_location = locations[0]
        if not isinstance(first_location, dict):
            return ""

        physical_location = first_location.get("physicalLocation")
        if not isinstance(physical_location, dict):
            return ""

        region = physical_location.get("region")
        if not isinstance(region, dict):
            return ""

        snippet = region.get("snippet")
        if not isinstance(snippet, dict):
            return ""

        text = snippet.get("text")
        return text if isinstance(text, str) else ""

    def _extract_fingerprint(self, result: dict[str, Any]) -> str:
        partial_fingerprints = result.get("partialFingerprints")
        if isinstance(partial_fingerprints, dict) and partial_fingerprints:
            first_key = next(iter(partial_fingerprints))
            first_value = partial_fingerprints[first_key]
            if first_value is not None and str(first_value):
                return str(first_value)
            return str(first_key)

        final_rule_id = (
            str(result.get("ruleId")) if result.get("ruleId") is not None else "unknown-rule"
        )
        final_path, final_line, _ = self._extract_location(result)

        canonical = f"{final_rule_id}|{final_path}|{final_line}"
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _extract_cwe(self, rule: dict[str, Any]) -> list[str]:
        properties = rule.get("properties")
        if not isinstance(properties, dict):
            return []

        cwe = properties.get("cwe")
        if isinstance(cwe, list):
            return [str(item) for item in cwe if item is not None]

        tags = properties.get("tags")
        if isinstance(tags, list):
            return [
                str(item)
                for item in tags
                if isinstance(item, str) and item.upper().startswith("CWE-")
            ]

        return []

    def _map_severity(self, level: str) -> str:
        mapping = {
            "error": "ERROR",
            "warning": "WARNING",
            "note": "INFO",
            "none": "INFO",
        }
        return mapping.get(level.lower(), "INFO")

    @staticmethod
    def _as_rule_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [rule for rule in value if isinstance(rule, dict)]

    @staticmethod
    def _find_rule_by_id(rules: list[dict[str, Any]], rule_id: str) -> dict[str, Any]:
        for rule in rules:
            if str(rule.get("id", "")) == rule_id:
                return rule
        return {}

    @staticmethod
    def _extract_tool_name(run: dict[str, Any]) -> str:
        tool = run.get("tool")
        if not isinstance(tool, dict):
            return "unknown"
        driver = tool.get("driver")
        if not isinstance(driver, dict):
            return "unknown"
        name = driver.get("name")
        if not isinstance(name, str) or not name:
            return "unknown"
        return name

    @staticmethod
    def _resolve_path_with_base_id(run: dict[str, Any], uri: str, uri_base_id: str) -> str:
        bases = run.get("originalUriBaseIds")
        if not isinstance(bases, dict):
            return uri

        base_entry = bases.get(uri_base_id)
        if not isinstance(base_entry, dict):
            return uri

        base_uri = base_entry.get("uri")
        if not isinstance(base_uri, str) or not base_uri:
            return uri

        normalized_base = base_uri.replace("file://", "")
        if not normalized_base:
            return uri

        if normalized_base.endswith("/"):
            return f"{normalized_base}{uri}"
        return str(Path(normalized_base) / uri)
