# Code Review Agent Next Steps Implementation Plan

## Goal

Move from concept documents to a real v1 deployment with the smallest useful scope and the lowest operational risk.

## Recommended strategy

Use **one platform only** for v1.

Choose:
- GitHub first, or
- GitLab first

Do not build both platforms in parallel.

## Recommended v1 scope

Build only these capabilities:
- PR/MR ingest
- diff classification
- lint / typecheck / tests / coverage ingestion
- SonarQube ingestion
- Semgrep ingestion
- normalized findings schema
- summary review comment
- deterministic pass / warn / block decision

Delay these items:
- CodeQL synthesis
- patch generation
- GitLab approval-policy deep integration
- architecture-aware review
- workflow-security deep review
- autonomous remediation

## Control model

Choose the rollout mode before implementation.

### Stage A: advisory mode
- bot comments only
- non-blocking checks
- compare output with human reviewers

### Stage B: guarded enforcement
- selected required checks
- deterministic blocking only
- LLM-originated findings remain advisory unless backed by explicit policy

## Minimum infrastructure

Use this first deployment stack:
- FastAPI service
- Redis queue
- one worker process
- PostgreSQL or SQLite for metadata
- Docker-based deployment
- SCM app/token integration
- LLM credentials
- SonarQube connectivity
- Semgrep connectivity

## Build order

### 1. Define schemas first
Create stable definitions for:
- review request
- change classification
- normalized finding
- merge recommendation
- posted summary
- posted inline comment

### 2. Implement a file-based classifier
Start with heuristics.

Examples:
- `*.md` only -> docs / low risk
- `auth/`, `permission`, `policy`, `roles` -> security-sensitive
- `.github/workflows`, `.gitlab-ci.yml` -> workflow-security
- migrations / schema files -> migration-risk

### 3. Integrate deterministic evidence
Wire in:
- linter
- type checker
- tests
- coverage
- SonarQube
- Semgrep

Treat these as the primary facts.

### 4. Add normalization
Convert every tool output into one canonical finding schema.

### 5. Add LLM synthesis
Limit the LLM to:
- deduplicating findings
- prioritizing findings
- identifying missing tests
- writing concise review comments

### 6. Add gate controller
Keep blocking logic in YAML, not prompts.

Example rules:
- fail if tests fail
- fail if typecheck fails
- fail if SonarQube gate fails
- fail if Semgrep returns blocking rules
- warn for maintainability-only issues
- escalate for auth, crypto, or workflow-permission changes

## First 30-day plan

### Week 1
- choose GitHub or GitLab
- create service repo
- define schemas
- implement webhook ingest
- implement changed-file classifier

### Week 2
- integrate lint/type/test/coverage
- integrate SonarQube
- integrate Semgrep
- persist normalized findings

### Week 3
- add LLM synthesis
- post PR/MR summary comment
- add initial policy YAML
- run on a small set of repos in shadow mode

### Week 4
- tune false positives
- add severity/confidence thresholds
- enable one non-blocking status check
- prepare required-check rollout for low-risk repos

## Shadow mode requirements

Run the system in shadow mode before enforcement.

Measure:
- false positives
- missed obvious issues
- comment usefulness
- agreement with senior reviewers
- developer irritation level

## Internal benchmark

Create a benchmark set from:
- good PRs
- reverted PRs
- security fix PRs
- incident-causing PRs
- clean PRs to test overflagging

Use it to score:
- precision
- recall on serious issues
- quality of remediation guidance
- merge recommendation quality

## Initial engineering artifacts

Create these first:
- `default.policy.yaml`
- `finding.schema.json`
- `review.schema.json`
- `classifier.py`
- `normalize.py`
- `synthesize.py`
- `github_checks.py` or `gitlab_status.py`
- one sample CI workflow file
- one evaluation dataset folder with 20-50 historical PR cases

## Recommended real-world v1

Use this first production shape:
- GitHub first
- Python service
- FastAPI + Redis worker
- SonarQube + Semgrep + tests + coverage
- PR summary bot comment
- non-blocking status checks
- policy YAML
- 2-week shadow mode
- then required checks for `core-quality` only

## Team ownership

Assign owners for:
- policy file
- Semgrep rules
- SonarQube gate tuning
- prompt changes
- exception handling
- metrics and evaluation

Without ownership, the agent will drift and become noisy.

## Success criteria for v1

The v1 system is successful if it:
- catches obvious regressions and missing tests
- surfaces high-signal security issues
- keeps false positives low enough that developers do not mute it
- produces comments that are concise and actionable
- can be promoted from advisory mode to partial enforcement

## Recommended immediate next action

Create the service repository and the canonical schemas first. Then wire in GitHub or GitLab webhook ingestion before implementing any LLM prompt logic.
