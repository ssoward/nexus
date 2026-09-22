"""email OTP is an explicitly enrolled factor, not implied by the password

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-22
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Before this, /switch-mfa let a password-only caller move any account onto
    # email codes. Email OTP now has to be enrolled (setup-mfa, or Settings with
    # step-up) before it appears as a sign-in option. Accounts already using it
    # are grandfathered in.
    op.execute("ALTER TABLE users ADD COLUMN email_otp_enrolled INTEGER NOT NULL DEFAULT 0")
    op.execute("UPDATE users SET email_otp_enrolled = 1 WHERE mfa_method = 'email_otp'")


def downgrade() -> None:
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
            tokens_valid_after     TEXT,
            created_at             TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    op.execute("""
        INSERT INTO users_new
            (id, username, hashed_password, encrypted_totp_secret,
             failed_login_count, lockout_until, last_totp_code, last_totp_at,
             mfa_method, tokens_valid_after, created_at)
        SELECT id, username, hashed_password, encrypted_totp_secret,
               failed_login_count, lockout_until, last_totp_code, last_totp_at,
               mfa_method, tokens_valid_after, created_at
        FROM users
    """)
    op.execute("DROP TABLE users")
    op.execute("ALTER TABLE users_new RENAME TO users")
