"""Bring up the shards grid: node on NGS_PORT, then the named tunnel.

Tokens come from the shards keymaker (DPAPI); nothing prints a secret value,
fingerprints only. Every environment-shaped value resolves env-first.
"""
import msvcrt
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def _path_env(name, fallback):
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else Path(fallback).expanduser()


NOUGEN_HOME = _path_env("NOUGEN_HOME", Path.home() / ".nougen")
_HERE = Path(__file__).resolve()
_repo_override = os.environ.get("NGS_REPO", "").strip()
_repo_candidates = ([Path(_repo_override).expanduser()] if _repo_override else [])
_repo_candidates.extend((_HERE.parent.parent, Path.cwd()))
REPO = next((p for p in _repo_candidates if (p / "src").is_dir()), _HERE.parent.parent)
SECRETS_DB = _path_env("NOUGEN_SECRETS_DB", NOUGEN_HOME / "secrets" / "shards_secrets.db")
sys.path.insert(0, str(NOUGEN_HOME / "bin"))
import keymaker_peel  # noqa: E402
PORT = os.environ.get("NGS_PORT", "4444")
BIND = os.environ.get("NGS_BIND_HOST", "127.0.0.1")
_cloudflared_override = os.environ.get("NOUGEN_CLOUDFLARED_EXE", "").strip()
_cloudflared_candidates = ([Path(_cloudflared_override)] if _cloudflared_override else [])
_cloudflared_candidates.extend((
    _HERE.parent / "bin" / "cloudflared.exe",
    Path(shutil.which("cloudflared.exe") or ""),
    Path(os.environ.get("ProgramFiles(x86)", "")) / "cloudflared" / "cloudflared.exe",
    Path(os.environ.get("ProgramFiles", "")) / "cloudflared" / "cloudflared.exe",
))
CLOUDFLARED = next((str(p) for p in _cloudflared_candidates if str(p) and p.is_file()),
                   str(_HERE.parent / "bin" / "cloudflared.exe"))
SCRATCH = _path_env("NOUGEN_RUNTIME_DIR", NOUGEN_HOME / "bin")
SCRATCH.mkdir(parents=True, exist_ok=True)
PROBE_STATE_DIR = _path_env("NOUGEN_PROBE_STATE_DIR", NOUGEN_HOME / "state")
PROBE_STATE_DIR.mkdir(parents=True, exist_ok=True)
DETACHED = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0)
# Shared with node_lane.ps1 (same path there via $env:NOUGEN_NODE_LOCK) so
# neither launcher can spawn a competing uvicorn while the other is mid-start.
# 2026-08-27 incident: watchdog + manual node_lane.ps1 restart raced within
# the same second and stacked 4 uvicorn/ngs_node_serve processes on :4444,
# with Windows silently handing traffic to whichever bound last - the origin
# looked "up" to a PID check while actually serving nothing (context-canceled
# hangs on every request).
NODE_LOCK_PATH = _path_env("NOUGEN_NODE_LOCK", SCRATCH / "node_lane.lock")


class NodeLaunchLock:
    """Non-blocking cross-process exclusive lock via msvcrt.locking.

    Enter returns False (does not block) if another launcher already holds
    it - the caller should stand down rather than spawn a competitor.
    """

    def __init__(self, path):
        self.path = path
        self.fh = None

    def __enter__(self):
        self.fh = open(self.path, "a+")
        try:
            self.fh.seek(0)
            msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.fh.close()
            self.fh = None
            return False
        return True

    def __exit__(self, *exc):
        if self.fh:
            try:
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            self.fh.close()
            self.fh = None


def peel(pattern):
    rows = keymaker_peel.load(pattern, db=SECRETS_DB)
    if not rows:
        return None
    label, value, rotated = rows[0]
    print(f"secret {label} fp={keymaker_peel.fingerprint(value)} rotated={rotated[:10]}")
    return value


def port_up():
    try:
        req = urllib.request.Request(f"http://{BIND}:{PORT}/health")
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status
    except Exception as e:
        return f"down ({type(e).__name__})"


def rotate_log(path, cap=None):
    """Size-capped rotation so an append-forever log can't eat the disk."""
    cap = cap if cap is not None else int(os.environ.get("NOUGEN_GRID_LOG_MAX_BYTES", 10_000_000))
    try:
        if path.exists() and path.stat().st_size > cap:
            rolled = path.with_suffix(path.suffix + ".1")
            if rolled.exists():
                rolled.unlink()
            path.rename(rolled)
            print(f"rotated {path.name} -> {rolled.name} (> {cap} bytes)")
    except OSError as e:
        print(f"log rotation skipped ({type(e).__name__})")


def main():
    node_token = peel("NGS_NODE_TOKEN")
    if not node_token:
        print("FATAL: NGS_NODE_TOKEN not found")
        return 2

    rotate_log(SCRATCH / "ngs_node.log")
    rotate_log(SCRATCH / "cloudflared_tunnel.log")

    status = port_up()
    if isinstance(status, int):
        print(f"node already up on :{PORT} (health {status})")
    else:
        lock = NodeLaunchLock(NODE_LOCK_PATH)
        if not lock.__enter__():
            print("another launcher is already starting the node (lock held); standing down")
            return 0
        try:
            failed = _start_node(node_token)
        finally:
            lock.__exit__()
        if failed:
            return failed

    return _start_tunnel_if_needed()


def _start_node(node_token):
    # Re-check after acquiring the lock: the other launcher may have already
    # brought the node up while we were waiting.
    status = port_up()
    if isinstance(status, int):
        print(f"node came up while waiting for the lock (health {status})")
        return None
    env = dict(os.environ,
               NGS_NODE_TOKEN=node_token,
               NGS_PORT=PORT,
               NGS_BIND_HOST=BIND,
               PYTHONPATH=str(REPO / "src"),
               # The node dies silently under /search floods (08/25, twice
               # 08/27) with no Python traceback - the signature of a
               # native-level crash. faulthandler makes the next death
               # leave a stack in ngs_node.log instead of nothing.
               PYTHONFAULTHANDLER="1")
    # Google sign-in for the /authorize consent page: optional, the node
    # hides the button when these stay unset. Labels are env-overridable;
    # values go straight from the keymaker into the child env, never disk.
    google_id = peel(os.environ.get(
        "NOUGEN_GOOGLE_CLIENT_ID_LABEL", "NOUGEN_GOOGLE_OAUTH_CLIENT_ID"))
    google_secret = peel(os.environ.get(
        "NOUGEN_GOOGLE_CLIENT_SECRET_LABEL", "NOUGEN_GOOGLE_OAUTH_CLIENT_SECRET"))
    if google_id and google_secret:
        env["NOUGEN_GOOGLE_OAUTH_CLIENT_ID"] = google_id
        env["NOUGEN_GOOGLE_OAUTH_CLIENT_SECRET"] = google_secret
        print("google sign-in: configured")
    else:
        print("google sign-in: not configured (button hidden)")
    # Rhea's inference lanes: without a key in the child env the free
    # OpenRouter walk returns None instantly and /agent 500s with
    # "no inference lane available" (root-caused 2026-08-27). A validated
    # key is chosen from the store; label pattern env-overridable.
    if not os.environ.get("OPENROUTER_API_KEY"):
        or_key = peel(os.environ.get(
            "NOUGEN_OPENROUTER_KEY_LABEL", "OPENROUTER_KEY_NOUGENAI"))
        if or_key:
            env["OPENROUTER_API_KEY"] = or_key
            print("rhea free lane: openrouter key wired")
        else:
            print("rhea free lane: no openrouter key found (agent lane degraded)")
    # Rhea's Kimi lane rides the fleet's HF accounts: each account carries
    # small monthly Inference-Providers credit, and rhea_noir walks the
    # comma list when one 402s (the "free through a space" ride was always
    # these credits - one afternoon burned $0.09 of one account). Wire ALL
    # distinct hf_ tokens from both keymaker stores, not one.
    if not os.environ.get("NGS_INFERENCE_TOKENS"):
        hf_tokens = {}
        for pat in ("%HF_%", "%HUGGING%"):
            for db in (SECRETS_DB, None):
                try:
                    rows = keymaker_peel.load(pat, db=db, min_len=20)
                except Exception:
                    continue
                for _label, value, _rot in rows:
                    if value.startswith("hf_"):
                        hf_tokens[keymaker_peel.fingerprint(value)] = value
        if hf_tokens:
            env["NGS_INFERENCE_TOKENS"] = ",".join(hf_tokens.values())
            print(f"rhea kimi lane: {len(hf_tokens)} fleet hf token(s) wired")
    if not os.environ.get("NOUGEN_RHEA_MODEL"):
        env["NOUGEN_RHEA_MODEL"] = os.environ.get(
            "NOUGEN_KIMI_MODEL", "moonshotai/Kimi-K3")
        print(f"rhea kimi model: {env['NOUGEN_RHEA_MODEL']}")
    log = SCRATCH / "ngs_node.log"
    python_exe = REPO / ".venv" / "Scripts" / "python.exe"
    if not python_exe.is_file():
        python_exe = Path(sys.executable)
    with open(log, "ab") as fh:
        proc = subprocess.Popen(
            [str(python_exe), "-m",
             "uvicorn", "app:app", "--host", BIND, "--port", PORT],
            cwd=str(REPO), env=env, stdout=fh, stderr=subprocess.STDOUT,
            creationflags=DETACHED)
    print(f"node starting pid={proc.pid} log={log}")
    # Importing the full HUD plus the nine-database substrate can exceed a
    # minute on a cold boot. Keep the deadline environment-shaped so a slow
    # disk does not look like a dead node and leave the watcher holding the
    # launch lock until the child is genuinely ready.
    poll_s = max(0.1, float(os.environ.get("NOUGEN_GRID_START_POLL_S", "2")))
    timeout_s = max(poll_s, float(os.environ.get("NOUGEN_GRID_START_TIMEOUT_S", "180")))
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(poll_s)
        status = port_up()
        if isinstance(status, int):
            break
    print(f"node health on :{PORT} -> {status}")
    if not isinstance(status, int):
        print("FATAL: node did not come up; see log")
        return 3
    return None


def _start_tunnel_if_needed():
    # Idempotence guard: a rerun (watchdog or hand-run) must not stack a second
    # connector. Probe live process state instead of assuming (one cloudflared
    # "tunnel run" is the healthy shape; the exe name resolves from the same
    # env-first path as the launch command).
    exe_name = Path(CLOUDFLARED).name
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {exe_name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=15).stdout
        already = exe_name.lower() in out.lower()
    except Exception as e:
        print(f"tunnel probe failed ({type(e).__name__}); assuming not running")
        already = False
    if already:
        print(f"tunnel already up ({exe_name} running); not starting a duplicate")
        return 0

    tun_token = peel("NOUGEN_TUNNEL_RUN_TOKEN")
    if not tun_token:
        print("FATAL: NOUGEN_TUNNEL_RUN_TOKEN not found")
        return 4
    tlog = SCRATCH / "cloudflared_tunnel.log"
    with open(tlog, "ab") as fh:
        proc = subprocess.Popen(
            [CLOUDFLARED, "tunnel", "run", "--token", tun_token],
            stdout=fh, stderr=subprocess.STDOUT, creationflags=DETACHED)
    print(f"cloudflared starting pid={proc.pid} log={tlog}")
    return 0


def _authenticated_probe():
    """Exercise the real MCP lane and leave a visible non-secret failure."""
    if os.environ.get("NOUGEN_GRID_AUTH_PROBE", "1").strip().lower() in {
        "0", "false", "off", "no"
    }:
        return
    probe = REPO / "tools" / "gateway_probe.py"
    if not probe.is_file():
        print(f"authenticated probe skipped: missing {probe}")
        return
    python_exe = REPO / ".venv" / "Scripts" / "python.exe"
    if not python_exe.is_file():
        python_exe = Path(sys.executable)
    timeout_s = max(5.0, float(os.environ.get("NOUGEN_GRID_PROBE_TIMEOUT_S", "45")))
    log = SCRATCH / "gateway_probe.log"
    rotate_log(log)
    try:
        with open(log, "ab") as fh:
            result = subprocess.run(
                [str(python_exe), str(probe)], cwd=str(REPO),
                env=dict(os.environ, NGS_REPO=str(REPO),
                         NOUGEN_PROBE_STATE_DIR=str(PROBE_STATE_DIR)),
                stdout=fh, stderr=subprocess.STDOUT,
                timeout=timeout_s, check=False)
        if result.returncode:
            print(f"authenticated probe FAILED (rc={result.returncode}); see {log}")
        else:
            print("authenticated probe OK")
    except subprocess.TimeoutExpired:
        alert = PROBE_STATE_DIR / "gateway_probe.alert"
        alert.write_text(f"probe timeout after {timeout_s}s\n", encoding="utf-8")
        print(f"authenticated probe TIMEOUT after {timeout_s}s; see {alert}")


def watch():
    """Supervisor loop: the 08/25 outage was the node dying silently and staying
    dead for 23h because nothing re-ran main(). main() is idempotent (node port
    probe + tunnel process probe), so re-running it is the whole watchdog."""
    # Self-dedupe: the Startup .cmd spawns a --watch at every logon while a
    # prior loop may still be running (observed 2026-08-27: python.exe loop
    # from 08/26 alive when the pythonw.exe Startup copy would join it). Two
    # loops are race-safe now (singleton lock) but pure waste. Same lock file,
    # different byte offset, so the watch-guard never fights the launch lock.
    guard = open(NODE_LOCK_PATH.with_suffix(".watch.lock"), "a+")
    try:
        guard.seek(0)
        msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("another --watch supervisor already holds the watch lock; exiting (not an error)")
        return 0
    interval = int(os.environ.get("NOUGEN_GRID_WATCH_SECS", 300))
    while True:
        try:
            main()
            _authenticated_probe()
        except Exception as e:
            print(f"watch pass failed ({type(e).__name__}: {e}); retrying next tick")
        time.sleep(interval)


if __name__ == "__main__":
    if "--watch" in sys.argv:
        raise SystemExit(watch())
    raise SystemExit(main())
