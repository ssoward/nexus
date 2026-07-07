"""Serialize/deserialize ring buffers for session recovery after restart."""

import base64
import json
import logging
import os
import time

from app.crypto import decrypt_bytes, encrypt_bytes
from app.services import pty_broadcaster

logger = logging.getLogger(__name__)

RECOVERY_DIR = os.path.expanduser("~/.nexus")
# .enc: the blob is AES-GCM encrypted at rest (M1). Terminal scrollback routinely
# contains secrets (echoed tokens, `export` lines, credential URLs); it must not
# sit on disk in plaintext, even with 0600 perms.
RECOVERY_FILE = os.path.join(RECOVERY_DIR, "recovery.enc")
_LEGACY_PLAINTEXT_FILE = os.path.join(RECOVERY_DIR, "recovery.json")
_CONTEXT = "recovery"


def save_recovery() -> None:
    """Serialize ring buffers + metadata before shutdown, encrypted at rest."""
    data = {"saved_at": time.time(), "sessions": {}}
    for session_id, state in pty_broadcaster._sessions.items():
        chunks = [base64.b64encode(c).decode() for c in state.ring_buffer]
        data["sessions"][session_id] = {
            "ring_buffer": chunks,
            "last_output_time": state.last_output_time,
        }
    os.makedirs(RECOVERY_DIR, exist_ok=True)
    blob = encrypt_bytes(json.dumps(data).encode(), _CONTEXT)
    with open(RECOVERY_FILE, "wb") as f:
        f.write(blob)
    os.chmod(RECOVERY_FILE, 0o600)  # MED-3: contain session IDs to owner only
    # A prior build may have left a plaintext recovery.json — remove it so
    # scrollback doesn't linger unencrypted.
    try:
        os.remove(_LEGACY_PLAINTEXT_FILE)
    except FileNotFoundError:
        pass
    logger.info("Recovery data saved (encrypted) for %d sessions", len(data["sessions"]))


def load_recovery(ttl_hours: int) -> dict | None:
    """Load and decrypt the recovery file if it exists and is within TTL."""
    if not os.path.exists(RECOVERY_FILE):
        return None
    try:
        with open(RECOVERY_FILE, "rb") as f:
            blob = f.read()
        data = json.loads(decrypt_bytes(blob, _CONTEXT).decode())
        age_hours = (time.time() - data["saved_at"]) / 3600
        if age_hours > ttl_hours:
            logger.info("Recovery file too old (%.1fh > %dh), ignoring", age_hours, ttl_hours)
            os.remove(RECOVERY_FILE)
            return None
        logger.info("Recovery file loaded (%.1fh old, %d sessions)", age_hours, len(data["sessions"]))
        return data
    except Exception as e:
        logger.warning("Failed to load recovery file: %s", e)
        return None


def remove_recovery_file() -> None:
    for path in (RECOVERY_FILE, _LEGACY_PLAINTEXT_FILE):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
