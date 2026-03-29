from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    def __init__(self, ttl_seconds: int, max_entries: int = 1024) -> None:
        self.ttl_seconds = max(1, ttl_seconds)
        self.max_entries = max(1, max_entries)
        self._entries: OrderedDict[K, CacheEntry[V]] = OrderedDict()

    def get(self, key: K) -> V | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= monotonic():
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return entry.value

    def set(self, key: K, value: V) -> None:
        self._entries[key] = CacheEntry(value=value, expires_at=monotonic() + self.ttl_seconds)
        self._entries.move_to_end(key)
        self._evict_if_needed()

    def pop(self, key: K) -> None:
        self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()

    def force_expire(self, key: K) -> None:
        entry = self._entries.get(key)
        if entry is None:
            return
        entry.expires_at = 0.0

    def _evict_if_needed(self) -> None:
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)


@dataclass(slots=True)
class CacheEntry(Generic[V]):
    value: V
    expires_at: float
