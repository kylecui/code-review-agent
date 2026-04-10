# Code Review Agent Design Doc

## Title

**Policy-Grounded Agent for Code Review, Code Quality Assurance, Quality Control, and Code Safety**

## Purpose

Build an agent that reviews code changes with three distinct responsibilities:

- **Quality assurance**: enforce standards, architecture rules, and pre-merge expectations.
- **Quality control**: detect concrete defects, maintainability regressions, and missing tests in a specific change.
- **Safety/security**: detect vulnerabilities, unsafe workflows, and risky operational changes.

The agent is not the source of truth for merge control. It is the synthesis layer on top of deterministic evidence.

## Non-goals

This system does **not**:

- replace human approval for high-risk changes
- act as the sole merge authority
- invent findings without tool evidence or code-context evidence
- auto-remediate arbitrary security-sensitive logic
- guarantee semantic correctness of business logic in all domains

## Design principles

### 1. Separate reasoning from enforcement
The LLM can classify, prioritize, explain, and propose fixes.
The CI/policy system should decide whether a merge is allowed.

### 2. Use deterministic tools first
Let linters, type checkers, tests, SonarQube, Semgrep, CodeQL, secrets scanning, and dependency/supply-chain scanners produce evidence first. The agent reasons over that evidence instead of pretending to be the scanner.

### 3. Review by profile, not with one universal prompt
An auth change and a docs change should not invoke the same review path.

### 4. Emit structured findings
Every finding should have category, severity, confidence, evidence, impact, and fix guidance.

### 5. Bias toward low-noise outputs
A code-review agent that produces many weak comments will be ignored.

## System architecture

```text
SCM Event (PR/MR opened, synchronize, ready_for_review)
  -> Ingestor
  -> Change Classifier
  -> Review Profile Selector
  -> Evidence Collectors
      -> lint / format / type / tests / coverage
      -> SonarQube
      -> Semgrep
      -> CodeQL or platform SAST
      -> secrets scan
      -> dependency & SBOM scan
      -> repo posture checks
  -> Findings Normalizer
  -> Reasoning Engine
  -> Review Writer
  -> Gate Controller
  -> SCM Feedback + Metrics Store
```

## Main components

### Ingestor
Consumes:
- PR/MR metadata
- title/body
- base/head refs
- changed files
- diff hunks
- labels
- author/team ownership
- commit metadata

### Change classifier
Produces:
- change type: feature / bugfix / refactor / dependency / config / infra / test-only
- domains touched: authz, API, crypto, DB, CI/CD, network, parsing, secrets, etc.
- blast radius
- risk level
- required review profile

### Evidence collectors
Adapters for:
- formatter/linter/type checker
- unit/integration tests
- coverage delta
- SonarQube
- Semgrep
- CodeQL or GitLab-native SAST
- secrets scanning
- dependency and license scanning
- repo posture checks

### Findings normalizer
Converts raw tool outputs into one canonical schema:
- source tool
- category
- file/line
- severity
- rule id
- confidence
- dedupe key

### Reasoning engine
Jobs:
- merge duplicates
- connect line-level findings to real impact
- suppress trivial repeats
- identify missing tests
- identify missing design review
- estimate merge recommendation

### Review writer
Produces:
- inline comments
- summary comment
- risk summary
- escalation notices
- remediation suggestions

### Gate controller
Consumes:
- deterministic tool statuses
- normalized findings
- repository policy
- exception/override rules

Produces:
- pass
- warn
- request changes
- block
- escalate

## Review profiles

### `core_quality`
Use for most code changes.
Checks:
- formatter/linter/type/test
- coverage delta
- SonarQube maintainability/reliability
- basic test adequacy reasoning

### `api_surface`
Use when request/response schema or endpoint behavior changes.
Checks:
- input validation
- backward compatibility
- authn/authz
- error semantics
- negative tests

### `security_sensitive`
Use for auth, secrets, CI, parsers, deserialization, crypto, or workflow changes.
Checks:
- Semgrep security rules
- CodeQL or deep SAST
- secret scanning
- dependency and license scanning
- mandatory human escalation in some areas

### `workflow_security`
Use for `.github/workflows`, `.gitlab-ci.yml`, container build, release, deploy, and token/permission changes.
Checks:
- least privilege
- unpinned actions/images
- artifact integrity
- secret exposure
- branch/ruleset/pipeline policy conformance

### `migration_risk`
Use for schema or state changes.
Checks:
- rollback path
- backward compatibility
- idempotency
- safe rollout
- failure-mode test coverage

## Canonical finding schema

```json
{
  "id": "SEC-AUTHZ-001",
  "category": "security.authz",
  "severity": "high",
  "confidence": "high",
  "blocking": true,
  "file": "services/user/update.go",
  "line_start": 81,
  "line_end": 104,
  "source": ["semgrep", "llm"],
  "rule_source": "org-authz-policy-3.2",
  "title": "Missing ownership check before mutation",
  "evidence": [
    "Handler authenticates caller but does not verify target resource ownership",
    "Service accepts user_id from request body without authorization check"
  ],
  "impact": "Authenticated users may modify another user's profile",
  "fix_recommendation": "Enforce subject-resource ownership before update",
  "test_recommendation": "Add negative authorization test returning 403"
}
```

## Prompt contracts

### Change classification prompt
Input:
- metadata, file list, selected diff, labels

Output:
- change summary
- trust boundaries touched
- sensitive assets touched
- risk level
- review profile list

Constraint:
- no findings yet

### Synthesis prompt
Input:
- classification
- normalized tool findings
- code snippets
- org policies

Output:
- deduplicated findings
- missing tests
- escalation calls
- merge recommendation

Constraint:
- do not invent lines or exploit scenarios without evidence

### Review comment prompt
Input:
- one finding
- code context
- fix guidance

Output:
- concise inline comment under 120 words

## Policy model

Use a repository-level or org-level machine-readable file, for example:

```yaml
version: 1
profiles:
  core_quality:
    min_changed_lines_coverage: 80
    block_on:
      - sonar_quality_gate_fail
      - typecheck_fail
      - tests_fail
  security_sensitive:
    min_changed_lines_coverage: 90
    block_on:
      - codeql_high_or_critical
      - semgrep_blocking_finding
      - secret_scan_hit
    escalate_on:
      - auth_model_changed
      - crypto_changed
      - workflow_permission_expansion
exceptions:
  emergency_bypass_roles:
    - sre-lead
    - security-director
```

## Merge decision model

Recommended rule set:

- **pass**: no blocking findings, required checks green
- **warn**: non-blocking maintainability or low-confidence concerns
- **request_changes**: medium/high-confidence findings that need author action
- **block**: deterministic gate failed or critical/high material finding
- **escalate**: auth model, crypto, parser/sandbox, or workflow-permission changes

## Evaluation plan

Track:
- precision
- false positive rate
- critical-issue recall
- accepted-comment rate
- merge recommendation agreement with human reviewers
- time-to-actionable review
- percentage of findings backed by deterministic evidence

Use internal gold sets:
- historic PRs
- reverted PRs
- incident-causing commits
- security fix PRs
- “clean” PRs for overflagging tests

## Rollout plan

### Phase 1
- core quality only
- no blocking from LLM-originated findings
- deterministic gates only

### Phase 2
- security-sensitive profile
- structured findings
- human escalation

### Phase 3
- architecture invariants
- migration risk
- supply-chain posture

### Phase 4
- safe patch suggestions
- test generation for narrow classes
- requested-action buttons or MR fix suggestions

## Bottom line

Build the system as a **policy-grounded review orchestrator**, not as a single prompt. Deterministic evidence should come first, policy should remain explicit, and the LLM should synthesize and communicate findings rather than act as the only source of truth.
