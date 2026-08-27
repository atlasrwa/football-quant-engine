"""Integration tests for the FastAPI endpoints.

Tests the full request lifecycle: HTTP → auth → DB → response.
Uses httpx AsyncClient against the real FastAPI app with real PostgreSQL.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.api.app import app


pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client():
    """Provide an async HTTP client bound to the FastAPI app.

    Manually manages pool lifecycle since lifespan doesn't auto-trigger
    with the test transport.
    """
    from src.persistence.database import init_pool, close_pool
    await init_pool()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await close_pool()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Register a test user and return auth headers."""
    import uuid
    username = f"testuser_{uuid.uuid4().hex[:8]}"
    # Register
    resp = await client.post("/api/v1/auth/register", json={
        "username": username,
        "email": f"{username}@test.com",
        "display_name": "Test User",
        "password": "SecurePass123!",
    })
    assert resp.status_code == 201, resp.text

    # Login
    resp = await client.post("/api/v1/auth/login", json={
        "username": username,
        "password": "SecurePass123!",
    })
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════════

class TestHealth:
    async def test_health_check(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════

class TestAuthEndpoints:
    async def test_register_success(self, client: AsyncClient):
        import uuid
        resp = await client.post("/api/v1/auth/register", json={
            "username": f"newuser_{uuid.uuid4().hex[:8]}",
            "email": f"{uuid.uuid4().hex[:8]}@test.com",
            "display_name": "New User",
            "password": "password123!",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "user" in data
        assert data["user"]["role"] == "user"

    async def test_register_duplicate_username(self, client: AsyncClient):
        import uuid
        username = f"dupuser_{uuid.uuid4().hex[:8]}"
        await client.post("/api/v1/auth/register", json={
            "username": username, "display_name": "D",
            "password": "password123!",
        })
        resp = await client.post("/api/v1/auth/register", json={
            "username": username, "display_name": "D2",
            "password": "password456!",
        })
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "CONFLICT"

    async def test_login_success(self, client: AsyncClient):
        import uuid
        username = f"loginuser_{uuid.uuid4().hex[:8]}"
        await client.post("/api/v1/auth/register", json={
            "username": username, "display_name": "L",
            "password": "mypassword123",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "username": username, "password": "mypassword123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        import uuid
        username = f"wrongpw_{uuid.uuid4().hex[:8]}"
        await client.post("/api/v1/auth/register", json={
            "username": username, "display_name": "W",
            "password": "correctpassword",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "username": username, "password": "wrongpassword",
        })
        assert resp.status_code == 401

    async def test_get_me_authenticated(self, client: AsyncClient, auth_headers):
        resp = await client.get("/api/v1/users/me", headers=auth_headers)
        assert resp.status_code == 200
        assert "user" in resp.json()

    async def test_get_me_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/users/me")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════
# STRATEGIES
# ═══════════════════════════════════════════════════════════════════

class TestStrategyEndpoints:
    async def test_create_strategy(self, client: AsyncClient, auth_headers):
        resp = await client.post("/api/v1/strategies", headers=auth_headers, json={
            "name": "EPL Corners Over",
            "metric": "xC",
            "market": "corners_over_under",
            "conditions": [{"field": "home_xC", "op": ">", "value": 2.5}],
            "logic": "and",
            "direction": "OVER",
            "min_odds": 1.70,
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "strategy" in data
        assert "version" in data
        assert data["version"]["version"] == 1
        assert len(data["version"]["content_hash"]) == 64

    async def test_create_strategy_requires_auth(self, client: AsyncClient):
        resp = await client.post("/api/v1/strategies", json={
            "name": "No Auth", "metric": "xC", "market": "corners",
            "conditions": [{"field": "f", "op": ">", "value": 1.0}],
            "direction": "OVER",
        })
        assert resp.status_code == 401

    async def test_get_own_strategy(self, client: AsyncClient, auth_headers):
        # Create
        create_resp = await client.post("/api/v1/strategies", headers=auth_headers, json={
            "name": "Get Test", "metric": "xB", "market": "cards_over_under",
            "conditions": [{"field": "home_xB", "op": ">=", "value": 8.0}],
            "direction": "OVER", "min_odds": 1.80,
        })
        strategy_id = create_resp.json()["strategy"]["id"]

        # Get
        resp = await client.get(f"/api/v1/strategies/{strategy_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["strategy"]["id"] == strategy_id

    async def test_get_strategy_version(self, client: AsyncClient, auth_headers):
        create_resp = await client.post("/api/v1/strategies", headers=auth_headers, json={
            "name": "Version Test", "metric": "xO", "market": "offsides_over_under",
            "conditions": [{"field": "home_xO", "op": ">", "value": 1.5}],
            "direction": "OVER",
        })
        data = create_resp.json()
        strategy_id = data["strategy"]["id"]

        resp = await client.get(
            f"/api/v1/strategies/{strategy_id}/versions/1",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["version"]["version"] == 1

    async def test_update_visibility(self, client: AsyncClient, auth_headers):
        import uuid
        unique_val = float(hash(uuid.uuid4().hex) % 10000) / 100
        create_resp = await client.post("/api/v1/strategies", headers=auth_headers, json={
            "name": f"Vis Change {uuid.uuid4().hex[:6]}", "metric": "xC", "market": "corners_over_under",
            "conditions": [{"field": "f", "op": ">", "value": unique_val}],
            "direction": "UNDER", "visibility": "private",
        })
        assert create_resp.status_code == 201, create_resp.text
        strategy_id = create_resp.json()["strategy"]["id"]

        resp = await client.patch(
            f"/api/v1/strategies/{strategy_id}/versions/1/visibility",
            headers=auth_headers,
            json={"visibility": "public"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["strategy"]["visibility"] == "public"

    async def test_fork_strategy(self, client: AsyncClient, auth_headers):
        import uuid
        # Create source (public so it's forkable) with unique definition
        unique_val = float(hash(uuid.uuid4().hex) % 10000) / 100
        create_resp = await client.post("/api/v1/strategies", headers=auth_headers, json={
            "name": f"Fork Source {uuid.uuid4().hex[:6]}", "metric": "xC", "market": "corners_over_under",
            "conditions": [{"field": "home_xC", "op": ">", "value": unique_val}],
            "direction": "OVER", "visibility": "public",
        })
        assert create_resp.status_code == 201, create_resp.text
        source_id = create_resp.json()["strategy"]["id"]

        # Fork
        resp = await client.post(
            f"/api/v1/strategies/{source_id}/fork",
            headers=auth_headers,
            json={"name": "My Fork"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["strategy"]["name"] == "My Fork"
        assert data["fork_source"]["strategy_id"] == source_id
        assert data["fork_source"]["version"] == 1


# ═══════════════════════════════════════════════════════════════════
# IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════════

class TestIdempotencyHeader:
    async def test_duplicate_request_returns_cached(self, client: AsyncClient, auth_headers):
        """Same Idempotency-Key with same body returns cached response."""
        import uuid
        idem_key = f"test-idem-key-{uuid.uuid4().hex[:8]}"
        unique_val = float(hash(uuid.uuid4().hex) % 10000) / 100
        body = {
            "name": f"Idempotent Strategy {uuid.uuid4().hex[:6]}", "metric": "xC", "market": "corners_over_under",
            "conditions": [{"field": "f", "op": ">", "value": unique_val}],
            "direction": "OVER",
        }

        # First request
        headers = {**auth_headers, "Idempotency-Key": idem_key}
        resp1 = await client.post("/api/v1/strategies", headers=headers, json=body)
        assert resp1.status_code == 201, resp1.text

        # Second request (same key, same body) — should return cached
        resp2 = await client.post("/api/v1/strategies", headers=headers, json=body)
        # Cached response comes back (might be 200 or 201 depending on implementation)
        assert resp2.status_code in (200, 201), resp2.text
        assert resp2.json()["strategy"]["id"] == resp1.json()["strategy"]["id"]

    async def test_same_key_different_body_returns_409(self, client: AsyncClient, auth_headers):
        """Same Idempotency-Key with different body returns 409."""
        idem_key = "conflict-key-001"
        body1 = {
            "name": "First", "metric": "xC", "market": "corners_over_under",
            "conditions": [{"field": "f", "op": ">", "value": 88.0}],
            "direction": "OVER",
        }
        body2 = {
            "name": "Second", "metric": "xB", "market": "cards_over_under",
            "conditions": [{"field": "g", "op": "<", "value": 5.0}],
            "direction": "UNDER",
        }

        headers = {**auth_headers, "Idempotency-Key": idem_key}
        resp1 = await client.post("/api/v1/strategies", headers=headers, json=body1)
        assert resp1.status_code == 201

        resp2 = await client.post("/api/v1/strategies", headers=headers, json=body2)
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


# ═══════════════════════════════════════════════════════════════════
# CORRELATION ID
# ═══════════════════════════════════════════════════════════════════

class TestCorrelationID:
    async def test_response_includes_request_id(self, client: AsyncClient):
        resp = await client.get("/health")
        assert "x-request-id" in resp.headers

    async def test_client_provided_id_preserved(self, client: AsyncClient):
        resp = await client.get("/health", headers={"X-Request-ID": "my-custom-id-123"})
        assert resp.headers["x-request-id"] == "my-custom-id-123"


# ═══════════════════════════════════════════════════════════════════
# IDOR PROTECTION
# ═══════════════════════════════════════════════════════════════════

class TestIDORProtection:
    async def test_cannot_read_other_users_private_strategy(self, client: AsyncClient):
        """User A cannot see User B's private strategy."""
        import uuid

        # Create User A
        user_a = f"usera_{uuid.uuid4().hex[:8]}"
        await client.post("/api/v1/auth/register", json={
            "username": user_a, "display_name": "A", "password": "password123!",
        })
        login_a = await client.post("/api/v1/auth/login", json={
            "username": user_a, "password": "password123!",
        })
        headers_a = {"Authorization": f"Bearer {login_a.json()['access_token']}"}

        # Create User B
        user_b = f"userb_{uuid.uuid4().hex[:8]}"
        await client.post("/api/v1/auth/register", json={
            "username": user_b, "display_name": "B", "password": "password123!",
        })
        login_b = await client.post("/api/v1/auth/login", json={
            "username": user_b, "password": "password123!",
        })
        headers_b = {"Authorization": f"Bearer {login_b.json()['access_token']}"}

        # User B creates private strategy
        create_resp = await client.post("/api/v1/strategies", headers=headers_b, json={
            "name": "B Secret", "metric": "xC", "market": "corners_over_under",
            "conditions": [{"field": "f", "op": ">", "value": 7.7}],
            "direction": "OVER", "visibility": "private",
        })
        assert create_resp.status_code == 201
        strategy_id = create_resp.json()["strategy"]["id"]

        # User A tries to read it
        resp = await client.get(f"/api/v1/strategies/{strategy_id}", headers=headers_a)
        assert resp.status_code == 404  # RLS hides it completely
