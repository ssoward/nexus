"""Account recovery tokens for MFA reset via email link

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-20
"""
from alembic import op

revision = "0007"
down_revision = "0006"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS account_recovery_tokens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at TEXT NOT NULL,
            used       INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_recovery_user ON account_recovery_tokens(user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_recovery_expires ON account_recovery_tokens(expires_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS account_recovery_tokens")
