import threading
import time

from app.core.enums import RefreshStatus
from app.services.cache import TTLCache


def test_fresh_cache_hit_returns_same_value_without_recomputing():
    cache = TTLCache()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    v1, s1, a1 = cache.get_or_refresh("k", 10.0, compute)
    v2, s2, a2 = cache.get_or_refresh("k", 10.0, compute)

    assert v1 == v2 == 1
    assert calls["n"] == 1
    assert s2 in (RefreshStatus.FRESH, RefreshStatus.CACHED)


def test_expired_cache_triggers_recomputation():
    cache = TTLCache()
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return calls["n"]

    cache.get_or_refresh("k", 0.01, compute)
    time.sleep(0.05)
    v2, s2, a2 = cache.get_or_refresh("k", 0.01, compute)

    assert calls["n"] == 2
    assert v2 == 2
    assert s2 == RefreshStatus.FRESH


def test_stale_fallback_preserves_last_good_snapshot_on_refresh_failure():
    cache = TTLCache()

    def good():
        return "good-value"

    def bad():
        raise RuntimeError("provider down")

    cache.get_or_refresh("k", 0.01, good)
    time.sleep(0.05)
    value, status, age = cache.get_or_refresh("k", 0.01, bad)

    assert value == "good-value"
    assert status == RefreshStatus.STALE_FALLBACK


def test_no_snapshot_ever_succeeded_raises():
    cache = TTLCache()

    def always_fails():
        raise RuntimeError("no data")

    try:
        cache.get_or_refresh("k", 10.0, always_fails)
        assert False, "expected an exception when no prior snapshot exists"
    except RuntimeError:
        pass


def test_per_symbol_concurrency_lock_prevents_duplicate_recomputation():
    cache = TTLCache()
    calls = {"n": 0}
    lock = threading.Lock()

    def slow_compute():
        with lock:
            calls["n"] += 1
        time.sleep(0.2)
        return "computed"

    results = []

    def worker():
        v, s, a = cache.get_or_refresh("SPX", 5.0, slow_compute)
        results.append((v, s))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls["n"] == 1, "only one thread should have actually recomputed (single-flight)"
    assert all(v == "computed" for v, _ in results)


def test_simultaneous_requests_for_different_symbols_do_not_block_each_other():
    cache = TTLCache()
    start_times = {}
    lock = threading.Lock()

    def compute_for(symbol):
        def _inner():
            with lock:
                start_times[symbol] = time.perf_counter()
            time.sleep(0.15)
            return symbol
        return _inner

    def worker(symbol):
        cache.get_or_refresh(symbol, 5.0, compute_for(symbol))

    t1 = threading.Thread(target=worker, args=("SPX",))
    t2 = threading.Thread(target=worker, args=("TSLA",))
    t0 = time.perf_counter()
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    total_elapsed = time.perf_counter() - t0

    # If they ran sequentially this would take >=0.3s; concurrently, ~0.15-0.2s.
    assert total_elapsed < 0.3
