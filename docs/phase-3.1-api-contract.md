# Phase 3.1 API Contract

## Base URL
```
http://localhost:8000
```

## Authentication
All authenticated endpoints require:
```
Authorization: Bearer <JWT>
```

JWT payload: `{"sub": "<user_id>", "role": "<role>", "exp": <timestamp>}`

## Common Headers

| Header | Required | Purpose |
|--------|----------|---------|
| `Authorization` | Yes (except health/register/login) | Bearer JWT token |
| `Idempotency-Key` | Optional (POST endpoints) | Client-supplied dedup key (24h TTL) |
| `X-Request-ID` | Optional | Correlation ID (auto-generated if absent) |

## Error Response Format
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description",
    "details": {}
  },
  "request_id": "correlation-uuid"
}
```

## Endpoints

### Health
```
GET /health → 200 {"status": "ok", "service": "football-quant-engine"}
```

---

### Auth

#### Register
```
POST /api/v1/auth/register
Body: {"username", "email?", "display_name", "password"}
→ 201 {"user": {id, username, email, display_name, role, status, created_at}}
→ 409 CONFLICT (duplicate username/email)
```

#### Login
```
POST /api/v1/auth/login
Body: {"username", "password"}
→ 200 {"access_token", "token_type": "bearer", "user": {...}}
→ 401 UNAUTHENTICATED (bad credentials)
→ 403 FORBIDDEN (disabled account)
```

#### Get Current User
```
GET /api/v1/users/me
Auth: Required
→ 200 {"user": {id, username, email, display_name, role, status, avatar_url, bio, created_at}}
→ 401 UNAUTHENTICATED
```

---

### Strategies

#### Create Strategy
```
POST /api/v1/strategies
Auth: Required
Headers: Idempotency-Key (optional)
Body: {
  "name": string (1-200 chars),
  "description?": string,
  "metric": "xC" | "xB" | "xO",
  "market": string,
  "conditions": [{"field", "op", "value"}],
  "logic": "and" | "or",
  "direction": "OVER" | "UNDER" | "BACK" | "LAY",
  "min_odds": float > 1.0,
  "visibility": "private" | "public" | "unlisted"
}
→ 201 {"strategy": {...}, "version": {...}}
→ 409 CONFLICT (duplicate definition)
→ 409 IDEMPOTENCY_CONFLICT (key reused with different body)
```

#### Get Strategy
```
GET /api/v1/strategies/{strategy_id}
Auth: Required
→ 200 {"strategy": {id, owner_id, name, description, visibility, status, created_at}}
→ 404 NOT_FOUND (or private + not owner)
```

#### Get Strategy Version
```
GET /api/v1/strategies/{strategy_id}/versions/{version}
Auth: Required
→ 200 {"version": {id, strategy_id, version, definition, content_hash, created_by, is_deprecated, created_at}}
→ 404 NOT_FOUND
```

#### Update Visibility
```
PATCH /api/v1/strategies/{strategy_id}/versions/{version}/visibility
Auth: Required (owner only)
Body: {"visibility": "private" | "public" | "unlisted"}
→ 200 {"strategy": {...}}
→ 403 FORBIDDEN (not owner)
→ 404 NOT_FOUND
```

#### Fork Strategy
```
POST /api/v1/strategies/{strategy_id}/fork
Auth: Required
Body: {"source_version?": int, "name?": string, "description?": string}
→ 201 {"strategy": {...}, "version": {...}, "fork_source": {strategy_id, version, content_hash}}
→ 404 NOT_FOUND (source not visible)
```

---

## Error Codes

| Code | HTTP | Meaning |
|------|------|---------|
| VALIDATION_ERROR | 400 | Request body validation failed |
| UNAUTHENTICATED | 401 | Missing or invalid token |
| FORBIDDEN | 403 | Authenticated but not authorized |
| NOT_FOUND | 404 | Resource does not exist (or hidden by RLS) |
| CONFLICT | 409 | Resource already exists |
| IDEMPOTENCY_CONFLICT | 409 | Same key used with different request |
| BUSINESS_RULE_VIOLATION | 422 | Valid request but violates domain rule |
| INTERNAL_ERROR | 500 | Unexpected server error (details hidden) |
