"""The federated lane pool must be shared and bounded.

Regression for a thread leak that wedged a long-lived node three times in one
evening. `federated_retrieve` used to build a fresh ThreadPoolExecutor per
call and close it with `shutdown(wait=False)`, which does not stop running
threads - it only declines to wait. A lane that overran the recall deadline
therefore left its worker alive and unreferenced, with nothing capping how
many accumulated. Lanes overrun routinely (an unreachable local vault, a cloud
peer returning 502), so the count climbed on a steady drip until the process
could no longer accept connections: 7,077 threads, HTTP dead on every path,
while the OS still reported it as responding and netstat still showed a
healthy LISTENING socket.
"""
import threading

from nougen_shards import federation


def test_pool_is_shared_across_calls():
    """A per-call executor is the leak. One pool, reused, is the fix."""
    assert federation._lane_executor() is federation._lane_executor()


def test_pool_is_bounded_and_env_sized(monkeypatch):
    monkeypatch.setenv("NOUGEN_FED_LANE_POOL", "7")
    assert federation._lane_pool_size() == 7


def test_pool_size_has_a_floor(monkeypatch):
    """Too small a pool would serialise the lanes; there are four of them."""
    monkeypatch.setenv("NOUGEN_FED_LANE_POOL", "1")
    assert federation._lane_pool_size() >= 4


def test_bad_pool_size_falls_back_instead_of_raising(monkeypatch):
    monkeypatch.setenv("NOUGEN_FED_LANE_POOL", "not-a-number")
    assert federation._lane_pool_size() >= 4


def test_threads_do_not_grow_per_call(monkeypatch):
    """The actual regression: repeated retrievals must not add threads.

    Every lane is stubbed to hang past its deadline, which is precisely the
    condition that used to orphan a thread per lane per call. With a shared
    bounded pool the total is capped no matter how many calls are made.
    """
    monkeypatch.setenv("NOUGEN_FED_LANE_POOL", "8")
    monkeypatch.setenv("NOUGEN_RECALL_DEADLINE_S", "0.05")
    # Reset so this test owns the pool sizing.
    monkeypatch.setattr(federation, "_LANE_EXECUTOR", None, raising=False)

    stop = threading.Event()

    def _hang(*_a, **_k):
        stop.wait(5)          # outlives the deadline, like a dead peer
        return []

    # The lane fetchers are closures inside federated_retrieve, so stub the
    # underlying callables they delegate to instead.
    monkeypatch.setattr(federation.core, "retrieve", _hang, raising=False)
    monkeypatch.setattr(federation, "query_external_dbs", _hang, raising=False)
    monkeypatch.setattr(federation, "query_cloud_shards", _hang, raising=False)
    monkeypatch.setattr(federation, "query_local_vaults", _hang, raising=False)

    try:
        baseline = threading.active_count()
        for _ in range(6):
            try:
                federation.federated_retrieve("probe", limit=1)
            except Exception:       # pylint: disable=broad-except
                pass                # a stubbed lane may raise; thread count is the assertion
        grown = threading.active_count() - baseline
        cap = federation._lane_pool_size()
        assert grown <= cap, (
            f"6 calls added {grown} threads against a pool cap of {cap}; "
            "the per-call executor leak is back")
    finally:
        stop.set()


def test_shutdown_is_not_called_on_the_shared_pool(monkeypatch):
    """Retiring the shared pool mid-flight would break concurrent callers."""
    pool = federation._lane_executor()
    calls = []
    monkeypatch.setattr(pool, "shutdown", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(federation.core, "retrieve", lambda *a, **k: [], raising=False)
    monkeypatch.setattr(federation, "query_external_dbs", lambda *a, **k: [], raising=False)
    monkeypatch.setattr(federation, "query_cloud_shards", lambda *a, **k: [], raising=False)
    monkeypatch.setattr(federation, "query_local_vaults", lambda *a, **k: [], raising=False)
    try:
        federation.federated_retrieve("probe", limit=1)
    except Exception:               # pylint: disable=broad-except
        pass
    assert not calls, "federated_retrieve must not shut down the shared pool"
