"""
TTL cache with single-flight concurrency protection and
stale-while-revalidate semantics (sections 8-11 of the v0.1.1 hardening
spec).

This is intentionally a simple, dependency-free, thread-safe cache
suitable for a single-process FastAPI/uvicorn deployment. It is not a
distributed cache — for multi-process deployment, back this with Redis
using the same interface.

Key distinction preserved throughout: DATA FRESHNESS (how old the
underlying observed market data is — see DataStatus) is a different
concept from CACHE FRESHNESS (how old this computed snapshot is relative
to when it was cached — RefreshStatus). A cached analysis can be
CACHE-fresh while wrapping DATA that is STALE, and vice versa.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

from app.core.enums import RefreshStatus


@dataclass
class CacheEntry:
    value: Any
    created_at: float


class TTLCache:
    def __init__(self):
        self._store: Dict[str, CacheEntry] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()

    def _get_lock(self, key: str) -> threading.Lock:
        with self._meta_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def peek(self, key: str) -> Optional[Tuple[Any, float]]:
        """Returns (value, age_seconds) without triggering a refresh, or
        None if nothing has ever been cached for this key."""
        entry = self._store.get(key)
        if entry is None:
            return None
        return entry.value, time.time() - entry.created_at

    def get_or_refresh(
        self, key: str, ttl_seconds: float, compute_fn: Callable[[], Any]
    ) -> Tuple[Any, RefreshStatus, float]:
        """Single-flight, stale-while-revalidate cache access.

        Returns (value, refresh_status, cache_age_seconds).

        Behavior:
          - valid cache hit                -> (value, FRESH or CACHED, age)
          - expired, this call wins race   -> recompute -> (new_value, FRESH, 0.0)
          - expired, refresh fails         -> fall back to last good value,
                                               (value, STALE_FALLBACK, age)
          - expired, another call refreshing -> return last good value,
                                               (value, REFRESHING, age) if any exists,
                                               else block until the winner finishes.
          - no cache ever, refresh fails    -> re-raise (caller returns typed error).
        """
        now = time.time()
        entry = self._store.get(key)

        if entry is not None and (now - entry.created_at) < ttl_seconds:
            age = now - entry.created_at
            status = RefreshStatus.FRESH if age < ttl_seconds * 0.2 else RefreshStatus.CACHED
            return entry.value, status, age

        lock = self._get_lock(key)
        acquired = lock.acquire(blocking=False)

        if acquired:
            try:
                try:
                    new_value = compute_fn()
                    self._store[key] = CacheEntry(new_value, time.time())
                    return new_value, RefreshStatus.FRESH, 0.0
                except Exception:
                    if entry is not None:
                        age = time.time() - entry.created_at
                        return entry.value, RefreshStatus.STALE_FALLBACK, age
                    raise
            finally:
                lock.release()
        else:
            if entry is not None:
                age = now - entry.created_at
                return entry.value, RefreshStatus.REFRESHING, age
            # No data at all yet and someone else is computing it: wait
            # for them rather than failing outright or double-computing.
            lock.acquire()
            lock.release()
            entry2 = self._store.get(key)
            if entry2 is not None:
                return entry2.value, RefreshStatus.FRESH, time.time() - entry2.created_at
            raise RuntimeError(f"Cache refresh for key '{key}' failed with no prior snapshot available.")

    def invalidate(self, key: str) -> None:
        with self._meta_lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._meta_lock:
            self._store.clear()
            self._locks.clear()


# Process-wide cache instances, one per layer (section 8's pipeline):
# Provider -> Normalized Chain Cache -> Gamma Computation ->
# Analysis Snapshot Cache -> TV Payload Cache -> FastAPI.
chain_cache = TTLCache()
analysis_cache = TTLCache()
tv_payload_cache = TTLCache()
