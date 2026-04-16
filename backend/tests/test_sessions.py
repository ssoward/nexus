"""Integration tests for session endpoints."""
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.database import db
from app.models.session import SessionStatus


async def _insert_stopped_session(user_id: int, name: str = "test-session") -> str:
    """Insert a session directly into the DB (no PTY spawning)."""
    session_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO sessions
               (id, user_id, name, image, container_name, status, cols, rows)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (session_id, user_id, name, "bash", f"s-{session_id[:8]}",
         SessionStatus.STOPPED.value, 80, 24),
    )
    return session_id


# ---------------------------------------------------------------------------
# GET /api/sessions
# ---------------------------------------------------------------------------

class TestListSessions:
    async def test_empty_for_new_user(self, auth_client):
        ac, _ = auth_client
        r = await ac.get("/api/sessions")
        assert r.status_code == 200
        assert r.json() == []

    async def test_unauthenticated_returns_401(self, client: AsyncClient, setup_db):
        r = await client.get("/api/sessions")
        assert r.status_code == 401

    async def test_returns_user_sessions(self, auth_client, setup_db):
        ac, user = auth_client
        await _insert_stopped_session(user["id"], "my-session")
        r = await ac.get("/api/sessions")
        assert r.status_code == 200
        sessions = r.json()
        assert len(sessions) == 1
        assert sessions[0]["name"] == "my-session"

    async def test_does_not_return_other_users_sessions(self, auth_client, setup_db):
        """Sessions belonging to a different user must not appear."""
        ac, _ = auth_client
        # Insert a session owned by user_id=9999 (doesn't match our test user)
        other_session_id = str(uuid.uuid4())
        await setup_db.execute(
            """INSERT INTO users (username, hashed_password) VALUES (?, ?)""",
            ("otheruser", "x" * 60),
        )
        other = await setup_db.fetchone(
            "SELECT id FROM users WHERE username = ?", ("otheruser",)
        )
        await _insert_stopped_session(other["id"], "other-session")
        r = await ac.get("/api/sessions")
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# POST /api/sessions
# ---------------------------------------------------------------------------

class TestCreateSession:
    async def test_success_with_valid_preset(self, auth_client, setup_db):
        ac, _ = auth_client
        with (
            patch("app.services.pty_service.spawn", return_value=12345),
            patch(
                "app.services.pty_broadcaster.ensure_reader",
                new_callable=AsyncMock,
            ),
        ):
            r = await ac.post(
                "/api/sessions",
                json={"name": "my shell", "image": "bash", "cols": 80, "rows": 24},
            )
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "my shell"
        assert body["image"] == "bash"
        assert body["status"] == SessionStatus.RUNNING.value

    async def test_unauthenticated_returns_401(self, client: AsyncClient, setup_db):
        r = await client.post(
            "/api/sessions",
            json={"name": "x", "image": "bash", "cols": 80, "rows": 24},
        )
        assert r.status_code == 401

    async def test_invalid_cols_returns_422(self, auth_client, setup_db):
        ac, _ = auth_client
        r = await ac.post(
            "/api/sessions",
            json={"name": "x", "image": "bash", "cols": 5, "rows": 24},
        )
        assert r.status_code == 422

    async def test_empty_name_returns_422(self, auth_client, setup_db):
        ac, _ = auth_client
        r = await ac.post(
            "/api/sessions",
            json={"name": "   ", "image": "bash", "cols": 80, "rows": 24},
        )
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/sessions/{id}
# ---------------------------------------------------------------------------

class TestDeleteSession:
    async def test_success(self, auth_client, setup_db):
        ac, user = auth_client
        session_id = await _insert_stopped_session(user["id"])
        with patch("app.services.pty_service.kill"):
            r = await ac.delete(f"/api/sessions/{session_id}")
        assert r.status_code == 204

        remaining = await setup_db.fetchone(
            "SELECT id FROM sessions WHERE id = ?", (session_id,)
        )
        assert remaining is None

    async def test_returns_404_for_unknown_session(self, auth_client, setup_db):
        ac, _ = auth_client
        r = await ac.delete("/api/sessions/non-existent-id")
        assert r.status_code == 404

    async def test_cannot_delete_another_users_session(self, auth_client, setup_db):
        ac, _ = auth_client
        await setup_db.execute(
            "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
            ("otheruser2", "x" * 60),
        )
        other = await setup_db.fetchone(
            "SELECT id FROM users WHERE username = ?", ("otheruser2",)
        )
        other_session_id = await _insert_stopped_session(other["id"])
        r = await ac.delete(f"/api/sessions/{other_session_id}")
        assert r.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, setup_db):
        r = await client.delete("/api/sessions/some-id")
        assert r.status_code == 401
