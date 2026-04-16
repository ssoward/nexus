"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-15
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            username               TEXT NOT NULL UNIQUE,
            hashed_password        TEXT NOT NULL,
            encrypted_totp_secret  BLOB,
            failed_login_count     INTEGER NOT NULL DEFAULT 0,
            lockout_until          TEXT,
            created_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
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
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_sessions_container_id ON sessions(container_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action       TEXT NOT NULL,
            detail       TEXT,
            ip_address   TEXT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_user_id ON audit_log(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_log(created_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS ws_tokens (
            jti          TEXT PRIMARY KEY,
            user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_id   TEXT NOT NULL,
            expires_at   TEXT NOT NULL,
            used         INTEGER NOT NULL DEFAULT 0
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS idx_ws_tokens_expires_at ON ws_tokens(expires_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ws_tokens")
    op.execute("DROP TABLE IF EXISTS audit_log")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS users")
