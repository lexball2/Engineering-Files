"""Bounded, expiring conversation memory for development and single-process use."""
import threading
import time
import json
from dataclasses import dataclass, field

from backend.config import settings


@dataclass
class _Session:
    items: list[dict[str, str]] = field(default_factory=list)
    touched_at: float = field(default_factory=time.monotonic)


class ConversationMemory:
    def __init__(self, max_history: int | None = None):
        self.max_history = max_history or settings.MAX_HISTORY_ROUNDS
        self._store: dict[str, _Session] = {}
        self._lock = threading.Lock()

    def _purge_locked(self, now: float) -> None:
        expired = [
            key for key, session in self._store.items()
            if now - session.touched_at >= settings.MEMORY_TTL_SECONDS
        ]
        for key in expired:
            self._store.pop(key, None)
        if len(self._store) > settings.MAX_MEMORY_SESSIONS:
            oldest = sorted(self._store, key=lambda key: self._store[key].touched_at)
            for key in oldest[: len(self._store) - settings.MAX_MEMORY_SESSIONS]:
                self._store.pop(key, None)

    def add(self, memory_key: str, question: str, answer: str) -> None:
        now = time.monotonic()
        with self._lock:
            self._purge_locked(now)
            session = self._store.setdefault(memory_key, _Session())
            session.items.append({"q": question, "a": answer})
            session.items = session.items[-self.max_history:]
            session.touched_at = now
            self._purge_locked(now)

    def get_raw(self, memory_key: str) -> list[dict[str, str]]:
        now = time.monotonic()
        with self._lock:
            self._purge_locked(now)
            session = self._store.get(memory_key)
            if not session:
                return []
            session.touched_at = now
            return [item.copy() for item in session.items]

    def get_history(self, memory_key: str, trunc_len: int = 300) -> str:
        history = self.get_raw(memory_key)
        if not history:
            return "（暂无历史对话）"
        lines = []
        for idx, item in enumerate(history, 1):
            answer = item["a"]
            short_answer = answer[:trunc_len] + "..." if len(answer) > trunc_len else answer
            lines.append(f"第{idx}轮 - 用户：{item['q']}\n第{idx}轮 - 助手：{short_answer}")
        return "\n".join(lines)

    def clear(self, memory_key: str) -> None:
        with self._lock:
            self._store.pop(memory_key, None)

    def clear_all(self) -> None:
        with self._lock:
            self._store.clear()


class RedisConversationMemory:
    def __init__(self, redis_url: str, max_history: int | None = None):
        from redis import Redis

        self.max_history = max_history or settings.MAX_HISTORY_ROUNDS
        self.client = Redis.from_url(redis_url, decode_responses=True, socket_timeout=3)

    @staticmethod
    def _key(memory_key: str) -> str:
        return f"kb:chat:{memory_key}"

    def add(self, memory_key: str, question: str, answer: str) -> None:
        key = self._key(memory_key)
        with self.client.pipeline(transaction=True) as pipeline:
            pipeline.rpush(key, json.dumps({"q": question, "a": answer}, ensure_ascii=False))
            pipeline.ltrim(key, -self.max_history, -1)
            pipeline.expire(key, settings.MEMORY_TTL_SECONDS)
            pipeline.execute()

    def get_raw(self, memory_key: str) -> list[dict[str, str]]:
        key = self._key(memory_key)
        values = self.client.lrange(key, 0, -1)
        if values:
            self.client.expire(key, settings.MEMORY_TTL_SECONDS)
        return [json.loads(value) for value in values]

    def get_history(self, memory_key: str, trunc_len: int = 300) -> str:
        history = self.get_raw(memory_key)
        if not history:
            return "（暂无历史对话）"
        lines = []
        for idx, item in enumerate(history, 1):
            answer = item["a"]
            short_answer = answer[:trunc_len] + "..." if len(answer) > trunc_len else answer
            lines.append(f"第{idx}轮 - 用户：{item['q']}\n第{idx}轮 - 助手：{short_answer}")
        return "\n".join(lines)

    def clear(self, memory_key: str) -> None:
        self.client.delete(self._key(memory_key))

    def clear_all(self) -> None:
        raise RuntimeError("Global Redis chat deletion is intentionally disabled")


memory = RedisConversationMemory(settings.REDIS_URL) if settings.REDIS_URL else ConversationMemory()
