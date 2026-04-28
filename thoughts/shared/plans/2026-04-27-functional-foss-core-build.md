---
date: 2026-04-27 15:12:45 PDT
git_commit: e0ea63d7b90ccb6ad20f0dc0aa80a31f6a616f73
branch: master
repository: posthog-foss
last_updated: 2026-04-27
---

# Functional FOSS Core Build Implementation Plan

## Overview

Make this repository build and boot as a true FOSS PostHog distribution from the repo root, without an `ee/` directory and without relying on the hobby deployment wrapper.
The implementation should disable or degrade EE-only behavior cleanly while preserving core FOSS analytics services.

## Current State Analysis

The repository currently contains FOSS-visible build, startup, model, and migration paths that assume Enterprise Edition files exist.
The first Docker error is `COPY ee ee/`, but the deeper issue is that Django app state and several installed product modules still reference missing `ee` modules and models.

### Key Discoveries

- `Dockerfile:151` and `Dockerfile:350` unconditionally copy `ee`, so `docker build -f Dockerfile .` fails in a clean FOSS checkout.
- `posthog/models/organization_invite.py:20` imports `ee.models.rbac.access_control.AccessControl` at module import time, which breaks `collectstatic` after users fake an empty `ee/` directory.
- `posthog/settings/web.py:225-237` includes `ee.api.authentication.social_auth_allowed` in the social auth pipeline even when EE is absent.
- `posthog/settings/web.py:397-398` references `ee.models.assistant.Conversation` enum paths in OpenAPI settings.
- `posthog/user_permissions.py:116` and `posthog/user_permissions.py:139` import EE access-control models in cached properties that are reachable when organizations have advanced permissions data.
- `products/conversations/backend/api/tickets.py:57` imports `ee.models.rbac.role.Role` at module import time.
- `products/conversations/backend/api/tickets.py:181-185` uses `select_related("assignment__role")`, which requires a real role relation.
- `products/error_tracking/backend/api/issues.py:405-409` imports `ee.models.rbac.role.Role` for role assignment validation.
- `posthog/models/organization.py:211-218` defines `default_role` as a `ForeignKey("ee.Role")`.
- `posthog/models/role_external_reference.py:31-35` defines `role` as a `ForeignKey("ee.Role")`.
- `products/error_tracking/backend/models.py:146`, `:254`, and `:302` define role relationships as `ForeignKey("ee.Role")`.
- `products/conversations/backend/models/assignment.py:9` defines `role` as a `ForeignKey("ee.Role")`.
- `products/signals/backend/models.py:161-163` defines deprecated `conversation` as a `ForeignKey("ee.Conversation")`.
- Fresh FOSS migrations depend on EE at `posthog/migrations/0829_organization_default_role.py:9`, `posthog/migrations/0993_approvalpolicy_bypass_options.py:5`, `posthog/migrations/1117_role_external_reference.py:12`, `products/error_tracking/backend/migrations/0001_migrate_error_tracking_models.py:16`, `products/conversations/backend/migrations/0013_ticket_assignment.py:11`, and `products/signals/backend/migrations/0001_initial.py:12`.
- `docker-compose.hobby.yml` is not an acceptable target because it assumes the wrapper layout and pulls in the hobby deployment path.
- `docker-compose.base.yml:476-482` runs Django and ClickHouse migrations, so any repo-root FOSS compose target must prove both migration paths work without EE.

## Desired End State

A clean clone of this repository can build and boot core FOSS services from the repo root without creating an `ee/` directory.

The desired target is not hobby deployment.
It is a repo-root FOSS compose target that builds local images and starts the core open-source stack: Postgres, Redis, ClickHouse, Kafka/Redpanda, the Django web image, Celery worker, plugin/ingestion Node services, capture services, feature flags, replay ingestion, object storage, and required migration jobs.

### Verification Summary

- `docker build -t local/posthog-foss:local -f Dockerfile .` succeeds from the repo root with no `ee/` directory present.
- A new repo-root compose file, `docker-compose.foss.yml`, validates with `docker compose -f docker-compose.foss.yml config`.
- FOSS compose builds the app, node, and Rust service images from repo-root paths.
- Django starts far enough to run `collectstatic`, `check`, and `migrate` without `ee`.
- Fresh Postgres migrations apply without dependencies on the missing `ee` Django app.
- Runtime requests to EE-only features return disabled or unsupported behavior instead of crashing on `ModuleNotFoundError`.

## What We're NOT Doing

- Not supporting or fixing `docker-compose.hobby.yml` or the hobby deployment wrapper.
- Not creating fake `ee` packages, placeholder `ee.models`, `.gitkeep` hacks, or stub Enterprise models.
- Not preserving role-based access control, advanced permissions, Enterprise billing limits, Max AI, session summaries, or other EE-only product behavior.
- Not preserving compatibility with a separate proprietary checkout containing real `ee` code.
- Not keeping migrations compatible with upstream proprietary migration history where that conflicts with fresh FOSS installability.
- Not solving every optional product feature that imports `ee` in code that is never reached during core boot. Those should be triaged after core build and migration are green.
- Not enabling PostHog telemetry, sourcemap upload secrets, or hobby deployment telemetry paths.

## Implementation Approach

Use explicit FOSS behavior instead of pretending EE exists.
Where a field only needs to preserve an existing database column name, replace hard `ForeignKey("ee.*")` relationships with nullable scalar UUID fields named with the existing column, such as `role_id` and `conversation_id`.

For runtime features that depend on EE models, validate user assignments only and reject or ignore role assignments in FOSS.
For permissions and access-control code, no-op advanced access-control paths when EE is unavailable.

Rewrite FOSS migration history where needed so a fresh database can apply migrations without an `ee` Django app.
This fork is allowed to diverge from upstream migration history to make clean FOSS installation possible.

Add a repo-root `docker-compose.foss.yml` that builds from `.` and excludes the hobby wrapper assumptions.
Reuse existing base service definitions only when they do not force wrapper paths or hobby behavior.

## Phase 1: Make Docker Image FOSS-Safe

### Overview

Remove hard Docker build dependency on the missing `ee/` directory and ensure Django static collection can start in a clean checkout.

### Changes Required

#### 1. Main Application Dockerfile

**File**: `Dockerfile`

**Changes**:
- Remove `COPY ee ee/` from the `posthog-build` stage.
- Remove `COPY --chown=posthog:posthog ee ee/` from the final runtime stage.
- Keep copying `posthog/`, `products/`, `common/`, `manage.py`, frontend assets, Python runtime, and plugin transpiler artifacts.
- Optionally normalize legacy Docker `ENV` syntax while touching the file, but do not let formatting cleanups expand scope.

```dockerfile
# FOSS builds must not require Enterprise Edition sources.
COPY posthog posthog/
COPY products/ products/
```

#### 2. Docker Ignore Rules

**File**: `.dockerignore`

**Changes**:
- Remove `!ee` and `ee/**/node_modules` entries if they become misleading.
- Keep build context narrow for repo-root builds.

### Success Criteria

#### Automated Verification

- [x] Repo contains no `ee/` directory: `test ! -d ee`
- [ ] Main app image build starts without Docker checksum errors: `docker build -t local/posthog-foss:local -f Dockerfile .`
- [ ] Build does not fail at `COPY ee ee/`.

#### Manual Verification

- [ ] Dockerfile remains readable and clearly communicates that FOSS builds do not require Enterprise sources.

**Implementation Note**: After this phase, a build may still fail during Django startup. That is expected until Phase 2 and Phase 3 are complete.

## Phase 2: Remove Django Startup Dependencies on EE

### Overview

Make `django.setup()`, `collectstatic`, and URL import succeed without `ee`.
Focus only on import-time and always-reachable startup paths first.

### Changes Required

#### 1. Organization Invite Access-Control Creation

**File**: `posthog/models/organization_invite.py`

**Changes**:
- Remove the module-level `from ee.models.rbac.access_control import AccessControl` import.
- In `OrganizationInvite.use`, only create project access-control rows when EE is available.
- In FOSS, ignore `private_project_access` rows after validating the invite and creating the membership.
- Keep product-list sync using `UserAccessControl`, which should no-op EE access controls when unavailable.

```python
if self.private_project_access:
    try:
        from ee.models.rbac.access_control import AccessControl
    except ImportError:
        AccessControl = None

    if AccessControl is not None:
        # existing row creation logic
```

#### 2. Social Auth Pipeline

**File**: `posthog/settings/web.py`

**Changes**:
- Build `SOCIAL_AUTH_PIPELINE` so `ee.api.authentication.social_auth_allowed` is only included when EE is importable.
- Keep the existing non-EE social auth pipeline intact.

```python
SOCIAL_AUTH_PIPELINE = (
    "social_core.pipeline.social_auth.social_details",
    "social_core.pipeline.social_auth.social_uid",
    "social_core.pipeline.social_auth.auth_allowed",
    *(["ee.api.authentication.social_auth_allowed"] if EE_AVAILABLE else []),
    ...
)
```

#### 3. OpenAPI Enum Overrides

**File**: `posthog/settings/web.py`

**Changes**:
- Remove or conditionally include `ConversationStatus` and `ConversationType` enum overrides pointing to `ee.models.assistant.Conversation`.
- FOSS OpenAPI generation must not import missing EE model paths.

#### 4. User Permissions

**File**: `posthog/user_permissions.py`

**Changes**:
- Import `EE_AVAILABLE` from settings.
- Return `{}` from `_prefetched_access_controls` and `_prefetched_role_memberships` when EE is not available.
- Leave dashboard privileges as `{}` when EE is absent.
- Do not import `AccessControl` or `RoleMembership` when `EE_AVAILABLE` is false.

```python
if not EE_AVAILABLE:
    return {}
```

#### 5. Conversations Ticket API

**File**: `products/conversations/backend/api/tickets.py`

**Changes**:
- Remove module-level `Role` import.
- Avoid `select_related("assignment__role")` after the model relation is converted to a scalar field in Phase 3.
- In FOSS, reject `assignee.type == "role"` with a validation error such as `role assignees are not supported in FOSS`.
- Keep user assignment behavior intact.

#### 6. Error Tracking Issue Assignment

**File**: `products/error_tracking/backend/api/issues.py`

**Changes**:
- In FOSS, reject `assignee.type == "role"` before importing `Role`.
- Keep user assignment behavior intact.

### Success Criteria

#### Automated Verification

- [ ] Django import check succeeds without EE: `SKIP_SERVICE_VERSION_REQUIREMENTS=1 DATABASE_URL='postgres:///' REDIS_URL='redis:///' python manage.py check --deploy --fail-level ERROR`
- [ ] Static collection succeeds without EE: `SKIP_SERVICE_VERSION_REQUIREMENTS=1 STATIC_COLLECTION=1 DATABASE_URL='postgres:///' REDIS_URL='redis:///' python manage.py collectstatic --noinput`
- [x] Python import scan shows no module-level `from ee` imports in core startup modules touched by this phase.

#### Manual Verification

- [ ] Accepting an invite without private project access still creates an organization membership.
- [ ] Role assignment attempts in Conversations and Error tracking return clear unsupported validation errors instead of 500s.

**Implementation Note**: Pause after this phase if `django.setup()` still fails, because any remaining failure should be classified as either a model-state issue for Phase 3 or a separate import-time dependency.

## Phase 3: Convert FOSS Models Away From Missing EE Relations

### Overview

Remove hard Django model dependencies on `ee.Role` and `ee.Conversation` while preserving existing database column names and FOSS behavior.

### Changes Required

#### 1. Organization Default Role

**File**: `posthog/models/organization.py`

**Changes**:
- Replace `default_role = models.ForeignKey("ee.Role", ...)` with `default_role_id = models.UUIDField(null=True, blank=True, db_index=True, ...)`.
- Update any code using `organization.default_role_id` to keep working.
- Do not expose or resolve a `default_role` object in FOSS.

```python
default_role_id = models.UUIDField(
    null=True,
    blank=True,
    db_index=True,
    help_text="Role automatically assigned to new members joining the organization when EE is available.",
)
```

#### 2. Role External Reference

**File**: `posthog/models/role_external_reference.py`

**Changes**:
- Replace `role = models.ForeignKey("ee.Role", ...)` with `role_id = models.UUIDField()`.
- Keep constraints on external provider fields.
- Consider whether this model should remain imported by `posthog/models/__init__.py`; it can remain if scalar-only.

#### 3. Error Tracking Role Columns

**File**: `products/error_tracking/backend/models.py`

**Changes**:
- Replace role FKs in `ErrorTrackingIssueAssignment`, `ErrorTrackingAssignmentRule`, and `ErrorTrackingGroupingRule` with scalar `role_id = models.UUIDField(null=True, blank=True)`.
- Preserve `role_id` column names so serializers and ClickHouse sync can still report assigned role IDs when old data exists.
- Remove any ORM usage expecting `assignment.role` relation.

#### 4. Conversations Ticket Assignment Role Column

**File**: `products/conversations/backend/models/assignment.py`

**Changes**:
- Replace `role = models.ForeignKey("ee.Role", ...)` with scalar `role_id = models.UUIDField(null=True, blank=True)`.
- Update the check constraint to reference `role_id__isnull` instead of `role__isnull`.

#### 5. Signals Deprecated Conversation Column

**File**: `products/signals/backend/models.py`

**Changes**:
- Replace deprecated `conversation = ForeignKey("ee.Conversation")` with deprecated scalar `conversation_id = models.UUIDField(null=True, blank=True)`.
- Preserve the existing database column name.

#### 6. Serializers That Read Role Relations

**Files**:
- `products/conversations/backend/api/serializers.py`
- `products/error_tracking/backend/api/utils.py`

**Changes**:
- Ensure assignment serializers no longer require `assignment.role` object traversal.
- Serialize `{"type": "role", "id": str(role_id)}` only if a stored role ID exists.
- In FOSS, new role assignment creation should be blocked by API validation.

### Success Criteria

#### Automated Verification

- [ ] `python manage.py check` succeeds without unresolved model relation errors.
- [ ] `python manage.py makemigrations --check --dry-run` reports no unintended migration drift after migration files are updated in Phase 4.
- [ ] Serializer unit tests or targeted API tests pass for user assignment and unassignment paths.

#### Manual Verification

- [ ] Ticket assignment to a user works.
- [ ] Error tracking issue assignment to a user works.
- [ ] Role IDs in old rows, if present, do not crash serializers.

**Implementation Note**: Do not add new FOSS replacement role models. Scalar IDs are only compatibility storage for existing columns and degraded read behavior.

## Phase 4: Rewrite FOSS Migration History for Fresh Installs

### Overview

Make a clean FOSS database migrate from zero without an `ee` app in `INSTALLED_APPS`.
Because this fork is FOSS-only, rewrite historical migrations that reference EE rather than adding fake app labels.

### Changes Required

#### 1. Organization Default Role Migration

**File**: `posthog/migrations/0829_organization_default_role.py`

**Changes**:
- Remove `("ee", ...)` dependency.
- Change state operation from `ForeignKey(to="ee.role")` to `UUIDField` named `default_role_id`.
- Change database operation to add a nullable UUID column without a foreign key constraint to `ee_role`.
- Keep or recreate the existing index concurrently.

#### 2. Approval Policy Bypass Roles Migration

**File**: `posthog/migrations/0993_approvalpolicy_bypass_options.py`

**Changes**:
- Remove `("ee", ...)` dependency.
- Keep `bypass_org_membership_levels`.
- Remove `bypass_roles` M2M field creation or replace with a FOSS-safe no-op state operation if the model no longer includes it.
- Verify current `ApprovalPolicy` model state before finalizing to avoid migration drift.

#### 3. Role External Reference Migration

**File**: `posthog/migrations/1117_role_external_reference.py`

**Changes**:
- Remove `("ee", ...)` dependency.
- Replace `role` FK field with scalar `role_id = models.UUIDField()`.
- Keep provider lookup indexes and uniqueness constraints.

#### 4. Error Tracking Initial Product Migration

**File**: `products/error_tracking/backend/migrations/0001_migrate_error_tracking_models.py`

**Changes**:
- Remove `("ee", ...)` dependency.
- Replace role FKs with scalar UUID fields named `role_id` in state operations.
- Ensure `SeparateDatabaseAndState` remains correct for moved tables.

#### 5. Conversations Ticket Assignment Migration

**File**: `products/conversations/backend/migrations/0013_ticket_assignment.py`

**Changes**:
- Remove `("ee", ...)` dependency.
- Replace `role` FK with scalar `role_id = models.UUIDField(null=True, blank=True)`.
- Update check constraint from `role__isnull` to `role_id__isnull`.

#### 6. Signals Initial Migration

**File**: `products/signals/backend/migrations/0001_initial.py`

**Changes**:
- Remove `("ee", ...)` dependency.
- Replace `conversation` FK with scalar `conversation_id = models.UUIDField(null=True, blank=True)`.

#### 7. Older PostHog Error Tracking Migrations

**Files**:
- `posthog/migrations/0717_errortrackingassignmentrule_role_and_more.py`
- `posthog/migrations/0724_errortrackinggroupingrule.py`

**Changes**:
- Replace active `to="ee.role"` field additions with nullable scalar UUID fields or no-op state-only operations based on current migration ordering.
- Preserve database column names where those migrations still run before product model migration.

### Success Criteria

#### Automated Verification

- [ ] Fresh Postgres migration succeeds in a clean database: `python manage.py migrate`
- [ ] Product migrations apply without an installed `ee` app.
- [ ] Migration graph validation succeeds: `python manage.py showmigrations posthog error_tracking conversations signals`
- [x] Migration SQL for touched migrations contains no `REFERENCES "ee_role"` and no dependency on `ee.conversation`.
- [ ] `python manage.py makemigrations --check --dry-run` reports no model drift.

#### Manual Verification

- [ ] Inspect migration output to confirm no table or column drops were introduced.
- [ ] Confirm fresh database schema includes scalar `*_role_id`, `default_role_id`, and `conversation_id` columns where needed.

**Implementation Note**: This phase deliberately edits historical migrations because fresh FOSS installability is a requirement and upstream EE migration compatibility is out of scope.

## Phase 5: Add Repo-Root FOSS Compose Target

### Overview

Provide a direct repo-root compose path that does not use hobby deployment and does not require a wrapper directory named `posthog/`.

### Changes Required

#### 1. FOSS Compose File

**File**: `docker-compose.foss.yml`

**Changes**:
- Add a new compose file intended for repo-root use.
- Build the Django image from `.` using `Dockerfile`.
- Build the Node image from `.` using `Dockerfile.node` after auditing it for EE copies.
- Build Rust services from `rust/` using existing args where needed.
- Include core services only:
  - `db`
  - `redis7`
  - `clickhouse`
  - `kafka`
  - `objectstorage` or `seaweedfs` for session recording/object storage
  - `migrate`
  - `web`
  - `worker`
  - `plugins`
  - `ingestion-general`
  - `ingestion-sessionreplay`
  - `recording-api`
  - `capture`
  - `replay-capture`
  - `feature-flags`
  - `property-defs-rs`
- Exclude hobby-only wrapper services and paths.
- Exclude telemetry-oriented or EE/AI-specific services unless required for core boot.
- Set environment defaults for local FOSS boot: `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, `CLICKHOUSE_*`, `KAFKA_HOSTS`, `OBJECT_STORAGE_*`, `ENCRYPTION_SALT_KEYS`, `OTEL_SDK_DISABLED=true`, and `DEPLOYMENT=foss`.

#### 2. FOSS Environment Example

**File**: `.env.foss.example`

**Changes**:
- Document the minimal repo-root environment variables for the FOSS compose target.
- Include no telemetry keys, sourcemap upload secrets, license settings, or hobby deployment variables.

#### 3. Documentation

**File**: `README.md` or `docs/self-host-foss.md`

**Changes**:
- Add a concise FOSS build and boot section.
- Document repo-root commands.
- State explicitly that `docker-compose.hobby.yml` is not the FOSS target.

```bash
docker build -t local/posthog-foss:local -f Dockerfile .
docker compose -f docker-compose.foss.yml build
docker compose -f docker-compose.foss.yml up migrate
docker compose -f docker-compose.foss.yml up web worker plugins ingestion-general
```

### Success Criteria

#### Automated Verification

- [ ] Compose validates: `docker compose -f docker-compose.foss.yml config`
- [ ] Compose build succeeds: `docker compose -f docker-compose.foss.yml build`
- [ ] Migration job exits successfully: `docker compose -f docker-compose.foss.yml up migrate`
- [ ] Core services start: `docker compose -f docker-compose.foss.yml up web worker plugins ingestion-general ingestion-sessionreplay recording-api capture replay-capture feature-flags`
- [ ] Health endpoint returns 200: `curl -fsS http://localhost:8000/_health`

#### Manual Verification

- [ ] User can open the app in a browser and reach the signup/login flow.
- [ ] Basic project creation/onboarding does not crash.
- [ ] Event capture reaches Kafka/ClickHouse and appears in the UI after ingestion.
- [ ] Feature flag endpoint responds for a test project.

**Implementation Note**: Keep `docker-compose.foss.yml` intentionally boring and explicit. Do not try to reuse hobby deployment if it forces wrapper paths or telemetry behavior.

## Phase 6: Triage Remaining EE Imports by Runtime Reachability

### Overview

After core boot works, classify remaining `ee` imports and fix only those reachable by the FOSS core service paths.

### Changes Required

#### 1. Runtime Import Scan

**Files**: all Python files under `posthog/` and `products/`

**Changes**:
- Search for `from ee.` and `import ee`.
- Classify each occurrence as:
  - startup blocker
  - core runtime blocker
  - optional product feature
  - tests only
- Fix startup and core runtime blockers.
- Leave tests and optional product features unless they affect boot or core services.

#### 2. Optional Feature Degradation

**Files**: product APIs and services with EE-only imports

**Changes**:
- Return explicit disabled responses for EE-only capabilities.
- Avoid broad `except Exception` masking for unsupported features.
- Prefer small helper functions where multiple call sites need the same unsupported response.

Examples:
- Max AI tool files can remain unused unless imported by core startup.
- Billing quota checks in data imports should treat missing EE billing limits as unlimited or disabled, depending on the existing non-cloud behavior.
- Session summary Temporal workflows should not be registered in FOSS if they import EE-only modules.

### Success Criteria

#### Automated Verification

- [ ] No `ModuleNotFoundError: No module named 'ee'` appears in logs during core compose boot.
- [ ] `python manage.py check` passes.
- [ ] Core pytest targets for touched modules pass through `hogli test <path>`.
- [x] Import scan report is attached to the PR or implementation notes.

#### Manual Verification

- [ ] Attempting to use known EE-only features produces a clear unsupported/disabled result or remains hidden from core flows.
- [ ] Core analytics, dashboards, replay ingestion, feature flags, and plugin ingestion remain operational.

**Implementation Note**: This is intentionally after compose boot. Do not block the initial FOSS boot on cold code paths unless they are imported by web, worker, migration, or core service startup.

## Testing Strategy

### Unit Tests

- Test `OrganizationInvite.use` without EE and with `private_project_access` data.
- Test `UserPermissions` with `EE_AVAILABLE=False` returns empty access-control and role-membership prefetched maps.
- Test Conversations assignment validation rejects role assignments and accepts user assignments in FOSS.
- Test Error tracking assignment validation rejects role assignments and accepts user assignments in FOSS.
- Test serializers handle scalar `role_id` without dereferencing `role` relations.

### Migration Tests

- Run fresh Postgres migrations from an empty database.
- Verify touched migration SQL contains no `ee_role`, `ee.conversation`, or `REFERENCES "ee_role"`.
- Run `makemigrations --check --dry-run` to confirm model and migration state match.

### Integration Tests

- Build the main Django Docker image from repo root without `ee/`.
- Build FOSS compose services from repo root.
- Run migrations in the FOSS compose stack.
- Start web and worker.
- Send a capture event and verify it is queryable in the UI or API.
- Create a feature flag and verify `/flags` or the feature flags service responds.

### Manual Testing Steps

1. Delete any local `ee/` directory if present.
2. Build the app image from the repo root.
3. Start the FOSS compose stack.
4. Open the web UI and create the first user/org/project.
5. Capture a test event using the project API key.
6. Confirm the event appears in Product analytics.
7. Create a dashboard and insight.
8. Create and evaluate a feature flag.
9. Upload or ingest a test session replay if the local stack supports replay capture.
10. Trigger a role assignment attempt in Conversations or Error tracking and verify the UI/API returns unsupported instead of crashing.

## Performance Considerations

- Replacing FKs with scalar UUID fields removes ORM join capability for role data in FOSS. This is acceptable because role behavior is disabled.
- Avoid broad startup-time scans for optional product modules. Only import optional EE-dependent modules inside guarded paths.
- Keep Docker build cache behavior stable by avoiding unnecessary changes to dependency installation layers.
- Keep compose service count minimal enough for local development while still covering the FOSS core stack.

## Migration Notes

- This fork will edit historical migrations to remove EE dependencies. That is a deliberate divergence because clean FOSS installation is a product requirement.
- Do not drop columns as part of this work. Preserve existing column names with scalar fields.
- For nullable scalar UUID replacements, no data backfill is needed.
- For existing databases that somehow contain EE role IDs in these columns, values remain stored but FOSS will not resolve them to role objects.
- If future upstream migrations reintroduce `ee` dependencies, add a CI guard to catch them before merge.

## CI And Guardrails

Add or document lightweight checks after the core fixes land:

- Search Dockerfiles for unconditional `COPY ee`.
- Search non-test startup paths for module-level `from ee.` imports.
- Search migrations for active `("ee", ...)` dependencies.
- Search model fields for `to="ee.` or `ForeignKey("ee.`.
- Run `docker compose -f docker-compose.foss.yml config` in CI if Docker is available.

## References

- Docker failure: `Dockerfile:151`, `Dockerfile:350`
- Startup import failure: `posthog/models/organization_invite.py:20`
- Social auth EE pipeline: `posthog/settings/web.py:225-237`
- OpenAPI EE enum paths: `posthog/settings/web.py:397-398`
- User permissions EE imports: `posthog/user_permissions.py:116`, `posthog/user_permissions.py:139`
- Conversations role import: `products/conversations/backend/api/tickets.py:57`
- Organization EE role FK: `posthog/models/organization.py:211-218`
- Role external reference EE FK: `posthog/models/role_external_reference.py:31-35`
- Error tracking EE role FKs: `products/error_tracking/backend/models.py:146`, `products/error_tracking/backend/models.py:254`, `products/error_tracking/backend/models.py:302`
- Conversations EE role FK: `products/conversations/backend/models/assignment.py:9`
- Signals EE conversation FK: `products/signals/backend/models.py:161-163`
- Migration blockers: `posthog/migrations/0829_organization_default_role.py`, `posthog/migrations/0993_approvalpolicy_bypass_options.py`, `posthog/migrations/1117_role_external_reference.py`, `products/error_tracking/backend/migrations/0001_migrate_error_tracking_models.py`, `products/conversations/backend/migrations/0013_ticket_assignment.py`, `products/signals/backend/migrations/0001_initial.py`
