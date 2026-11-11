"""Read-only connection pool must not keep connections of finished threads."""
import sqlite3
import threading

from nougen_shards import core


def _fresh_db(tmp_path, monkeypatch):
    db = tmp_path / "grid_0.db"
    sqlite3.connect(db).execute("CREATE TABLE t (x INTEGER)").connection.commit()
    monkeypatch.setattr(core, "get_db_path", lambda index: db)
    core.close_readonly_pool()
    return db


def test_finished_threads_release_their_connections(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)

    def worker():
        core.get_readonly_connection(0).execute("SELECT 1")

    for _ in range(20):
        t = threading.Thread(target=worker)
        t.start()
        t.join()
    core.get_readonly_connection(0)  # the call that triggers pruning
    with core._RO_POOL_LOCK:
        owners = {key[0] for key in core._RO_CONN_POOL}
    alive = {t.ident for t in threading.enumerate()}
    assert owners <= alive
    assert len(core._RO_CONN_POOL) == 1  # only this thread's connection remains
    core.close_readonly_pool()


def test_pool_cap_is_configurable(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    monkeypatch.setenv("NOUGEN_RO_POOL_MAX", "3")
    gate = threading.Event()
    started = []

    def holder():
        core.get_readonly_connection(0)
        started.append(1)
        gate.wait(5)

    threads = [threading.Thread(target=holder) for _ in range(6)]
    for t in threads:
        t.start()
    while len(started) < 6:
        pass
    with core._RO_POOL_LOCK:
        size = len(core._RO_CONN_POOL)
    gate.set()
    for t in threads:
        t.join()
    assert size <= 3
    core.close_readonly_pool()
