"""Redis-backed fixed-window rate limiting for enrollment (design D2).

A small fixed-window counter keyed by ``(bucket, identity, minute)``, backed by
the in-stack Redis already used by Huey (constructed from ``HUEY_REDIS_HOST`` /
``HUEY_REDIS_PORT`` — no new dependency). Exposed as per-route FastAPI
dependencies so a rejected request is refused *before* the handler body runs —
no CSR signed, no ``Station`` / ``EnrollmentToken`` written.

Fail-open: rate limits are a throttle, not the authorization boundary (that is
the HMAC token + attempts cap + DB-backed quotas). If the Redis backend is
unreachable the limiter logs a warning and allows the request rather than
hard-failing every enrollment on a limiter hiccup.
"""

import logging
import time
from typing import cast

import redis
from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.api.deps import CurrentUser, client_source
from app.core.config import settings

logger = logging.getLogger(__name__)

# Constructed at import like huey_client / garage_client: redis-py connects
# lazily, so this touches no socket at import. Short timeouts bound the
# fail-open latency when the backend is down (e.g. dev, where there is no
# Redis and the hostname does not resolve). Patched to a fake in tests.
redis_client = redis.Redis(
    host=settings.HUEY_REDIS_HOST,
    port=settings.HUEY_REDIS_PORT,
    socket_connect_timeout=0.25,
    socket_timeout=0.25,
)


def _within_fixed_window(bucket: str, identity: str, limit: int) -> tuple[bool, int]:
    """Count one hit for ``(bucket, identity)`` in the current minute window.

    Returns ``(allowed, retry_after_seconds)``. Any Redis error fails open
    (logs and allows) — see the module docstring.
    """
    now = time.time()
    key = f"ratelimit:{bucket}:{identity}:{int(now // 60)}"
    try:
        # redis-py types incr() as a sync/async union; the sync client returns
        # an int.
        count = cast(int, redis_client.incr(key))
        if count == 1:
            # First hit of this window: expire the counter so it self-resets.
            redis_client.expire(key, 60)
    except RedisError as exc:
        logger.warning("rate-limit backend unavailable (%s); failing open", exc)
        return True, 0
    if count > limit:
        return False, 60 - int(now % 60)
    return True, 0


def _reject(retry_after: int) -> None:
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests",
        headers={"Retry-After": str(retry_after)},
    )


def enforce_enrollment_create_rate(current_user: CurrentUser) -> None:
    """Per-authenticated-user rate limit on ``POST /enrollment/create``.

    Superusers are exempt (D2). Runs as a route dependency, so a 429 is raised
    before the handler persists anything.
    """
    if current_user.is_superuser:
        return
    allowed, retry_after = _within_fixed_window(
        "enroll_create",
        str(current_user.id),
        settings.ENROLLMENT_CREATE_RATE_PER_MIN,
    )
    if not allowed:
        _reject(retry_after)


def enforce_enrollment_confirm_rate(request: Request) -> None:
    """Per-source rate limit on ``POST /enrollment/confirm/{session_id}``.

    In addition to the existing ≤3-attempts-per-session cap. The source is the
    leftmost forwarded hop (see ``client_source``); an unknown source shares one
    bucket rather than escaping the limit.
    """
    allowed, retry_after = _within_fixed_window(
        "enroll_confirm",
        client_source(request) or "unknown",
        settings.ENROLLMENT_CONFIRM_RATE_PER_MIN,
    )
    if not allowed:
        _reject(retry_after)
