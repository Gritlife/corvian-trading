import time

from app.services.refresh_service import BackgroundRefreshService


def test_tick_calls_refresh_fn_for_every_configured_symbol():
    calls = []

    def refresh_fn(symbol):
        calls.append(symbol)

    svc = BackgroundRefreshService(symbols=["SPX", "TSLA"], interval_seconds=999, refresh_fn=refresh_fn)
    svc.tick()
    assert calls == ["SPX", "TSLA"]


def test_tick_isolates_exceptions_per_symbol():
    calls = []

    def refresh_fn(symbol):
        if symbol == "BAD":
            raise RuntimeError("boom")
        calls.append(symbol)

    svc = BackgroundRefreshService(symbols=["SPX", "BAD", "TSLA"], interval_seconds=999, refresh_fn=refresh_fn)
    svc.tick()  # must not raise
    assert calls == ["SPX", "TSLA"]


def test_start_and_stop_is_clean_and_no_duplicate_thread():
    def refresh_fn(symbol):
        pass

    svc = BackgroundRefreshService(symbols=["SPX"], interval_seconds=0.05, refresh_fn=refresh_fn)
    svc.start()
    assert svc.is_running
    svc.start()  # calling start twice must not create a second thread
    time.sleep(0.15)
    svc.stop()
    assert not svc.is_running


def test_get_instance_returns_singleton():
    BackgroundRefreshService.reset_singleton_for_tests()

    def refresh_fn(symbol):
        pass

    a = BackgroundRefreshService.get_instance(["SPX"], 10.0, refresh_fn)
    b = BackgroundRefreshService.get_instance(["TSLA"], 20.0, refresh_fn)
    assert a is b  # second call does not create a new instance
    BackgroundRefreshService.reset_singleton_for_tests()
