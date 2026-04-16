"""totp replay protection — track last used code per user

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-16
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Store the last successfully-used TOTP code so we can reject reuse
    # within the same ~90-second valid window (valid_window=1 → ±1 step).
    op.execute("ALTER TABLE users ADD COLUMN last_totp_code TEXT")
    op.execute("ALTER TABLE users ADD COLUMN last_totp_at   TEXT")


def downgrade() -> None:
    # SQLite does not support DROP COLUMN before 3.35; recreate without the columns.
    op.execute("""
        CREATE TABLE users_new (
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
        INSERT INTO users_new
            (id, username, hashed_password, encrypted_totp_secret,
             failed_login_count, lockout_until, created_at)
        SELECT id, username, hashed_password, encrypted_totp_secret,
               failed_login_count, lockout_until, created_at
        FROM users
    """)
    op.execute("DROP TABLE users")
    op.execute("ALTER TABLE users_new RENAME TO users")
