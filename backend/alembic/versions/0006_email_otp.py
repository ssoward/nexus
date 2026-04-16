"""email OTP MFA and self-registration

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-16
"""
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    # Track which MFA method the user chose
    op.execute("ALTER TABLE users ADD COLUMN mfa_method TEXT DEFAULT NULL")
    # Backfill: existing TOTP users
    op.execute("UPDATE users SET mfa_method = 'totp' WHERE encrypted_totp_secret IS NOT NULL")

    # Pending email OTP codes (short-lived, cleaned up by watchdog)
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_otp_codes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            hashed_code TEXT NOT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at  TEXT NOT NULL,
            used        INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_email_otp_user ON email_otp_codes(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_email_otp_expires ON email_otp_codes(expires_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_otp_codes")
