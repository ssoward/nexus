"""Serialize/deserialize ring buffers for session recovery after restart."""

import base64
import json
import logging
import os
import time

from app.services import pty_broadcaster

logger = logging.getLogger(__name__)

RECOVERY_DIR = os.path.expanduser("~/.nexus")
RECOVERY_FILE = os.path.join(RECOVERY_DIR, "recovery.json")


def save_recovery() -> None:
    """Serialize ring buffers + metadata before shutdown."""
    data = {"saved_at": time.time(), "sessions": {}}
    for session_id, state in pty_broadcaster._sessions.items():
        chunks = [base64.b64encode(c).decode() for c in state.ring_buffer]
        data["sessions"][session_id] = {
            "ring_buffer": chunks,
            "last_output_time": state.last_output_time,
        }
    os.makedirs(RECOVERY_DIR, exist_ok=True)
    with open(RECOVERY_FILE, "w") as f:
        json.dump(data, f)
    logger.info("Recovery data saved for %d sessions", len(data["sessions"]))


def load_recovery(ttl_hours: int) -> dict | None:
    """Load recovery file if it exists and is within TTL."""
    if not os.path.exists(RECOVERY_FILE):
        return None
    try:
        with open(RECOVERY_FILE) as f:
            data = json.load(f)
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
    try:
        os.remove(RECOVERY_FILE)
    except FileNotFoundError:
        pass
