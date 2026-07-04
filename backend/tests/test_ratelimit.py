"""Unit tests for the enrollment fixed-window rate limiter internals.

These exercise ``_within_fixed_window`` directly (not through the HTTP routes,
which ``tests/api/routes/test_enrollment.py`` covers): the atomic window
creation and the fail-open circuit breaker.
"""

from __future__ import annotations

import pytest
from redis.exceptions import RedisError

from app.core import ratelimit
from tests.utils.fake_redis import FakeRedis


def test_window_counter_is_created_with_a_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """The window counter is always created with its expiry (SET NX EX), so a
    counter can never be left un-expiring and leak the key.
    """
    fake = FakeRedis()
    monkeypatch.setattr(ratelimit, "redis_client", fake)
    ratelimit._reset_circuit()

    allowed, _ = ratelimit._within_fixed_window("bucket", "identity", limit=5)

    assert allowed is True
    (key,) = fake.counts  # exactly one window key was touched
    assert fake.ttls.get(key) == 60  # created with its TTL, not left un-expiring


def test_window_counts_up_and_rejects_past_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hits accumulate in one window and the (limit+1)-th is rejected with a
    positive Retry-After.
    """
    fake = FakeRedis()
    monkeypatch.setattr(ratelimit, "redis_client", fake)
    monkeypatch.setattr(ratelimit.time, "time", lambda: 1_000_000.0)
    ratelimit._reset_circuit()

    for _ in range(2):
        assert ratelimit._within_fixed_window("b", "id", limit=2) == (True, 0)
    allowed, retry_after = ratelimit._within_fixed_window("b", "id", limit=2)
    assert allowed is False
    assert retry_after > 0


def test_circuit_breaker_skips_backend_during_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After a Redis error the limiter opens a circuit and stops touching the
    backend for a cooldown, so a down backend is not re-probed (and re-timed-out)
    on every request. It fails open while the circuit is open.
    """
    touches = {"n": 0}

    class _DownRedis:
        def pipeline(self, transaction: bool = True) -> object:
            touches["n"] += 1
            raise RedisError("backend down")

    monkeypatch.setattr(ratelimit, "redis_client", _DownRedis())
    monkeypatch.setattr(ratelimit.time, "time", lambda: 1_000_000.0)
    ratelimit._reset_circuit()

    first = ratelimit._within_fixed_window("b", "id", limit=5)
    second = ratelimit._within_fixed_window("b", "id", limit=5)

    assert first == (True, 0) and second == (True, 0)  # both fail open
    assert touches["n"] == 1  # backend probed once, then skipped while cooling


def test_circuit_breaker_reprobes_after_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Once the cooldown elapses the limiter probes the backend again (the
    circuit is not stuck open).
    """
    touches = {"n": 0}
    clock = {"t": 1_000_000.0}

    class _DownRedis:
        def pipeline(self, transaction: bool = True) -> object:
            touches["n"] += 1
            raise RedisError("backend down")

    monkeypatch.setattr(ratelimit, "redis_client", _DownRedis())
    monkeypatch.setattr(ratelimit.time, "time", lambda: clock["t"])
    ratelimit._reset_circuit()

    ratelimit._within_fixed_window("b", "id", limit=5)  # trips the circuit
    clock["t"] += ratelimit._CIRCUIT_COOLDOWN_SECONDS + 1  # let it cool down
    ratelimit._within_fixed_window("b", "id", limit=5)  # probes again

    assert touches["n"] == 2
