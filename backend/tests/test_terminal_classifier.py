"""Tests for terminal state classification from recent PTY output."""
import time
from unittest.mock import patch

from app.services.terminal_classifier import TerminalState, classify, _strip_ansi


def test_strip_ansi_removes_escape_sequences():
    assert _strip_ansi("\x1b[31mred\x1b[0m") == "red"
    assert _strip_ansi("plain") == "plain"


def test_no_output_time_is_busy():
    with patch("app.services.pty_broadcaster.get_last_output_time", return_value=0):
        state, idle = classify("s1")
    assert state == TerminalState.BUSY
    assert idle == 0.0


def test_recent_output_is_working():
    now = time.monotonic()
    with patch("app.services.pty_broadcaster.get_last_output_time", return_value=now):
        state, _ = classify("s1")
    assert state == TerminalState.WORKING


def _classify_idle_with_buffer(buffer: bytes):
    old = time.monotonic() - 10  # older than WORKING_THRESHOLD
    with (
        patch("app.services.pty_broadcaster.get_last_output_time", return_value=old),
        patch("app.services.pty_broadcaster.get_buffer", return_value=buffer),
    ):
        return classify("s1")[0]


def test_shell_prompt_is_waiting():
    assert _classify_idle_with_buffer(b"user@host:~$ ") == TerminalState.WAITING


def test_python_repl_prompt_is_waiting():
    assert _classify_idle_with_buffer(b">>> ") == TerminalState.WAITING


def test_yes_no_question_is_asking():
    assert _classify_idle_with_buffer(b"Overwrite file? (y/n)") == TerminalState.ASKING


def test_confirm_phrase_is_asking():
    assert _classify_idle_with_buffer(b"Do you want to continue") == TerminalState.ASKING


def test_idle_non_prompt_output_is_busy():
    assert _classify_idle_with_buffer(b"compiling module 42 of 100") == TerminalState.BUSY
