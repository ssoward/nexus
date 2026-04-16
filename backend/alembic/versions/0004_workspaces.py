"""workspace grouping

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-16
"""
from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            color       TEXT NOT NULL DEFAULT '#388bfd',
            sort_order  INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_workspaces_user_id ON workspaces(user_id)")
    op.execute("ALTER TABLE sessions ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id) ON DELETE SET NULL")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspaces")
