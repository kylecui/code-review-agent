# Admin Dashboard Implementation Plan

## Decisions (User-Confirmed)

- Frontend: React 19 + Vite + shadcn/ui + TanStack Router + TanStack Query
- Existing Jinja2 UI: Absorbed into SPA (removed)
- Auth: Two-role (is_superuser boolean) + GitHub OAuth
- Config storage: DB for operational settings, env vars for secrets/infrastructure
- Policy storage: DB-backed with disk YAML as initial seed/fallback
- API client: Auto-generated TypeScript from FastAPI OpenAPI spec via @hey-api/openapi-ts
- SPA serving: FastAPI StaticFiles(html=True) catch-all (single container)
- Phasing: Backend APIs first (Phase 1-2), then frontend (Phase 3-5)

## Architecture Overview

```
Browser → FastAPI (port 8000)
            ├── /api/auth/*          (auth endpoints, public)
            ├── /api/admin/*         (admin endpoints, auth required)
            ├── /api/scan            (scan trigger, existing)
            ├── /webhooks/github     (webhook, HMAC-only, NO auth)
            ├── /health, /ready      (health checks, public)
            └── /* catch-all         (SPA static files, index.html fallback)
```

## Phase 1: Backend Auth Foundation

### Commit 1: User model and password hashing
**Files to create/modify:**
- NEW `src/agent_review/models/user.py` — User ORM model
  - id: UUID PK (same pattern as ReviewRun)
  - email: str, unique, indexed
  - hashed_password: str
  - full_name: str | None
  - is_active: bool = True
  - is_superuser: bool = False
  - github_id: int | None, unique (for OAuth link)
  - github_login: str | None
  - created_at, updated_at: DateTime with timezone
- MODIFY `src/agent_review/models/__init__.py` — export User
- NEW `alembic/versions/004_add_user_table.py` — migration
- NEW `src/agent_review/auth/__init__.py`
- NEW `src/agent_review/auth/password.py` — hash_password(), verify_password() using pwdlib
- MODIFY `pyproject.toml` — add `pwdlib[argon2,bcrypt]`
- NEW `tests/unit/test_password.py` — hash, verify, hash migration tests

**Acceptance criteria:**
- User model created in DB via migration
- password hash/verify round-trips correctly
- `make check` passes (ruff, mypy strict, all tests)

**QA scenario:**
- Tool: pytest
- Steps: (1) Run `alembic upgrade head` → verify user table exists. (2) Call hash_password("test123") → returns non-empty string != "test123". (3) Call verify_password("test123", hashed) → True. (4) Call verify_password("wrong", hashed) → False. (5) Run `make check` → exit 0.

### Commit 2: JWT token creation and validation
**Files to create/modify:**
- MODIFY `src/agent_review/config.py` — add `secret_key: SecretStr` with sensible default for dev, `access_token_expire_minutes: int = 60`
- MODIFY `.env.example` — add AGENT_REVIEW_SECRET_KEY
- NEW `src/agent_review/auth/token.py` — create_access_token(user_id, is_superuser) -> str, decode_access_token(token) -> TokenPayload
- NEW `src/agent_review/auth/dependencies.py` — get_current_user(request) -> User (reads HttpOnly cookie), get_current_superuser(request) -> User (raises 403 if not superuser)
- NEW `src/agent_review/schemas/auth.py` — TokenPayload, LoginRequest, RegisterRequest, UserRead, UserCreate, UserUpdate
- NEW `tests/unit/test_token.py` — create, decode, expired, invalid signature, malformed

**Acceptance criteria:**
- JWT round-trips: create -> decode recovers user_id and is_superuser
- Expired token raises appropriate error
- Invalid signature raises appropriate error
- `get_current_user` dependency extracts user from cookie
- `get_current_superuser` raises 403 for non-superuser

**QA scenario:**
- Tool: pytest
- Steps: (1) create_access_token(user_id=UUID, is_superuser=True) → returns JWT string. (2) decode_access_token(token) → TokenPayload with matching user_id and is_superuser=True. (3) Create token with expire=-1min, decode → raises 401 HTTPException. (4) Tamper with token string, decode → raises 401 HTTPException. (5) Mock request with cookie "access_token={valid_token}", call get_current_user → returns User. (6) Mock request with no cookie, call get_current_user → raises 401. (7) Call get_current_superuser with viewer user → raises 403.

### Commit 3: Login/register API endpoints
**Files to create/modify:**
- NEW `src/agent_review/api/auth.py` — APIRouter with:
  - POST /api/auth/register — create user, return UserRead, set HttpOnly cookie
  - POST /api/auth/login — verify credentials, return UserRead, set HttpOnly cookie
  - POST /api/auth/logout — clear cookie
  - GET /api/auth/me — return current user (requires auth)
- MODIFY `src/agent_review/app.py` — include auth_router at prefix="/api/auth"
- NEW `tests/integration/test_auth_api.py` — full flow: register, login, me, logout, unauthorized access

**Acceptance criteria:**
- Register creates user, sets cookie, returns user data
- Login with valid creds returns 200 + cookie
- Login with wrong password returns 401
- GET /me with valid cookie returns user
- GET /me without cookie returns 401
- POST /webhooks/github still works without cookie (CRITICAL)
- Existing tests still pass (171+)

**QA scenario:**
- Tool: pytest with httpx AsyncClient (app=create_app)
- Steps: (1) POST /api/auth/register {"email":"a@b.com","password":"Test1234!","full_name":"Test"} → 201, response has "id","email","full_name", Set-Cookie header contains "access_token" with HttpOnly flag. (2) GET /api/auth/me with cookie → 200, body matches registered user. (3) POST /api/auth/logout → 200, Set-Cookie clears access_token. (4) GET /api/auth/me without cookie → 401 {"detail":"Not authenticated"}. (5) POST /api/auth/login {"email":"a@b.com","password":"Test1234!"} → 200 with Set-Cookie. (6) POST /api/auth/login {"email":"a@b.com","password":"wrong"} → 401. (7) POST /webhooks/github with valid HMAC body, no cookie → 200 (not 401). (8) Run full test suite → 171+ pass.

### Commit 4: GitHub OAuth flow
**Files to create/modify:**
- MODIFY `pyproject.toml` — add `authlib`, `itsdangerous`
- MODIFY `src/agent_review/config.py` — add github_oauth_client_id, github_oauth_client_secret (SecretStr), oauth_redirect_uri
- NEW `src/agent_review/auth/oauth.py` — GitHub OAuth helper: build_authorize_url(), exchange_code_for_token(), fetch_github_user()
- MODIFY `src/agent_review/api/auth.py` — add:
  - GET /api/auth/github/login — redirect to GitHub authorization URL
  - GET /api/auth/github/callback — exchange code, get-or-create user, set cookie, redirect to SPA
- MODIFY `src/agent_review/app.py` — add SessionMiddleware (needed for OAuth CSRF state)
- NEW `tests/integration/test_oauth.py` — mock GitHub responses, test get-or-create user, test callback sets cookie

**Acceptance criteria:**
- /api/auth/github/login redirects to GitHub with correct params
- /api/auth/github/callback with valid code creates user and sets cookie
- Existing GitHub user logs in (matched by github_id)
- SessionMiddleware does NOT affect webhook endpoint
- OAuth state parameter prevents CSRF

**QA scenario:**
- Tool: pytest with respx (mock GitHub API)
- Steps: (1) GET /api/auth/github/login → 302, Location header contains github.com/login/oauth/authorize with client_id and state params. (2) GET /api/auth/github/callback?code=mock_code&state=valid_state (with mocked GitHub token+user API responses) → 302 redirect to SPA root, Set-Cookie contains access_token. (3) Check DB → new User with github_id matching mock response, is_superuser=False. (4) Repeat callback with same github_id → same user, no duplicate. (5) POST /webhooks/github with valid HMAC, no session cookie → 200.

### Commit 5: User management API (superuser-only)
**Files to create/modify:**
- NEW `src/agent_review/api/admin/__init__.py`
- NEW `src/agent_review/api/admin/users.py` — APIRouter (all require superuser):
  - GET /api/admin/users — paginated list
  - GET /api/admin/users/{id} — single user
  - POST /api/admin/users — create user (admin-created)
  - PATCH /api/admin/users/{id} — update user (toggle active, superuser, change email/name)
  - DELETE /api/admin/users/{id} — deactivate user
- MODIFY `src/agent_review/app.py` — include admin users router
- NEW `tests/integration/test_admin_users.py` — CRUD tests, authorization tests (viewer gets 403)

**Acceptance criteria:**
- Superuser can CRUD users
- Viewer (is_superuser=False) gets 403 on all admin endpoints
- Unauthenticated gets 401
- Cannot delete yourself
- Cannot remove your own superuser flag

**QA scenario:**
- Tool: pytest with httpx AsyncClient
- Steps: (1) Create superuser via register (first user = superuser). (2) POST /api/admin/users {"email":"viewer@b.com","password":"V1ewer!","is_superuser":false} as superuser → 201. (3) GET /api/admin/users as superuser → 200, list contains 2 users. (4) PATCH /api/admin/users/{viewer_id} {"is_superuser":true} as superuser → 200. (5) GET /api/admin/users as viewer → 403. (6) DELETE /api/admin/users/{self_id} as superuser → 400 "Cannot delete yourself". (7) PATCH /api/admin/users/{self_id} {"is_superuser":false} as superuser → 400 "Cannot remove own superuser". (8) All requests without auth → 401.

## Phase 2: Admin API Endpoints

### Commit 6: Runtime settings management
**Files to create/modify:**
- NEW `src/agent_review/models/app_config.py` — AppConfig ORM model
  - id: UUID PK
  - key: str, unique, indexed
  - value: str (JSON-serialized)
  - updated_at: DateTime
  - updated_by: UUID FK to User
- MODIFY `src/agent_review/models/__init__.py` — export AppConfig
- NEW `alembic/versions/005_add_app_config_table.py`
- NEW `src/agent_review/api/admin/settings.py` — APIRouter (superuser-only):
  - GET /api/admin/settings — return all operational settings as object
  - PUT /api/admin/settings — update one or more settings, validate types
  - DELETE /api/admin/settings/{key} — remove DB override for a single key, reverts to env default
- NEW `src/agent_review/config.py` changes — add `get_effective_setting(key, db_value, env_value)` helper
  - Operational settings: llm_classify_model, llm_synthesize_model, llm_fallback_model, llm_max_tokens, llm_temperature, llm_cost_budget_per_run_cents, semgrep_mode, semgrep_severity_filter, max_inline_comments, max_diff_lines, log_level
  - Infrastructure settings (env-only, NOT editable): database_url, github_app_id, github_private_key, github_webhook_secret, secret_key
- NEW `tests/integration/test_admin_settings.py`

**Acceptance criteria:**
- GET returns current effective settings (DB overrides env defaults)
- PUT updates settings in DB, next GET reflects changes
- DELETE /api/admin/settings/{key} removes DB override, next GET shows env default
- Invalid setting key returns 422
- Invalid value type returns 422
- Infrastructure settings are not exposed for editing
- Viewer gets 403

**QA scenario:**
- Tool: pytest with httpx AsyncClient
- Steps: (1) GET /api/admin/settings → verify JSON response contains all operational keys with env defaults. (2) PUT {"llm_classify_model": "gpt-4o"} → 200. (3) GET → verify llm_classify_model is "gpt-4o". (4) DELETE /api/admin/settings/llm_classify_model → 200. (5) GET → verify llm_classify_model reverted to env default "gpt-4o-mini". (6) PUT {"database_url": "x"} → 422 (infrastructure setting). (7) PUT as viewer → 403. (8) GET as viewer → 403.

### Commit 7: Policy management API
**Files to create/modify:**
- NEW `src/agent_review/models/policy_store.py` — PolicyStore ORM model
  - id: UUID PK
  - name: str, unique (e.g., "default", "owner/repo")
  - content: str (YAML text)
  - etag: str (sha256 of content)
  - updated_at: DateTime
  - updated_by: UUID FK to User
- MODIFY `src/agent_review/models/__init__.py` — export PolicyStore
- NEW `alembic/versions/006_add_policy_store_table.py`
- MODIFY `src/agent_review/gate/policy_loader.py` — check DB first, fall back to disk YAML
  - New method: `load_from_db(session, repo)` -> PolicyConfig | None
  - Modified `load()` signature: accepts optional db session
- NEW `src/agent_review/api/admin/policies.py` — APIRouter (superuser-only):
  - GET /api/admin/policies — list all stored policies
  - GET /api/admin/policies/{name} — return policy content + ETag header
  - PUT /api/admin/policies/{name} — save policy, require If-Match ETag header for updates (not creates). Validate YAML parses and conforms to PolicyConfig schema.
  - DELETE /api/admin/policies/{name} — remove DB override (reverts to disk if exists)
- NEW `src/agent_review/api/admin/policies.py` — seed endpoint:
  - POST /api/admin/policies/seed — import disk YAML files into DB (one-time setup)
- NEW `tests/integration/test_admin_policies.py` — CRUD + ETag conflict + YAML validation

**Acceptance criteria:**
- Valid YAML saves and returns 200 with new ETag
- Invalid YAML returns 422 with parse error details
- YAML that doesn't conform to PolicyConfig schema returns 422 with validation errors
- PUT with stale ETag returns 409 Conflict
- PUT without If-Match on existing policy returns 428 Precondition Required
- DELETE reverts to disk-based policy
- PolicyLoader.load() checks DB first, then disk fallback
- Existing scan pipeline works with DB-backed policies
- Viewer gets 403

**QA scenario:**
- Tool: pytest with httpx AsyncClient
- Steps: (1) POST /api/admin/policies/seed as superuser → 200, imports disk YAML into DB. (2) GET /api/admin/policies → 200, list includes "default". (3) GET /api/admin/policies/default → 200, body contains YAML text, response has ETag header. (4) PUT /api/admin/policies/default with valid YAML + If-Match=current_etag → 200, new ETag returned. (5) PUT /api/admin/policies/default with same old ETag → 409 with body containing current server YAML. (6) PUT with If-Match but invalid YAML (missing colon) → 422 with parse error. (7) PUT with valid YAML that fails PolicyConfig validation (e.g., unknown collector) → 422 with validation details. (8) DELETE /api/admin/policies/default → 200. (9) Verify PolicyLoader.load() falls back to disk YAML. (10) All requests as viewer → 403.

### Commit 8: Scan management API
**Files to create/modify:**
- NEW `src/agent_review/api/admin/scans.py` — APIRouter:
  - GET /api/admin/scans — paginated scan list with filters (repo, state, kind), requires auth (viewer OK)
  - GET /api/admin/scans/{id} — scan detail with findings, requires auth (viewer OK)
  - POST /api/admin/scans/trigger — trigger new scan (requires superuser): accepts repo, installation_id or path
  - POST /api/admin/scans/{id}/cancel — cancel running scan (superuser)
  - DELETE /api/admin/scans/{id} — delete scan + findings (superuser)
- MODIFY `src/agent_review/app.py` — include admin scans router
- NEW `tests/integration/test_admin_scans.py`

**Acceptance criteria:**
- List endpoint returns paginated results, default 20 per page
- Filters work: by repo, by state, by kind
- Viewers can list/view scans but cannot trigger/cancel/delete
- Superusers can trigger/cancel/delete
- Delete cascades to findings

**QA scenario:**
- Tool: pytest with httpx AsyncClient
- Steps: (1) Create 25 scan records in DB. (2) GET /api/admin/scans as viewer → 200, body has "items" (20), "total" (25), "page" (1). (3) GET /api/admin/scans?page=2 → 200, items has 5 records. (4) GET /api/admin/scans?repo=kylecui/test → 200, filtered results. (5) GET /api/admin/scans/{id} as viewer → 200 with findings array. (6) POST /api/admin/scans/trigger as viewer → 403. (7) POST /api/admin/scans/trigger as superuser {"repo":"owner/repo","installation_id":123} → 202. (8) POST /api/admin/scans/{id}/cancel as superuser → 200. (9) DELETE /api/admin/scans/{id} as superuser → 200, verify findings also deleted from DB. (10) DELETE as viewer → 403.

### Commit 9: CORS middleware
**Files to create/modify:**
- MODIFY `src/agent_review/config.py` — add `cors_origins: list[str] = []`
- MODIFY `src/agent_review/app.py` — add CORSMiddleware if cors_origins is non-empty
- MODIFY `.env.example` — add AGENT_REVIEW_CORS_ORIGINS
- NEW `tests/integration/test_cors.py` — verify CORS headers, verify no CORS when empty

**Acceptance criteria:**
- CORS headers present when cors_origins configured
- No CORS middleware added when cors_origins is empty
- Preflight OPTIONS requests handled correctly
- Webhook endpoint works with CORS enabled

**QA scenario:**
- Tool: pytest with httpx AsyncClient
- Steps: (1) Create app with cors_origins=["http://localhost:5173"]. (2) OPTIONS /api/admin/scans with Origin: http://localhost:5173 → 200, response has Access-Control-Allow-Origin: http://localhost:5173. (3) GET /api/admin/scans with Origin header → response has CORS headers. (4) Create app with cors_origins=[]. (5) OPTIONS /api/admin/scans with Origin → no Access-Control-Allow-Origin header in response. (6) POST /webhooks/github with CORS enabled + valid HMAC → 200.

## Phase 3: Frontend Scaffold

### Commit 10: React + Vite project scaffold
**Files to create:**
- `frontend/package.json` — React 19, Vite, TanStack Router, TanStack Query, shadcn/ui, Tailwind CSS 4
- `frontend/vite.config.ts` — dev server proxy to localhost:8000
- `frontend/tsconfig.json`
- `frontend/src/main.tsx` — app entry
- `frontend/src/routes/` — TanStack file-based routing
- `frontend/src/components/ui/` — shadcn/ui components (button, input, form, table, card, badge, dialog, sidebar, etc.)
- `frontend/src/lib/` — utils, API client setup
- MODIFY `Makefile` — add `dev-frontend`, `build-frontend`, `check-frontend`

**Acceptance criteria:**
- `cd frontend && bun install && bun run dev` starts dev server on port 5173
- Dev server proxies /api/* to localhost:8000
- Empty shell renders with sidebar navigation
- `bun run build` produces dist/ directory

**QA scenario:**
- Tool: shell commands
- Steps: (1) `cd frontend && bun install` → exit 0, node_modules created. (2) `bun run build` → exit 0, dist/ directory exists with index.html. (3) `bun run type-check` → exit 0. (4) `bun run lint` → exit 0. (5) Verify dist/index.html contains `<div id="root">`. (6) Verify `make build-frontend` runs successfully from project root.

### Commit 11: Auto-generated API client
**Files to create/modify:**
- `frontend/openapi-ts.config.ts` — @hey-api/openapi-ts config pointing to http://localhost:8000/openapi.json
- `frontend/src/lib/api/` — generated client (run `bun run generate-api`)
- `frontend/src/hooks/use-auth.ts` — useAuth hook (login, logout, register, current user)
- `frontend/src/hooks/use-current-user.ts` — TanStack Query hook for GET /api/auth/me
- MODIFY `frontend/package.json` — add `generate-api` script

**Acceptance criteria:**
- `bun run generate-api` produces typed client matching all backend endpoints
- useAuth hook provides login/logout/register functions
- useCurrentUser returns current user or null

**QA scenario:**
- Tool: shell + vitest
- Steps: (1) Start backend `make serve`. (2) `cd frontend && bun run generate-api` → exit 0, src/lib/api/ directory has generated TypeScript files. (3) Verify generated client has functions for: postApiAuthLogin, postApiAuthRegister, getApiAuthMe, getApiAdminScans, etc. (4) `bun run type-check` → exit 0 (generated types compile). (5) Vitest unit tests for useAuth and useCurrentUser hooks pass.

### Commit 12: Login page and auth flow
**Files to create:**
- `frontend/src/routes/login.tsx` — login form + GitHub OAuth button
- `frontend/src/routes/__root.tsx` — root layout with auth check
- `frontend/src/components/auth-guard.tsx` — redirect to /login if not authenticated
- `frontend/src/components/layout/sidebar.tsx` — navigation sidebar (scans, settings, policies, users)
- `frontend/src/components/layout/header.tsx` — top bar with user info + logout

**Acceptance criteria:**
- Unauthenticated user redirected to /login
- Login with email/password works
- GitHub OAuth button redirects and returns authenticated
- Authenticated user sees sidebar navigation
- Logout clears session and redirects to /login

**QA scenario:**
- Tool: Playwright E2E
- Steps: (1) Navigate to / without auth → redirected to /login. (2) Fill email + password, submit → redirected to /scans, sidebar visible with "Scans", "Settings", "Policies", "Users" links. (3) Click logout in header → redirected to /login. (4) Verify GitHub OAuth button has href to /api/auth/github/login. (5) Verify sidebar shows "Settings", "Policies", "Users" only for superuser; viewer sees only "Scans".

## Phase 4: Frontend Features

### Commit 13: Scan management dashboard
**Files to create:**
- `frontend/src/routes/scans/index.tsx` — scan list with DataTable, pagination, filters
- `frontend/src/routes/scans/$scanId.tsx` — scan detail (replaces Jinja2 scan_detail.html)
  - Run overview, decision section, findings grouped by blocking/advisory
  - Severity badges, classification explanations (same logic as current Jinja2 template)
- `frontend/src/hooks/use-scans.ts` — TanStack Query hooks for scan CRUD
- `frontend/src/components/scan/` — ScanCard, FindingCard, VerdictBadge, SeverityBadge

**Acceptance criteria:**
- Scan list loads with pagination
- Filters by repo, state, kind
- Scan detail shows all information from current Jinja2 template
- Blocking findings grouped by severity vs policy (same as current UI)
- Superuser sees trigger/cancel/delete buttons; viewer does not
- Viewers can access scan list and detail

**QA scenario:**
- Tool: Playwright E2E
- Steps: (1) Login as viewer, navigate to /scans → DataTable visible with scan rows. (2) Click a scan row → /scans/{id} opens with run overview, decision, findings. (3) Verify blocking findings split into "By Severity" (HIGH/CRITICAL) and "By Policy" (category match) groups. (4) Verify no "Trigger Scan" / "Delete" / "Cancel" buttons visible for viewer. (5) Login as superuser → "Trigger Scan" button visible, clicking it opens dialog. (6) Test pagination: verify page 2 link works when >20 scans exist. (7) Test filter: select repo filter → list narrows.

### Commit 14: Settings management page
**Files to create:**
- `frontend/src/routes/settings.tsx` — settings form
  - Grouped sections: LLM, Collectors, Limits, Observability
  - Each setting shows: current value, source (env/db), description
  - Save button, reset to env defaults button
- `frontend/src/hooks/use-settings.ts` — TanStack Query hooks
- Superuser-only (sidebar item hidden for viewers)

**Acceptance criteria:**
- Shows all operational settings with current values
- Indicates source (env default vs DB override)
- Save validates and persists to DB
- Reset removes DB override, reverts to env value (uses DELETE /api/admin/settings/{key})
- Viewer cannot access (redirect or 403 page)

**QA scenario:**
- Tool: Playwright E2E
- Steps: (1) Login as viewer, navigate to /settings → redirected away or 403 page. (2) Login as superuser, navigate to /settings → form visible with grouped sections (LLM, Collectors, Limits). (3) Each setting shows current value and source badge ("env" or "db"). (4) Change llm_classify_model to "gpt-4o", click Save → success toast, source badge changes to "db". (5) Click "Reset" on that setting → source badge reverts to "env", value shows original default. (6) Enter invalid value (e.g., negative number for max_tokens), click Save → validation error shown.

### Commit 15: Policy YAML editor
**Files to create:**
- `frontend/src/routes/policies/index.tsx` — policy list
- `frontend/src/routes/policies/$name.tsx` — policy editor with Monaco editor
  - YAML syntax highlighting
  - Client-side YAML validation
  - Server-side PolicyConfig schema validation on save
  - ETag-based conflict detection (shows diff if conflict)
- `frontend/src/hooks/use-policies.ts` — TanStack Query hooks with ETag handling
- Superuser-only

**Acceptance criteria:**
- Monaco editor loads with YAML content
- Syntax errors highlighted in editor
- Save sends PUT with If-Match ETag
- 409 conflict shows user the server version, allows merge/overwrite
- Create new per-repo policy override
- Delete returns to list

**QA scenario:**
- Tool: Playwright E2E
- Steps: (1) Login as superuser, navigate to /policies → list shows "default" policy. (2) Click "default" → Monaco editor opens with YAML content. (3) Edit YAML (change max_inline_comments to 50), click Save → success toast. (4) Open policy in two tabs, edit in tab A and save, then save in tab B → tab B shows 409 conflict dialog with server version diff. (5) Click "Create Policy" → dialog to enter name (e.g., "kylecui/test-repo"), editor opens blank. (6) Enter invalid YAML, click Save → error message with parse details. (7) Click Delete on a policy → confirm dialog → redirected to list, policy removed.

### Commit 16: User management page
**Files to create:**
- `frontend/src/routes/users/index.tsx` — user list with DataTable
- `frontend/src/routes/users/$userId.tsx` — user edit form
- `frontend/src/components/user/create-user-dialog.tsx` — create user modal
- `frontend/src/hooks/use-users.ts` — TanStack Query hooks
- Superuser-only

**Acceptance criteria:**
- User list shows email, name, role, status, GitHub linked
- Create user with email + password + role
- Edit user: toggle active, toggle superuser, change name
- Cannot deactivate yourself
- Cannot remove your own superuser role

**QA scenario:**
- Tool: Playwright E2E
- Steps: (1) Login as superuser, navigate to /users → DataTable with columns: Email, Name, Role (admin/viewer), Status (active/inactive), GitHub. (2) Click "Create User" → dialog with email, password, name, role toggle. Fill and submit → new user in list. (3) Click a user row → edit form. Toggle is_superuser on → save → role column updates. (4) Try to toggle own is_superuser off → error message "Cannot remove own superuser role". (5) Try to deactivate own account → error message "Cannot deactivate yourself".

## Phase 5: Integration & Deployment

### Commit 17: Multi-stage Docker build
**Files to modify:**
- MODIFY `Dockerfile` — add Node.js/bun build stage before Python stage
  - Stage 1: node:22-slim, copy frontend/, bun install, bun run build
  - Stage 2: existing python:3.12-slim, COPY --from=frontend-build /app/frontend/dist /app/static
- MODIFY `docker-compose.yml` — if needed for build args
- MODIFY `.dockerignore` — add frontend/node_modules

**Acceptance criteria:**
- `docker compose build` succeeds
- Production image does NOT contain Node.js or node_modules
- Static files present at /app/static/ in container

**QA scenario:**
- Tool: shell commands
- Steps: (1) `docker compose build app` → exit 0. (2) `docker run --rm code-review-agent-app which node` → exit non-0 (node not found). (3) `docker run --rm code-review-agent-app ls /app/static/index.html` → exit 0. (4) `docker run --rm code-review-agent-app ls /app/static/assets/` → lists .js and .css files. (5) Image size < 500MB (verify with `docker images`).

### Commit 18: SPA static serving from FastAPI
**Files to modify:**
- MODIFY `src/agent_review/config.py` — add `frontend_dir: Path = Path("./static")`
- MODIFY `src/agent_review/app.py`:
  - Remove Jinja2 web_router import/include
  - Add StaticFiles mount at "/" with html=True (MUST be last mount)
- DELETE `src/agent_review/web/routes.py` — replaced by SPA
- DELETE `src/agent_review/templates/` — replaced by SPA (keep templates needed for email/reports if any)
- NEW `tests/integration/test_spa_serving.py` — verify:
  - GET /api/scan returns JSON (not index.html)
  - GET /webhooks/github returns proper response (not index.html)
  - GET /health returns JSON
  - GET /any-unknown-path returns index.html (SPA catch-all)

**Acceptance criteria:**
- SPA loads at /
- All /api/* routes return JSON, not index.html
- /webhooks/github works without auth
- /health and /ready work
- Unknown paths return index.html for client-side routing
- Existing 171+ backend tests still pass

**QA scenario:**
- Tool: pytest with httpx AsyncClient
- Steps: (1) GET / → 200, content-type text/html, body contains `<div id="root">`. (2) GET /api/scan with JSON body → response content-type is application/json (not text/html). (3) GET /health → 200 {"status":"ok"}. (4) GET /ready → 200 {"status":"ready"}. (5) POST /webhooks/github with valid HMAC → 200 (not 404 or index.html). (6) GET /admin/nonexistent → 200, text/html with `<div id="root">` (SPA catch-all). (7) Full test suite `make check` → exit 0, 171+ tests pass.

### Commit 19: CI pipeline for frontend
**Files to create/modify:**
- MODIFY `.github/workflows/ci.yml` (or create if doesn't exist):
  - Job: frontend-check — bun install, bun run lint, bun run type-check, bun run test, bun run build
  - Job: backend-check — make check (existing)
  - Both jobs must pass for PR merge

**Acceptance criteria:**
- CI workflow file is valid YAML and defines two jobs: backend-check and frontend-check
- backend-check job runs: `make check` (ruff, mypy, pytest)
- frontend-check job runs: `bun install`, `bun run lint`, `bun run type-check`, `bun run test`, `bun run build`
- Both jobs use appropriate runtimes (Python 3.12 for backend, Node/bun for frontend)
- Jobs run in parallel (no dependency between them)

**QA scenario:**
- Tool: shell + `act` (local CI runner) or manual verification
- Steps: (1) Verify `.github/workflows/ci.yml` parses as valid YAML. (2) Verify "backend-check" job has steps: checkout, setup-python, install deps, `make check`. (3) Verify "frontend-check" job has steps: checkout, setup-bun, `bun install`, `bun run lint`, `bun run type-check`, `bun run test`, `bun run build`. (4) Verify neither job has `needs:` referencing the other (parallel). (5) `cd frontend && bun run lint && bun run type-check && bun run test && bun run build` → all exit 0. (6) `make check` → exit 0.

### Commit 20: Documentation update
**Files to modify:**
- MODIFY `README.md` — add admin dashboard section to both EN and ZH
- MODIFY `docs/user-guide.md` — add sections for:
  - First-time setup (create initial admin user)
  - GitHub OAuth configuration
  - Admin dashboard features overview
  - Settings management
  - Policy editor
  - User management
- MODIFY `HOW-TO.md` — add admin-related instructions
- MODIFY `.env.example` — add all new env vars with comments

**Acceptance criteria:**
- README has admin dashboard section in both English and Chinese
- User guide has complete instructions for first-time setup, OAuth config, and all admin features
- .env.example includes: SECRET_KEY, GITHUB_OAUTH_CLIENT_ID, GITHUB_OAUTH_CLIENT_SECRET, CORS_ORIGINS
- All new env vars have inline comments explaining their purpose

**QA scenario:**
- Tool: manual review + grep
- Steps: (1) grep README.md for "admin" → sections exist in both English and Chinese blocks. (2) grep docs/user-guide.md for "GitHub OAuth" → configuration section exists. (3) grep .env.example for AGENT_REVIEW_SECRET_KEY, AGENT_REVIEW_CORS_ORIGINS → both present with comments. (4) Verify no broken markdown links (`docs/user-guide.md` references valid anchors).

## Key Technical Decisions

### Auth middleware strategy
- Router-level Depends(), NOT global middleware
- /webhooks/github stays auth-free (HMAC-only)
- /health, /ready stay auth-free
- /api/auth/* public (login, register, oauth)
- /api/admin/* requires auth, some routes require superuser

### Config snapshot semantics
- Pipeline runners snapshot settings at scan start
- Runtime config changes take effect for NEW scans only
- In-flight scans use the config they started with

### Policy conflict resolution
- ETag (sha256 of content) for optimistic locking
- PUT requires If-Match header for existing policies
- 409 response includes current server content for client-side resolution

### SPA catch-all route ordering
- API routes registered FIRST in create_app()
- StaticFiles mount registered LAST
- Integration test verifies /api/* returns JSON, not index.html

### First user bootstrap
- POST /api/auth/register creates first user as superuser if no users exist
- Subsequent registrations create viewer accounts
- Superuser can promote viewers to admin

## Dependencies to Add

### Python (pyproject.toml)
- `pwdlib[argon2,bcrypt]` — password hashing
- `authlib` — GitHub OAuth
- `itsdangerous` — session signing for OAuth CSRF state

### Frontend (frontend/package.json)
- react, react-dom (v19)
- @tanstack/react-router, @tanstack/react-query
- tailwindcss (v4), @shadcn/ui
- @hey-api/openapi-ts — API client generation
- @monaco-editor/react — YAML editor
- vite, vitest, @playwright/test
