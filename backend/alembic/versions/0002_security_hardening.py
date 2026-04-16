"""security hardening — revoked_tokens table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-15
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # JWT revocation store (logout invalidation)
    op.execute("""
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            jti         TEXT PRIMARY KEY,
            user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
            expires_at  TEXT NOT NULL,
            revoked_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires_at "
        "ON revoked_tokens(expires_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS revoked_tokens")
