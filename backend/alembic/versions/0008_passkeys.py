"""WebAuthn passkey credentials and challenge storage

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-26
"""
from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS passkey_credentials (
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
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_passkey_user ON passkey_credentials(user_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS webauthn_challenges (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            challenge  TEXT NOT NULL,
            purpose    TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used       INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_challenge_user ON webauthn_challenges(user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_challenge_expires ON webauthn_challenges(expires_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS passkey_credentials")
    op.execute("DROP TABLE IF EXISTS webauthn_challenges")
