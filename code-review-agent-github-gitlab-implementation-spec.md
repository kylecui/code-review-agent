# Code Review Agent GitHub/GitLab Implementation Spec

## Objective

Provide an implementation-grade specification for deploying the code review agent on GitHub and GitLab.

## Repository layout

```text
agent-review/
  README.md
  docs/
    architecture.md
    policy-model.md
    prompt-contracts.md
    evaluation.md
  services/
    api/
      main.py
      routes/
        github_webhooks.py
        gitlab_webhooks.py
      schemas/
        finding.py
        review.py
        event.py
    classifier/
      classifier.py
      profiles.py
    collectors/
      lint.py
      tests.py
      coverage.py
      sonar.py
      semgrep.py
      codeql.py
      sast_gitlab.py
      secrets.py
      deps.py
      repo_posture.py
    normalize/
      normalize.py
      dedupe.py
    reasoning/
      synthesize.py
      comments.py
    gate/
      policy.py
      controller.py
    scm/
      github_checks.py
      github_reviews.py
      gitlab_notes.py
      gitlab_status.py
  prompts/
    classify.txt
    synthesize.txt
    inline_comment.txt
    summary.txt
  policies/
    default.policy.yaml
  tests/
    fixtures/
    unit/
    integration/
```

## Service boundaries

### `api`
Receives webhooks and queues reviews.

### `classifier`
Maps changed files and metadata to a review profile.

### `collectors`
Runs or fetches outputs from scanners and CI jobs.

### `normalize`
Transforms tool-specific outputs into the canonical finding schema.

### `reasoning`
Uses the LLM after evidence is collected.

### `gate`
Applies deterministic merge policy.

### `scm`
Posts checks, reviews, notes, and summary comments.

## Minimal APIs

### Internal review request
```json
{
  "scm": "github",
  "repo": "org/service-a",
  "change_id": "pr-1842",
  "base_ref": "main",
  "head_ref": "feature/authz-fix",
  "head_sha": "abc123",
  "profile_hint": null
}
```

### Internal review result
```json
{
  "change_id": "pr-1842",
  "overall_risk": "high",
  "merge_recommendation": "request_changes",
  "required_human_review": true,
  "findings": [],
  "check_status": {
    "lint": "pass",
    "tests": "pass",
    "sonar": "pass",
    "semgrep": "pass",
    "security": "warn"
  }
}
```

## Environment variables

```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-5.4-thinking

SONAR_HOST_URL=...
SONAR_TOKEN=...

SEMGREP_APP_TOKEN=...

GITHUB_APP_ID=...
GITHUB_PRIVATE_KEY=...
GITHUB_WEBHOOK_SECRET=...

GITLAB_TOKEN=...
GITLAB_WEBHOOK_SECRET=...
GITLAB_BASE_URL=...

POLICY_DIR=./policies
MAX_INLINE_COMMENTS=30
MAX_BLOCKING_FINDINGS=10
```

## GitHub implementation

### Event model
Trigger on:
- `pull_request.opened`
- `pull_request.synchronize`
- `pull_request.ready_for_review`

### Feedback channels
Use two channels:
- **Check run / annotations** for machine-readable status and line annotations
- **PR review summary** for synthesized human-readable feedback

### Recommended GitHub checks
Create distinct checks:
- `agent-review/classify`
- `agent-review/core-quality`
- `agent-review/security`
- `agent-review/summary`

### GitHub Actions workflow example

```yaml
name: agent-review
on:
  pull_request:
    types: [opened, synchronize, ready_for_review]

jobs:
  classify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Detect changed files
        run: git diff --name-only origin/${{ github.base_ref }}...${{ github.sha }} > changed_files.txt
      - name: Run classifier
        run: python -m services.classifier.classifier

  quality:
    runs-on: ubuntu-latest
    needs: classify
    steps:
      - uses: actions/checkout@v4
      - name: Lint
        run: make lint
      - name: Typecheck
        run: make typecheck
      - name: Tests
        run: make test
      - name: Coverage
        run: make coverage

  sonar:
    runs-on: ubuntu-latest
    needs: quality
    steps:
      - uses: actions/checkout@v4
      - name: SonarQube Scan
        run: ./scripts/run-sonar.sh

  semgrep:
    runs-on: ubuntu-latest
    needs: classify
    steps:
      - uses: actions/checkout@v4
      - name: Semgrep
        run: semgrep ci

  summarize:
    runs-on: ubuntu-latest
    needs: [quality, sonar, semgrep]
    steps:
      - uses: actions/checkout@v4
      - name: Synthesize findings
        run: python -m services.reasoning.synthesize
      - name: Publish checks
        run: python -m services.scm.github_checks
```

### GitHub ruleset / branch protection
Require:
- `agent-review/core-quality`
- `agent-review/security`
- `sonarqube-quality-gate`
- `codeql`

## GitLab implementation

### Event model
Trigger on:
- merge request webhook
- pipeline webhook
- optional scheduled policy re-evaluation

### Feedback channels
Use:
- MR note/discussion for summary
- job status for pass/fail
- security widget and approval policies for scanner-produced security results

### GitLab CI example

```yaml
stages:
  - classify
  - quality
  - security
  - summarize

variables:
  AST_ENABLE_MR_PIPELINES: "true"

classify:
  stage: classify
  image: python:3.12
  script:
    - python -m services.classifier.classifier
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"

quality:
  stage: quality
  image: python:3.12
  script:
    - make lint
    - make typecheck
    - make test
    - make coverage
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"

semgrep:
  stage: security
  image: semgrep/semgrep:latest
  script:
    - semgrep ci
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"

summarize:
  stage: summarize
  image: python:3.12
  script:
    - python -m services.reasoning.synthesize
    - python -m services.scm.gitlab_status
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

### GitLab approval policy pattern
Use merge request approval policies to require approval for:
- new critical findings
- removed mandatory security jobs
- protected-branch security-sensitive changes

## SonarQube integration pattern

Use SonarQube for PR decoration and as one deterministic input into the gate.

Recommended gate:
- fail if PR quality gate fails
- surface maintainability and reliability issues separately from security findings
- map severity into blocking vs advisory using repo policy

## Semgrep integration pattern

Use Semgrep in two ways:
- CI evidence source
- developer-facing PR/MR comments for selected high-signal rules

## CodeQL / native code scanning integration

On GitHub:
- treat CodeQL or GitHub code scanning as first-class evidence
- do not duplicate its annotations with low-value bot comments
- summarize only the most material alerts

## Policy file example

```yaml
version: 1
profiles:
  core_quality:
    require_checks:
      - lint
      - typecheck
      - tests
      - sonar
    changed_lines_coverage_min: 80
    blocking_categories:
      - correctness.regression
  security_sensitive:
    require_checks:
      - semgrep
      - sonar
      - codeql
    changed_lines_coverage_min: 90
    blocking_categories:
      - security.authz
      - security.secrets
      - security.workflow
    escalate_categories:
      - security.crypto
      - security.sandbox
      - security.authz_model
  workflow_security:
    require_checks:
      - workflow-lint
      - semgrep
    block_on_permission_expansion: true
limits:
  max_inline_comments: 25
  max_summary_findings: 10
```

## Review comment style guide

Every comment should answer three things:
- what is wrong
- why it matters
- what to change

Example:

```text
This handler authenticates the caller but does not verify ownership of the target resource before update. That allows an authenticated user to modify another user’s profile if they can supply a different user_id. Enforce subject-resource ownership before calling the service layer, and add a negative test asserting a 403 for cross-user updates.
```

## MVP scope

Build first:
- classifier
- quality collectors
- SonarQube collector
- Semgrep collector
- GitHub checks / GitLab status posting
- canonical schema
- synthesis step
- deterministic gate controller

Delay:
- auto-fix
- cross-repo reasoning
- deep architecture inference
- business-logic abuse discovery beyond seeded policies

## Recommended first milestone

A practical first production target is:
- GitHub first
- PR classification
- lint/test/type/coverage
- SonarQube gate
- Semgrep high-signal rules
- structured summary comment
- required status checks

Then add:
- CodeQL synthesis
- GitLab MR path
- approval-policy integration
- workflow-security profile
- patch suggestions

## Bottom line

Build this as a **review orchestrator** rather than a single model prompt: deterministic evidence in front, policy in the middle, LLM synthesis at the end, and SCM-native controls for merge enforcement.
