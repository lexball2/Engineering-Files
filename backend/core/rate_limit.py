import threading
import time
import logging
from collections import deque

from fastapi import Request

from backend.config import settings
from backend.core.security import decode_token

logger = logging.getLogger(__name__)

class RequestRateLimiter:
    """Bounded process-local limiter; use Redis at the ingress for multi-instance deployments."""

    def __init__(self, max_keys: int = 10_000):
        self.max_keys = max_keys
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._redis = None
        if settings.REDIS_URL:
            from redis import Redis

            self._redis = Redis.from_url(settings.REDIS_URL, socket_timeout=2)

    def _identity(self, request: Request) -> str:
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        token = token or request.cookies.get(settings.COOKIE_NAME, "")
        payload = decode_token(token) if token else None
        if payload and payload.get("sub"):
            return f"user:{payload['sub']}"
        host = request.client.host if request.client else "unknown"
        return f"ip:{host}"

    def _limit_for_path(self, path: str) -> int:
        if path.startswith(("/api/images/understand", "/api/images/search/image", "/api/images/upload", "/api/image-assets/upload-batch")):
            return settings.EXPENSIVE_RATE_LIMIT_PER_MINUTE
        return settings.API_RATE_LIMIT_PER_MINUTE

    def allow(self, request: Request) -> bool:
        now = time.monotonic()
        key = f"{self._identity(request)}:{request.url.path}"
        limit = self._limit_for_path(request.url.path)
        if self._redis is not None:
            redis_key = f"kb:rate:{key}:{int(time.time() // 60)}"
            try:
                count = self._redis.incr(redis_key)
                if count == 1:
                    self._redis.expire(redis_key, 61)
                return count <= limit
            except Exception:
                logger.exception("Redis rate limiter failed; using bounded local fallback")
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and now - events[0] >= 60:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            if len(self._events) > self.max_keys:
                stale = [name for name, values in self._events.items() if not values or now - values[-1] >= 60]
                for name in stale[: len(self._events) - self.max_keys]:
                    self._events.pop(name, None)
                if len(self._events) > self.max_keys:
                    self._events.pop(next(iter(self._events)), None)
        return True


request_rate_limiter = RequestRateLimiter()
