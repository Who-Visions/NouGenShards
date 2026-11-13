"""nougentube_ingest answers with a job id at once; a repeat rejoins the same job."""
import threading
import time

import app


def _wait(job_id, until=("done", "error"), timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        job = app.nougentube_job(job_id)
        if job["status"] in until:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} stuck: {app.nougentube_job(job_id)}")


def _fn(tool):
    return getattr(tool, "fn", tool)


def test_ingest_returns_job_then_result(monkeypatch):
    monkeypatch.setattr(app, "_run_nougentube", lambda url, dry_run, limit: {"processed": 1})
    url = "https://www.youtube.com/watch?v=job0000000a"
    job = app._tube_job_submit(url, 1)
    assert job["job_id"].startswith("tube-") and job["status"] in ("queued", "running", "done")
    assert _wait(job["job_id"])["result"] == {"processed": 1}


def test_repeat_while_running_does_not_start_a_second_ingest(monkeypatch):
    gate, calls = threading.Event(), []

    def slow(url, dry_run, limit):
        calls.append(url)
        gate.wait(5)
        return {"processed": 1}

    monkeypatch.setattr(app, "_run_nougentube", slow)
    url = "https://www.youtube.com/watch?v=job0000000b"
    first = app._tube_job_submit(url, 1)
    _wait(first["job_id"], until=("running",))
    second = app._tube_job_submit(url, 1)
    assert second["job_id"] == first["job_id"] and second.get("repeat") is True
    gate.set()
    _wait(first["job_id"])
    assert len(calls) == 1


def test_errors_are_reported_not_raised(monkeypatch):
    def boom(url, dry_run, limit):
        raise RuntimeError("upstream 524")

    monkeypatch.setattr(app, "_run_nougentube", boom)
    job = app._tube_job_submit("https://www.youtube.com/watch?v=job0000000c", 1)
    done = _wait(job["job_id"])
    assert done["status"] == "error" and "524" in done["error"]


def test_unknown_job():
    assert app.nougentube_job("tube-nope")["status"] == "unknown"
