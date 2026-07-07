"""Router tests for the orchestration endpoints (session state / buffer / input)."""
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.models.session import SessionStatus


async def _insert_session(setup_db, user_id, status=SessionStatus.RUNNING.value, name="s"):
    import uuid
    sid = str(uuid.uuid4())
    await setup_db.execute(
        "INSERT INTO sessions (id, user_id, name, image, container_name, status, cols, rows, "
        "created_at, last_active_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
        (sid, user_id, name, "bash", f"session-{sid[:8]}", status, 80, 24),
    )
    return sid


class TestOrchestrationAuth:
    async def test_states_requires_auth(self, client: AsyncClient, setup_db):
        assert (await client.get("/api/orchestration/sessions/states")).status_code == 401

    async def test_input_requires_auth(self, client: AsyncClient, setup_db):
        r = await client.post("/api/orchestration/sessions/x/input", json={"data": "ls"})
        assert r.status_code == 401


class TestSessionState:
    async def test_unknown_session_404(self, auth_client, setup_db):
        ac, _ = auth_client
        r = await ac.get("/api/orchestration/sessions/nope/state")
        assert r.status_code == 404

    async def test_non_running_session_409(self, auth_client, setup_db):
        ac, user = auth_client
        sid = await _insert_session(setup_db, user["id"], status=SessionStatus.STOPPED.value)
        r = await ac.get(f"/api/orchestration/sessions/{sid}/state")
        assert r.status_code == 409

    async def test_running_session_returns_state(self, auth_client, setup_db):
        ac, user = auth_client
        sid = await _insert_session(setup_db, user["id"])
        with patch(
            "app.routers.orchestration.classify",
            return_value=("BUSY", 1.5),
        ):
            r = await ac.get(f"/api/orchestration/sessions/{sid}/state")
        assert r.status_code == 200
        assert r.json()["session_id"] == sid

    async def test_cannot_read_other_users_session(self, auth_client, setup_db):
        ac, _ = auth_client
        await setup_db.execute(
            "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
            ("orch-other@example.com", "x" * 60),
        )
        other = await setup_db.fetchone(
            "SELECT id FROM users WHERE username = ?", ("orch-other@example.com",)
        )
        sid = await _insert_session(setup_db, other["id"])
        r = await ac.get(f"/api/orchestration/sessions/{sid}/state")
        assert r.status_code == 404


class TestSessionBuffer:
    async def test_lines_out_of_range_rejected(self, auth_client, setup_db):
        ac, user = auth_client
        sid = await _insert_session(setup_db, user["id"])
        assert (await ac.get(f"/api/orchestration/sessions/{sid}/buffer?lines=0")).status_code == 400
        assert (await ac.get(f"/api/orchestration/sessions/{sid}/buffer?lines=5000")).status_code == 400

    async def test_returns_buffer(self, auth_client, setup_db):
        ac, user = auth_client
        sid = await _insert_session(setup_db, user["id"])
        with patch(
            "app.services.pty_broadcaster.get_buffer",
            return_value=b"hello\nworld",
        ):
            r = await ac.get(f"/api/orchestration/sessions/{sid}/buffer?lines=10")
        assert r.status_code == 200
        assert r.json()["buffer"] == "hello\nworld"


class TestSessionInput:
    async def test_empty_input_rejected(self, auth_client, setup_db):
        ac, user = auth_client
        sid = await _insert_session(setup_db, user["id"])
        r = await ac.post(f"/api/orchestration/sessions/{sid}/input", json={"data": ""})
        assert r.status_code == 422

    async def test_oversized_input_rejected(self, auth_client, setup_db):
        ac, user = auth_client
        sid = await _insert_session(setup_db, user["id"])
        r = await ac.post(
            f"/api/orchestration/sessions/{sid}/input",
            json={"data": "x" * 5000},
        )
        assert r.status_code == 422

    async def test_input_written_to_pty(self, auth_client, setup_db):
        ac, user = auth_client
        sid = await _insert_session(setup_db, user["id"])
        with (
            patch("app.services.pty_service.get_fd", return_value=7),
            patch("app.services.pty_service.write_all") as mock_write,
        ):
            r = await ac.post(
                f"/api/orchestration/sessions/{sid}/input",
                json={"data": "echo hi\n"},
            )
        assert r.status_code == 200
        mock_write.assert_called_once()
        assert mock_write.call_args[0][1] == b"echo hi\n"

    async def test_input_pty_gone_returns_410(self, auth_client, setup_db):
        ac, user = auth_client
        sid = await _insert_session(setup_db, user["id"])
        with patch("app.services.pty_service.get_fd", return_value=None):
            r = await ac.post(
                f"/api/orchestration/sessions/{sid}/input",
                json={"data": "ls\n"},
            )
        assert r.status_code == 410
