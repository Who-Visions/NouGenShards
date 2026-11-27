"""backfill_recent paces arXiv API calls: a 3 s gap before each, none after the last."""
import importlib.util
from pathlib import Path

import pytest

from nougen_shards import arxiv_radar

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom">{}</feed>"""
ENTRY = ("<entry><id>http://arxiv.org/abs/{aid}v1</id><title>t {aid}</title>"
         "<summary>s</summary><published>2026-11-20T00:00:00Z</published></entry>")


class _Resp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body


def _load_lab(tmp_path, monkeypatch):
    monkeypatch.setenv("NOUGEN_VAULT_DIR", str(tmp_path / "vault"))
    path = arxiv_radar.VENDORED_RADAR_DIR / "arxiv_lab_watch.py"
    spec = importlib.util.spec_from_file_location("_vend_lab_pacing", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("n_ids, api_calls", [(3, 1), (61, 2), (120, 2), (121, 3)])
def test_sleep_precedes_every_api_call_and_never_trails(tmp_path, monkeypatch, n_ids, api_calls):
    lab = _load_lab(tmp_path, monkeypatch)
    ids = [f"2611.{i:05d}" for i in range(n_ids)]
    html = "".join(f'<a href="/abs/{a}">x</a>' for a in ids).encode()
    events = []

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        if "/list/" in url:
            events.append("list")
            return _Resp(html)
        events.append("api")
        chunk = url.split("id_list=")[1].split(",")
        return _Resp(ATOM.format("".join(ENTRY.format(aid=a) for a in chunk)).encode())

    monkeypatch.setattr(lab.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(lab.time, "sleep", lambda s: events.append(f"sleep{s}"))

    out = lab.backfill_recent("cs.AR")

    assert [e["id"] for e in out] == ids
    assert events == ["list"] + ["sleep3", "api"] * api_calls
    assert events[-1] == "api"  # no dead wait after the final request


def test_no_ids_means_no_api_call_and_no_sleep(tmp_path, monkeypatch):
    lab = _load_lab(tmp_path, monkeypatch)
    events = []
    monkeypatch.setattr(lab.urllib.request, "urlopen",
                        lambda req, timeout=None: events.append("list") or _Resp(b"<html></html>"))
    monkeypatch.setattr(lab.time, "sleep", lambda s: events.append("sleep"))
    assert lab.backfill_recent("cs.AR") == []
    assert events == ["list"]
