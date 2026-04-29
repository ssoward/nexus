"""
Test configuration and shared fixtures.

Env vars must be set at module load time — before any app module is imported —
so that pydantic-settings picks them up when Settings is first instantiated.
"""
import os

os.environ.setdefault("APP_SECRET", "test-app-secret-minimum-32-charsx")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-minimum-32-charsx")
os.environ.setdefault("CRYPTO_SALT", "test-crypto-salt-16cx")
os.environ.setdefault("CONFIG_PATH", "")  # skip config.yml in tests

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.crypto import init_crypto, hash_password
from app.database import db
from app.limiter import limiter
from app.routers import auth as auth_router, sessions as sessions_router, passkey as passkey_router

# One-time crypto init — matches what app lifespan does
_s = get_settings()
init_crypto(_s.app_secret, _s.crypto_salt)

# Full schema (mirrors alembic migrations 0001 + 0006)
_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id                     INTEGER PRIMARY KEY AUTOINCREMENT,
        username               TEXT NOT NULL UNIQUE,
        hashed_password        TEXT NOT NULL,
        encrypted_totp_secret  BLOB,
        failed_login_count     INTEGER NOT NULL DEFAULT 0,
        lockout_until          TEXT,
        last_totp_code         TEXT,
        last_totp_at           TEXT,
        mfa_method             TEXT DEFAULT NULL,
        created_at             TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        id               TEXT PRIMARY KEY,
        user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name             TEXT NOT NULL,
        image            TEXT NOT NULL,
        container_id     TEXT,
        container_name   TEXT NOT NULL,
        status           TEXT NOT NULL DEFAULT 'pending',
        cols             INTEGER NOT NULL DEFAULT 220,
        rows             INTEGER NOT NULL DEFAULT 50,
        created_at       TEXT NOT NULL DEFAULT (datetime('now')),
        last_active_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_container_id ON sessions(container_id)",
    """CREATE TABLE IF NOT EXISTS audit_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
        action       TEXT NOT NULL,
        detail       TEXT,
        ip_address   TEXT,
        created_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_log(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at)",
    """CREATE TABLE IF NOT EXISTS ws_tokens (
        jti          TEXT PRIMARY KEY,
        user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        session_id   TEXT NOT NULL,
        expires_at   TEXT NOT NULL,
        used         INTEGER NOT NULL DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS idx_ws_tokens_expires_at ON ws_tokens(expires_at)",
    """CREATE TABLE IF NOT EXISTS revoked_tokens (
        jti         TEXT PRIMARY KEY,
        user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
        expires_at  TEXT NOT NULL,
        revoked_at  TEXT NOT NULL DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires_at ON revoked_tokens(expires_at)",
    """CREATE TABLE IF NOT EXISTS email_otp_codes (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        hashed_code TEXT NOT NULL,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        expires_at  TEXT NOT NULL,
        used        INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS passkey_credentials (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        credential_id BLOB NOT NULL UNIQUE,
        public_key    BLOB NOT NULL,
        sign_count    INTEGER NOT NULL DEFAULT 0,
        transports    TEXT,
        aaguid        TEXT,
        name          TEXT,
        created_at    TEXT NOT NULL DEFAULT (datetime('now')),
        last_used_at  TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_passkey_user ON passkey_credentials(user_id)",
    """CREATE TABLE IF NOT EXISTS webauthn_challenges (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        challenge  TEXT NOT NULL,
        purpose    TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used       INTEGER NOT NULL DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS idx_challenge_user ON webauthn_challenges(user_id)",
]


def _make_app() -> FastAPI:
    """Minimal FastAPI app with real routers but no lifespan (no subprocess/watchdog)."""
    app = FastAPI()
    # Provide limiter state so @limiter.limit decorators don't crash
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(auth_router.router)
    app.include_router(sessions_router.router)
    app.include_router(passkey_router.router)
    return app


@pytest_asyncio.fixture
async def setup_db(tmp_path):
    """Fresh SQLite database per test — schema only, no seed data."""
    db._init(str(tmp_path / "test.db"))
    await db.connect()
    for stmt in _SCHEMA:
        await db.execute(stmt)
    yield db
    await db.close()
    db._delegate = None  # reset proxy so next test can re-init


@pytest_asyncio.fixture
async def client(setup_db):
    """Unauthenticated HTTP test client."""
    async with AsyncClient(
        transport=ASGITransport(app=_make_app()), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def test_user(setup_db):
    """Insert a plain (no-TOTP) test user; return credentials dict."""
    username, password = "testuser", "TestPassword1!Secure"
    await setup_db.execute(
        "INSERT INTO users (username, hashed_password) VALUES (?, ?)",
        (username, hash_password(password)),
    )
    row = await setup_db.fetchone("SELECT id FROM users WHERE username = ?", (username,))
    return {"id": row["id"], "username": username, "password": password}


@pytest_asyncio.fixture
async def auth_client(setup_db, test_user):
    """HTTP client pre-loaded with a valid access-token cookie."""
    from app.services.token_service import create_access_token

    token = create_access_token(test_user["id"])
    async with AsyncClient(
        transport=ASGITransport(app=_make_app()),
        base_url="http://test",
        cookies={"access_token": token},
    ) as ac:
        yield ac, test_user
