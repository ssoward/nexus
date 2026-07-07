"""Unit tests for the per-session terminal input rate limiter."""
import asyncio

import pytest

from app.services.rate_limiter import InputRateLimiter, MAX_CHARS_PER_SECOND


@pytest.mark.asyncio
async def test_first_input_allowed():
    rl = InputRateLimiter()
    assert await rl.allow("s1", 10) is True


@pytest.mark.asyncio
async def test_rejects_non_positive_and_oversized():
    rl = InputRateLimiter()
    assert await rl.allow("s1", 0) is False
    assert await rl.allow("s1", -5) is False
    assert await rl.allow("s1", 10_001) is False


@pytest.mark.asyncio
async def test_accumulates_within_window_then_blocks():
    rl = InputRateLimiter()
    # Fill the budget in one window
    assert await rl.allow("s1", MAX_CHARS_PER_SECOND) is True
    # Any further byte in the same window is dropped
    assert await rl.allow("s1", 1) is False


@pytest.mark.asyncio
async def test_new_window_resets_budget():
    rl = InputRateLimiter()
    assert await rl.allow("s1", MAX_CHARS_PER_SECOND) is True
    assert await rl.allow("s1", 1) is False
    # Force the window to roll over
    _, window_start = rl._state["s1"]
    rl._state["s1"] = (MAX_CHARS_PER_SECOND, window_start - 2.0)
    assert await rl.allow("s1", 5) is True


@pytest.mark.asyncio
async def test_sessions_are_isolated():
    rl = InputRateLimiter()
    assert await rl.allow("s1", MAX_CHARS_PER_SECOND) is True
    assert await rl.allow("s1", 1) is False
    # A different session has its own budget
    assert await rl.allow("s2", 10) is True


@pytest.mark.asyncio
async def test_remove_clears_state():
    rl = InputRateLimiter()
    await rl.allow("s1", 10)
    assert "s1" in rl._state
    rl.remove("s1")
    assert "s1" not in rl._state
    # Removing an unknown session is a no-op
    rl.remove("nope")
