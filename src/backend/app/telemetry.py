"""Telemetry: PostHog (product analytics), Sentry (error tracking), Upstash
(real-time cache + rate limiting), and structured console logging. Each is a
graceful no-op when its credential is absent, so the platform runs offline."""

from __future__ import annotations

import logging
import sys
from typing import Any

from app.config import settings

# ---------------------------------------------------------------- logging
def _configure_logging() -> None:
    root = logging.getLogger("cogito")
    root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    if not root.handlers:
        # stderr keeps stdout clean for MCP stdio protocol (and containers
        # capture both streams anyway).
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)s %(name)s: %(message)s", "%H:%M:%S"
            )
        )
        root.addHandler(h)


_configure_logging()
log = logging.getLogger("cogito")

# ---------------------------------------------------------------- Sentry
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            integrations=[FastApiIntegration()],
            traces_sample_rate=getattr(settings, "sentry_traces_sample_rate", 1.0),
            environment=settings.cogito_env,
        )
        log.info("Sentry enabled")
except Exception as e:  # noqa: BLE001
    log.warning(f"Sentry disabled: {e}")


def capture_exception(exc: BaseException, extras: dict[str, Any] | None = None) -> None:
    try:
        sentry_sdk.capture_exception(exc)
        if extras and getattr(sentry_sdk, "set_context", None):
            sentry_sdk.set_context("cogito", extras)
    except Exception:  # noqa: BLE001
        log.error("error captured by sentry", exc_info=exc)


# ---------------------------------------------------------------- PostHog
_posthog = None


def posthog():
    global _posthog
    if _posthog is None:
        if settings.posthog_api_key:
            import posthog

            posthog.project_api_key = settings.posthog_api_key
            posthog.host = settings.posthog_host
            _posthog = posthog
            log.info("PostHog enabled")
        else:
            _posthog = False
    return _posthog if _posthog else None


def capture(event: str, props: dict[str, Any] | None = None) -> None:
    ph = posthog()
    if ph:
        try:
            ph.capture(
                distinct_id=settings.posthog_distinct_id,
                event=event,
                properties=props or {},
            )
        except Exception as e:  # noqa: BLE001
            log.debug(f"posthog capture skipped: {e}")


# ---------------------------------------------------------------- Redis / Upstash
_redis = None


def redis_client():
    """Returns a redis.asyncio client, or an Upstash REST client if configured."""
    global _redis
    if _redis is not None:
        return _redis
    try:
        if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:

            from app.integrations.upstash import UpstashRestClient

            _redis = UpstashRestClient(
                settings.upstash_redis_rest_url, settings.upstash_redis_rest_token
            )
            log.info("Upstash REST enabled")
            return _redis
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        log.info("Redis enabled")
        return _redis
    except Exception as e:  # noqa: BLE001
        log.warning(f"Redis disabled: {e}")
        _redis = None
        return None


async def rate_limit(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    """Returns (allowed, remaining). Falls back to allow-everything if no Redis."""
    r = redis_client()
    if r is None:
        return True, limit
    try:
        return await r.sliding_window(key, limit, window_seconds)
    except Exception:  # noqa: BLE001
        return True, limit


async def cache_get(key: str):
    r = redis_client()
    if r is None:
        return None
    try:
        return await r.get(key)
    except Exception:  # noqa: BLE001
        return None


async def cache_set(key: str, value: str, ttl: int = 300) -> None:
    r = redis_client()
    if r is None:
        return
    try:
        await r.set(key, value, ex=ttl)
    except Exception:  # noqa: BLE001
        pass