"""
Optional background refresh service (section 12).

Keeps configured symbols' analysis snapshots warm on a fixed interval so
TV clients rarely hit a cold cache. Designed for clean startup/shutdown,
exception isolation (one symbol's failure never kills the loop or other
symbols), no duplicate scheduler instances, and testability (call
`tick()` directly in tests instead of waiting on real sleep intervals).
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class BackgroundRefreshService:
    _instance: Optional["BackgroundRefreshService"] = None
    _instance_lock = threading.Lock()

    def __init__(self, symbols: List[str], interval_seconds: float, refresh_fn: Callable[[str], None]):
        self.symbols = symbols
        self.interval_seconds = interval_seconds
        self.refresh_fn = refresh_fn
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @classmethod
    def get_instance(
        cls, symbols: List[str], interval_seconds: float, refresh_fn: Callable[[str], None]
    ) -> "BackgroundRefreshService":
        """Guards against duplicate scheduler instances within a process."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(symbols, interval_seconds, refresh_fn)
            return cls._instance

    def tick(self) -> None:
        """Runs exactly one refresh pass over all configured symbols.
        Exception in one symbol never prevents the others from running
        (exception isolation) — used directly by tests, and internally
        by the real background loop.
        """
        for symbol in self.symbols:
            try:
                self.refresh_fn(symbol)
            except Exception:  # noqa: BLE001
                logger.exception("Background refresh failed for symbol %s", symbol)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.tick()
            self._stop_event.wait(self.interval_seconds)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return  # already running; no duplicate loop
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="gamma-background-refresh")
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @classmethod
    def reset_singleton_for_tests(cls) -> None:
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance.stop()
            cls._instance = None
