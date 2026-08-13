"""Redis helper: login rate limit, JWT blacklist, refresh token store, concurrency semaphores."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from redis import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: Redis | None = None


def get_redis() -> Redis | None:
    global _redis
    if _redis is None:
        try:
            _redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2)
            _redis.ping()
        except Exception as exc:  # noqa: BLE001 - degrade gracefully in tests/local
            logger.warning("redis unavailable, degraded mode: %s", exc)
            _redis = None
    return _redis


def close_redis() -> None:
    global _redis
    if _redis is not None:
        _redis.close()
        _redis = None


# ------------------------------------------------------------- rate limit


def login_rate_limit(username: str) -> bool:
    """Return True if allowed. Limit LOGIN_MAX_FAILURES per minute, lock LOGIN_LOCK_MINUTES on exceed."""
    r = get_redis()
    if r is None:
        return True
    key = f"login:fail:{username}"
    lock = f"login:lock:{username}"
    if r.exists(lock):
        return False
    return True


def record_login_failure(username: str) -> int:
    """Increment failure count; returns current count."""
    r = get_redis()
    if r is None:
        return 0
    pipe = r.pipeline()
    key = f"login:fail:{username}"
    pipe.incr(key)
    pipe.expire(key, 60)
    count = pipe.execute()[0]
    if count >= settings.login_max_failures:
        r.setex(f"login:lock:{username}", settings.login_lock_minutes * 60, "1")
    return int(count)


def clear_login_failures(username: str) -> None:
    r = get_redis()
    if r is None:
        return
    r.delete(f"login:fail:{username}")


# ------------------------------------------------------------- JWT lifecycle


def blacklist_access(jti: str) -> None:
    r = get_redis()
    if r is None:
        return
    ttl = settings.access_token_expire_minutes * 60
    r.setex(f"bl:{jti}", ttl, "1")


def store_refresh(user_id: int, jti: str) -> None:
    r = get_redis()
    if r is None:
        return
    r.setex(f"rt:{user_id}", settings.refresh_token_expire_days * 86400, jti)


def validate_refresh(user_id: int, jti: str) -> bool:
    r = get_redis()
    if r is None:
        return True
    cur = r.get(f"rt:{user_id}")
    return bool(cur and cur == jti)


def revoke_refresh(user_id: int) -> None:
    r = get_redis()
    if r is None:
        return
    r.delete(f"rt:{user_id}")


# ------------------------------------------------------------- concurrency guard


def acquire_semaphore(key: str, limit: int, timeout: int = 30) -> bool:
    """Non-blocking acquire on Redis counter semaphore; returns False if full."""
    r = get_redis()
    if r is None:
        return True  # degraded mode: no enforcement in tests without redis
    lock_key = f"sem:lock:{key}"
    val_key = f"sem:{key}"
    acquired_lock = r.set(lock_key, "1", nx=True, ex=timeout)
    if not acquired_lock:
        return False
    try:
        cur = int(r.get(val_key) or 0)
        if cur < limit:
            r.set(val_key, cur + 1)
            return True
        return False
    finally:
        r.delete(lock_key)


def release_semaphore(key: str) -> None:
    r = get_redis()
    if r is None:
        return
    r.decr(f"sem:{key}")


# ------------------------------------------------------------- token buckets (rate limit)


def rate_limit(key: str, limit: int, per_seconds: int = 60) -> bool:
    """Simple fixed-window rate limit; returns True if allowed."""
    r = get_redis()
    if r is None:
        return True
    now = int(datetime.now(timezone.utc).timestamp())
    window = now // per_seconds
    rk = f"rl:{key}:{window}"
    count = r.incr(rk)
    if count == 1:
        r.expire(rk, per_seconds + 1)
    return count <= limit
