"""In-memory Redis fakes for the enrollment rate-limiter tests.

The limiter (``app.core.ratelimit``) does exactly one atomic
``SET key 0 NX EX 60`` + ``INCR key`` per request via a transactional pipeline.
These fakes model only that surface — enough for the fixed-window counting, the
TTL bookkeeping, and the fail-open path — without a real Redis.
"""

from __future__ import annotations

from redis.exceptions import RedisError


class _Pipeline:
    """Records the queued ``set``/``incr`` and applies them on ``execute``.

    Mirrors redis-py's transactional pipeline: the commands buffer and run
    together, ``set(..., nx=True)`` no-ops when the key already exists (returning
    ``None``), and ``execute`` returns the per-command results in order.
    """

    def __init__(self, backend: FakeRedis) -> None:
        self._backend = backend
        self._ops: list[tuple[object, ...]] = []

    def set(
        self, key: str, value: int, *, nx: bool = False, ex: int | None = None
    ) -> _Pipeline:
        self._ops.append(("set", key, value, nx, ex))
        return self

    def incr(self, key: str) -> _Pipeline:
        self._ops.append(("incr", key))
        return self

    def execute(self) -> list[object]:
        results: list[object] = []
        for op in self._ops:
            if op[0] == "set":
                _, key, value, nx, ex = op
                if nx and key in self._backend.counts:
                    results.append(None)
                    continue
                self._backend.counts[str(key)] = int(value)  # type: ignore[arg-type]
                if ex is not None:
                    self._backend.ttls[str(key)] = int(ex)  # type: ignore[arg-type]
                results.append(True)
            else:  # incr
                _, key = op
                k = str(key)
                self._backend.counts[k] = self._backend.counts.get(k, 0) + 1
                results.append(self._backend.counts[k])
        return results


class FakeRedis:
    """Deterministic in-memory fixed-window counter with TTL tracking."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def pipeline(self, transaction: bool = True) -> _Pipeline:
        return _Pipeline(self)


class _FailingPipeline:
    def set(self, *args: object, **kwargs: object) -> _FailingPipeline:
        return self

    def incr(self, *args: object, **kwargs: object) -> _FailingPipeline:
        return self

    def execute(self) -> list[object]:
        raise RedisError("rate-limit backend unavailable (test fake)")


class FailOpenRedis:
    """A backend whose pipeline always errors, so the limiter fails open."""

    def pipeline(self, transaction: bool = True) -> _FailingPipeline:
        return _FailingPipeline()
