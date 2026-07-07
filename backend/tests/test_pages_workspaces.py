"""Router tests for the Pages and Workspaces CRUD endpoints.

Covers auth enforcement, per-user ownership isolation, and input validation
(https-only page URLs, hex-only workspace colors).
"""
import pytest
from httpx import AsyncClient


async def _other_user(setup_db, username="other@example.com"):
    await setup_db.execute(
        "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
        (username, "x" * 60),
    )
    row = await setup_db.fetchone("SELECT id FROM users WHERE username = ?", (username,))
    return row["id"]


# ── Pages ─────────────────────────────────────────────────────────────────────

class TestPages:
    async def test_unauthenticated_returns_401(self, client: AsyncClient, setup_db):
        assert (await client.get("/api/pages")).status_code == 401

    async def test_create_and_list(self, auth_client, setup_db):
        ac, _ = auth_client
        r = await ac.post("/api/pages", json={"name": "Docs", "url": "https://example.com"})
        assert r.status_code == 201
        assert r.json()["url"] == "https://example.com"

        r = await ac.get("/api/pages")
        assert r.status_code == 200
        assert len(r.json()) == 1

    async def test_rejects_non_https_url(self, auth_client, setup_db):
        ac, _ = auth_client
        r = await ac.post("/api/pages", json={"name": "Bad", "url": "http://example.com"})
        assert r.status_code == 422

    async def test_rejects_javascript_url(self, auth_client, setup_db):
        ac, _ = auth_client
        r = await ac.post("/api/pages", json={"name": "XSS", "url": "javascript:alert(1)"})
        assert r.status_code == 422

    async def test_rejects_empty_name(self, auth_client, setup_db):
        ac, _ = auth_client
        r = await ac.post("/api/pages", json={"name": "   ", "url": "https://example.com"})
        assert r.status_code == 422

    async def test_cannot_update_another_users_page(self, auth_client, setup_db):
        ac, _ = auth_client
        other_id = await _other_user(setup_db)
        pid = await setup_db.execute_returning(
            "INSERT INTO pages (user_id, name, url) VALUES (?, ?, ?)",
            (other_id, "theirs", "https://theirs.example"),
        )
        r = await ac.patch(f"/api/pages/{pid}", json={"name": "hijacked"})
        assert r.status_code == 404

    async def test_cannot_delete_another_users_page(self, auth_client, setup_db):
        ac, _ = auth_client
        other_id = await _other_user(setup_db)
        pid = await setup_db.execute_returning(
            "INSERT INTO pages (user_id, name, url) VALUES (?, ?, ?)",
            (other_id, "theirs", "https://theirs.example"),
        )
        r = await ac.delete(f"/api/pages/{pid}")
        assert r.status_code == 404
        # Still present
        row = await setup_db.fetchone("SELECT id FROM pages WHERE id = ?", (pid,))
        assert row is not None

    async def test_update_rejects_non_https(self, auth_client, setup_db):
        ac, user = auth_client
        pid = await setup_db.execute_returning(
            "INSERT INTO pages (user_id, name, url) VALUES (?, ?, ?)",
            (user["id"], "mine", "https://mine.example"),
        )
        r = await ac.patch(f"/api/pages/{pid}", json={"url": "ftp://mine.example"})
        assert r.status_code == 422


# ── Workspaces ──────────────────────────────────────────────────────────────

class TestWorkspaces:
    async def test_unauthenticated_returns_401(self, client: AsyncClient, setup_db):
        assert (await client.get("/api/workspaces")).status_code == 401

    async def test_create_with_default_color(self, auth_client, setup_db):
        ac, _ = auth_client
        r = await ac.post("/api/workspaces", json={"name": "Work"})
        assert r.status_code == 201
        assert r.json()["color"] == "#388bfd"

    async def test_rejects_invalid_color(self, auth_client, setup_db):
        ac, _ = auth_client
        r = await ac.post("/api/workspaces", json={"name": "W", "color": "red"})
        assert r.status_code == 422

    async def test_rejects_css_injection_in_color(self, auth_client, setup_db):
        ac, _ = auth_client
        r = await ac.post(
            "/api/workspaces",
            json={"name": "W", "color": "#fff;background:url(x)"},
        )
        assert r.status_code == 422

    async def test_cannot_delete_another_users_workspace(self, auth_client, setup_db):
        ac, _ = auth_client
        other_id = await _other_user(setup_db, "ws-other@example.com")
        wid = await setup_db.execute_returning(
            "INSERT INTO workspaces (user_id, name) VALUES (?, ?)",
            (other_id, "theirs"),
        )
        r = await ac.delete(f"/api/workspaces/{wid}")
        assert r.status_code == 404
