# Phase 3.1 Security Model

## Table Ownership Classification

| Table | Class | Owner | RLS Forced | Rationale |
|-------|-------|-------|------------|-----------|
| `users` | A (User-owned) | Each user owns their row | Yes | Identity data; users see only themselves; admins see all |
| `user_wallets` | A (User-owned) | FK to user | Yes | Wallet cannot silently move between users |
| `strategies` | A (User-owned) | `owner_id` FK | Yes | Creator owns; public strategies readable by all |
| `strategy_versions` | A (User-owned via parent) | Inherits from strategy | Yes | Visibility derived from parent strategy |
| `strategy_forks` | A (User-owned) | `forked_by` FK | Yes | Fork creator + admins + public-linked users |
| `matches` | B (System-owned) | System/admin only write | Yes | All authenticated users can read; only ingestion writes |
| `event_log` | B (System-owned) | Append-only | Yes | All can read own events; no update/delete |
| `idempotency_keys` | A (User-owned) | `user_id` PK component | Yes | Scoped per user; 24h TTL |

## RLS Policies Summary

### users
- **SELECT**: Own row OR admin/system
- **INSERT**: System-controlled (registration flow)
- **UPDATE**: Own row OR admin/system

### strategies
- **SELECT**: Owner OR public visibility OR admin/system
- **INSERT**: Only if `owner_id = current_user` OR admin/system
- **UPDATE**: Owner OR admin/system

### strategy_versions
- **SELECT**: Visible if parent strategy visible
- **INSERT**: Only if parent strategy owner OR admin/system
- **UPDATE**: Only if parent strategy owner OR admin/system (deprecation only)

### strategy_forks
- **SELECT**: Fork creator OR admin OR linked strategy visible
- **INSERT**: Only if `forked_by = current_user` OR admin/system

### matches
- **SELECT**: All authenticated users (public data)
- **INSERT/UPDATE**: Admin/system only

### event_log
- **SELECT**: All authenticated (audit trail is readable)
- **INSERT**: Application layer only
- **UPDATE/DELETE**: Blocked by trigger + no RLS policy

### idempotency_keys
- **SELECT/INSERT/DELETE**: Own keys OR admin/system

## Authentication Flow

1. Client sends `Authorization: Bearer <JWT>` header
2. `get_current_user` dependency extracts and validates token
3. Token claims: `sub` (user_id UUID), `role` (user/creator/admin/system)
4. `AuthContext(user_id, role)` is injected into route handlers
5. Route handler sets `SET LOCAL app.user_id/app.user_role` inside transaction
6. All subsequent queries execute within RLS context

## Trust Boundaries

| Boundary | Rule |
|----------|------|
| User identity | Derived from verified JWT `sub` claim only; NEVER from request body |
| Owner attribution | `owner_id` set from `ctx.user_id`; NEVER from client input |
| Content hash | Computed server-side by `compute_content_hash()`; NEVER accepted from client |
| Strategy definition | Immutable after version creation; trigger-enforced |
| Fork lineage | Immutable after creation; trigger-enforced |
| Event actor | Derived from authenticated context; NEVER client-supplied |
| Idempotency scope | Keyed by `(user_id, key)`; users cannot access other users' keys |

## Immutability Enforcement

| Table | Mutable Fields | Enforcement |
|-------|---------------|-------------|
| `strategy_versions` | `is_deprecated`, `deprecated_at` | Trigger: `enforce_strategy_version_immutability()` |
| `strategies.owner_id` | Never | Trigger: `enforce_strategy_owner_immutability()` |
| `strategy_forks` | None | Triggers: `prevent_fork_mutation()` (UPDATE + DELETE) |
| `event_log` | None | Triggers: `prevent_event_log_mutation()` (UPDATE + DELETE) + no RLS UPDATE/DELETE policy |

## Database Roles

| Role | Purpose | Permissions |
|------|---------|-------------|
| `fqe_app` | Application service account | ALL on all tables (RLS enforces row-level isolation) |
| `postgres` | Superuser (admin) | Bypasses RLS |
