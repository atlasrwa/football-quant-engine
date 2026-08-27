# Phase 3.4 API Contract

## Broadcasts

### POST /api/v1/broadcasts

Create and dispatch a prediction broadcast.

**Request:**
```json
{
  "prediction_id": "uuid",
  "channel": "web|mobile|telegram|discord|email|webhook",
  "destination": "optional-channel-address"
}
```

**Headers:** `Authorization: Bearer <token>`, optional `Idempotency-Key`

**Trust Gate:** Prediction must belong to a PROMOTED strategy version.

**Server-Derived (NOT accepted from client):**
- payload_hash
- deep_link
- proof_hash
- fdr_validated
- closing_odds
- settlement outcome

**Response (201):**
```json
{
  "broadcast": {
    "id": "uuid",
    "user_id": "uuid",
    "prediction_id": "uuid",
    "channel": "web",
    "destination": null,
    "status": "DELIVERED",
    "payload_hash": "64-char-hex",
    "deep_link": "/predictions/{id}",
    "dispatched_at": "iso8601",
    "error_code": null,
    "error_message": null,
    "created_at": "iso8601"
  }
}
```

### GET /api/v1/broadcasts/{id}

Get broadcast status by ID.

**Response (200):** Same as above.

### GET /api/v1/predictions/{id}/broadcasts

Get all broadcasts for a prediction.

**Response (200):**
```json
{
  "broadcasts": [...]
}
```

---

## Attestations

### POST /api/v1/attestations/commit

Create a server-generated attestation commitment.

**Request:**
```json
{
  "prediction_id": "uuid"
}
```

**Constraints:**
- Must be called BEFORE prediction is settled
- commitment_hash is server-computed (never client-supplied)

**Response (201):**
```json
{
  "commitment": {
    "id": "uuid",
    "prediction_id": "uuid",
    "commitment_hash": "64-char-hex",
    "created_at": "iso8601",
    "chain_id": null,
    "contract_address": null,
    "tx_hash": null,
    "block_number": null
  }
}
```

### POST /api/v1/attestations/{commitment_id}/reveal

Create an attestation reveal after settlement.

**Request:**
```json
{
  "prediction_id": "uuid"
}
```

**Constraints:**
- Must be called AFTER prediction is settled
- Requires existing commitment
- outcome, closing_odds, P&L, CLV are server-derived from settlement

**Response (201):**
```json
{
  "reveal": {
    "id": "uuid",
    "commitment_id": "uuid",
    "prediction_id": "uuid",
    "settlement_id": "uuid",
    "reveal_payload": { ... },
    "reveal_hash": "64-char-hex",
    "created_at": "iso8601",
    "chain_id": null,
    "contract_address": null,
    "tx_hash": null,
    "block_number": null
  }
}
```

### GET /api/v1/attestations/{commitment_id}

Get attestation status by commitment ID.

### GET /api/v1/predictions/{id}/attestation

Get full attestation provenance (commitment + reveal if exists).

**Response (200):**
```json
{
  "attestation": {
    "commitment_id": "uuid",
    "prediction_id": "uuid",
    "commitment_hash": "64-char-hex",
    "committed_at": "iso8601",
    "reveal_id": "uuid|null",
    "settlement_id": "uuid|null",
    "reveal_payload": { ... } | null,
    "reveal_hash": "64-char-hex|null",
    "revealed_at": "iso8601|null",
    "commitment_chain_id": null,
    "reveal_chain_id": null
  }
}
```

## Error Responses

All errors follow the platform standard:
```json
{
  "error": {
    "code": "BUSINESS_RULE_VIOLATION",
    "message": "Human-readable description"
  }
}
```

| Code | Status | Meaning |
|------|--------|---------|
| BUSINESS_RULE_VIOLATION | 422 | Trust gate failed, lifecycle violation |
| NOT_FOUND | 404 | Resource not found |
| UNAUTHENTICATED | 401 | Missing/invalid token |
