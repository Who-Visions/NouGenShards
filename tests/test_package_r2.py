"""R2 distribution of the tester package: pack, scan, publish, share, install."""
import datetime as dt
import json
import os
import random
import string
import subprocess
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from nougen_shards import mesh, package_r2 as pr


@pytest.fixture(autouse=True)
def clean_env(tmp_path, monkeypatch):
    for k in list(os.environ):
        if k.startswith(("NOUGEN_", "NGS_", "R2_", "CLOUDFLARE_")):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "user"))
    monkeypatch.setenv("NOUGEN_ROOT", str(tmp_path / "user" / ".nougen"))
    monkeypatch.setattr(pr, "_setting", lambda names: next((os.environ[n] for n in names if os.environ.get(n)), None))


def _fake_key(prefix: str, n: int) -> str:
    return prefix + "".join(random.choices(string.ascii_letters + string.digits, k=n))


def _git_repo(path: Path, files: dict) -> Path:
    path.mkdir(parents=True)
    for rel, text in files.items():
        f = path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    for argv in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(path), *argv], check=True, env=env)
    return path


def _package(tmp_path, relay_files, monkeypatch):
    repos = tmp_path / "repos"
    pkg = {"schema": "nougen-package/1", "name": "nougen-tester",
           "repos": {"relay": {"exclude": ["logs/**"]}}}
    _git_repo(repos / mesh.REPOS["shards"], {"nougen.package.json": json.dumps(pkg), "README.md": "shards\n"})
    _git_repo(repos / mesh.REPOS["relay"], relay_files)
    monkeypatch.setenv("NOUGEN_REPOS_DIR", str(repos))
    return repos


def test_presign_matches_the_published_sigv4_example():
    url = pr.presign("GET", "https://examplebucket.s3.amazonaws.com/test.txt", "AKIAIOSFODNN7EXAMPLE",
                     "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", expires=86400, region="us-east-1",
                     now=dt.datetime(2013, 5, 24, tzinfo=dt.timezone.utc))
    assert url.endswith("X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404")


def test_presign_refuses_more_than_seven_days():
    with pytest.raises(ValueError):
        pr.presign("GET", "https://h/b/k", "a", "s", expires=8 * 86400)


def test_scan_finds_keys_and_skips_placeholders():
    text = f'k = "{_fake_key("sk-ant-api03-", 40)}"\nrefresh = "1//0{_fake_key("", 40)}"\nTOKEN = "your-token-here-xxxxxxxxxxxx"\n'
    kinds = {k for k, _, _ in pr.scan_text(text)}
    assert {"anthropic_key", "google_oauth_refresh"} <= kinds
    assert all(line in (1, 2) for _, line, _ in pr.scan_text(text))


def test_scan_finds_google_aq_keys_and_bearer_tokens():
    aq, bearer = _fake_key("AQ.Ab8RN6", 40), _fake_key("", 40).lower()
    text = f'"X-Goog-Api-Key: {aq}"\n"Authorization": "Bearer {bearer}"\n"Authorization": "Bearer <REDACTED_HF_KEY>"\n'
    kinds = [k for k, _, _ in pr.scan_text(text)]
    assert "google_aq_key" in kinds and "bearer_token" in kinds
    assert all(line in (1, 2) for _, line, _ in pr.scan_text(text))


def test_pack_excludes_runtime_data_and_writes_a_manifest(tmp_path, monkeypatch):
    _package(tmp_path, {"src/app.py": "print('hi')\n",
                        "logs/old.json": json.dumps({"refresh_token": "1//0" + _fake_key("", 40)})}, monkeypatch)
    out = pr.pack(None, str(tmp_path / "dist"), only=["shards", "relay"])
    assert out["ok"] and set(out["repos"]) == {"shards", "relay"}
    manifest = json.loads((tmp_path / "dist" / "manifest.json").read_text())
    assert manifest["schema"] == pr.SCHEMA
    import tarfile
    with tarfile.open(tmp_path / "dist" / manifest["repos"]["relay"]["file"]) as tf:
        names = tf.getnames()
    assert any(n.endswith("src/app.py") for n in names) and not any("/logs/" in n for n in names)
    assert not any("/.git/" in n for n in names)


def test_pack_refuses_a_repo_with_a_leaked_key(tmp_path, monkeypatch):
    _package(tmp_path, {"src/conf.py": f'KEY = "{_fake_key("hf_", 34)}"\n'}, monkeypatch)
    out = pr.pack(None, str(tmp_path / "dist"), only=["shards", "relay"])
    assert not out["ok"] and "relay" in out["refused"] and "relay" not in out["repos"]
    finding = out["refused"]["relay"]["findings"][0]
    assert {k: finding[k] for k in ("file", "line", "kind")} == {
        "file": f"{mesh.REPOS['relay']}/src/conf.py", "line": 1, "kind": "huggingface_token"}
    assert "hf_" not in json.dumps(out)  # the value itself is never reported


def test_scan_allow_passes_a_known_fixture_and_still_blocks_new_values():
    fixture, fresh = _fake_key("ghp_", 36), _fake_key("ghp_", 36)
    allow = [pr.value_id(fixture)]
    assert pr.scan_text(f'a = "{fixture}"', allow) == []
    assert [h[0] for h in pr.scan_text(f'a = "{fixture}"\nb = "{fresh}"', allow)] == ["github_token"]
    assert pr.scan_text('ENV_KEY = "NOUGEN_CLIENT_SECRET_NAME_HERE"') == []  # an env var name, not a key


def test_missing_r2_settings_name_every_key():
    with pytest.raises(pr.R2ConfigError) as e:
        pr.r2_settings()
    msg = str(e.value)
    for name in ("NOUGEN_R2_ACCOUNT_ID", "NOUGEN_R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        assert name in msg


class _FakeR2(BaseHTTPRequestHandler):
    store: dict = {}

    def log_message(self, *a):
        pass

    def _key(self):
        return urllib.parse.urlsplit(self.path).path

    def do_PUT(self):
        assert self.headers["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AK/")
        self.store[self._key()] = self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200 if self._key() in self.store else 404)
        self.end_headers()

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        assert "X-Amz-Signature" in q or self.headers.get("Authorization")
        body = self.store.get(self._key())
        self.send_response(200 if body is not None else 404)
        self.end_headers()
        self.wfile.write(body or b"")


def test_publish_share_install_round_trip(tmp_path, monkeypatch):
    _package(tmp_path, {"src/app.py": "print('hi')\n"}, monkeypatch)
    assert pr.pack(None, str(tmp_path / "dist"), only=["shards", "relay"])["ok"]
    _FakeR2.store = {}
    srv = HTTPServer(("127.0.0.1", 0), _FakeR2)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("NOUGEN_R2_ENDPOINT", f"http://127.0.0.1:{srv.server_port}")
        monkeypatch.setenv("NOUGEN_R2_BUCKET", "bkt")
        monkeypatch.setenv("NOUGEN_R2_ACCESS_KEY_ID", "AK")
        monkeypatch.setenv("NOUGEN_R2_SECRET_ACCESS_KEY", "SK")
        dry = pr.publish(str(tmp_path / "dist"), dry_run=True)
        assert dry["dry_run"] and not _FakeR2.store
        first = pr.publish(str(tmp_path / "dist"))
        assert "/bkt/" not in json.dumps(first["uploaded"]) and len(first["uploaded"]) == 4  # 2 tarballs, installer, manifest
        again = pr.publish(str(tmp_path / "dist"))
        assert len(again["present"]) == 2 and len(again["uploaded"]) == 2  # unchanged tarballs are skipped
        link = pr.share(days=1)
        assert "X-Amz-Expires=86400" in link["link"] and "nougen-install.py" in link["command"]
        got = pr.install_from(link["link"], str(tmp_path / "tester"))
        assert {r["state"] for r in got["repos"].values()} == {"installed"}
        assert (tmp_path / "tester" / mesh.REPOS["relay"] / "src" / "app.py").read_text() == "print('hi')\n"
    finally:
        srv.shutdown()


def test_publish_refuses_a_tampered_tarball(tmp_path, monkeypatch):
    _package(tmp_path, {"src/app.py": "x = 1\n"}, monkeypatch)
    pr.pack(None, str(tmp_path / "dist"), only=["shards", "relay"])
    manifest = json.loads((tmp_path / "dist" / "manifest.json").read_text())
    (tmp_path / "dist" / manifest["repos"]["relay"]["file"]).write_bytes(b"changed")
    with pytest.raises(pr.R2Error):
        pr.publish(str(tmp_path / "dist"), settings={"endpoint": "http://127.0.0.1:9", "bucket": "b", "prefix": "p",
                                                     "signer": pr._Signer("a", "s"), "region": "auto"})
