"""per-user token invalidation — reject tokens issued before a cutoff

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-05
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ISO-8601 timestamp; any access token whose auth_time predates this value is
    # rejected in get_current_user. Stamped on password change, email change, and
    # MFA recovery reset so those events evict every outstanding session.
    op.execute("ALTER TABLE users ADD COLUMN tokens_valid_after TEXT")


def downgrade() -> None:
    # SQLite < 3.35 has no DROP COLUMN; recreate the table without it.
    op.execute("""
        CREATE TABLE users_new (
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
        )
    """)
    op.execute("""
        INSERT INTO users_new
            (id, username, hashed_password, encrypted_totp_secret,
             failed_login_count, lockout_until, last_totp_code, last_totp_at,
             mfa_method, created_at)
        SELECT id, username, hashed_password, encrypted_totp_secret,
               failed_login_count, lockout_until, last_totp_code, last_totp_at,
               mfa_method, created_at
        FROM users
    """)
    op.execute("DROP TABLE users")
    op.execute("ALTER TABLE users_new RENAME TO users")
