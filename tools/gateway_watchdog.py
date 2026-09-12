"""
Autonomous Self-Healing and Self-Fixing Gateway Watchdog.
Runs on each machine (Hyperion, Blade, Phoebus) via hourly cron / Task Scheduler.
Checks local Uvicorn gateway (:4444) and Cloudflare tunnel.
If degraded or unresponsive, triggers self-healing, invokes local Ollama model to log diagnosis,
and restarts the local node cleanly without service flapping.
"""
from __future__ import annotations

import json
import logging
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Paths & Environment
HOST_NODE = platform.node().lower()
IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"

if "proart" in HOST_NODE or "whoart" in HOST_NODE:
    NODE_NAME = "whoart"
elif IS_MAC or "phoebus" in HOST_NODE or "mac" in HOST_NODE:
    NODE_NAME = "phoebus"
else:
    NODE_NAME = "blade"

LOG_DIR = Path(os.path.expanduser("~")) / ".nougen" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "gateway_watchdog.log"

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
logging.getLogger("").addHandler(console)

OLLAMA_URL = "http://127.0.0.1:11434"
GATEWAY_PORT = int(os.environ.get("NGS_PORT", "4444"))
LOCAL_HEALTH_URL = f"http://127.0.0.1:{GATEWAY_PORT}/health"

PUBLIC_ENDPOINTS = {
    "whoart": "https://whoart-vault.nougenai.com/health",
    "blade": "https://blade.nougenai.com/health",
    "phoebus": "https://phoebus.nougenai.com/health",
}

PREFERRED_MODELS = {
    "whoart": ["gemma4:e2b-qat", "Yukiai:e2b", "gemma2:2b"],
    "blade": ["dav1d:e2b", "gemma2:2b", "gemma4:e2b", "sol-ai:e4b", "solai:latest"],
    "phoebus": ["gemma4:e2b", "kaedracode:e2b", "kaedracode:latest"],
}


def check_port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2.0)
        return s.connect_ex(("127.0.0.1", port)) == 0


def check_http_endpoint(url: str, timeout: float = 6.0) -> tuple[bool, int | None, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "NouGenGatewayWatchdog/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status == 200, resp.status, body
    except urllib.error.HTTPError as e:
        return False, e.code, str(e)
    except Exception as e:
        return False, None, f"{type(e).__name__}: {e}"


def get_available_ollama_model() -> str | None:
    req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode())
            installed = {m["name"] for m in data.get("models", [])}
            # Try preferences for this node
            for cand in PREFERRED_MODELS.get(NODE_NAME, []):
                if cand in installed:
                    return cand
            # Fallback to any installed
            if installed:
                return next(iter(installed))
    except Exception as e:
        logging.warning("Ollama tags probe failed: %s", e)
    return None


def ollama_diagnose(context_msg: str) -> str:
    model = get_available_ollama_model()
    if not model:
        return "Ollama unavailable; manual rule applied."
    prompt = (
        f"You are the NouGen fleet reliability assistant for node '{NODE_NAME}'.\n"
        f"Issue: {context_msg}\n"
        f"Generate a concise 1-sentence root-cause diagnosis and remediation statement in ASCII."
    )
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=json.dumps({"model": model, "prompt": prompt, "stream": False}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            data = json.loads(resp.read().decode())
            ans = data.get("response", "").strip()
            # Strip thought channel if present
            if "<channel|>" in ans:
                ans = ans.split("<channel|>")[-1].strip()
            return ans.encode("ascii", "ignore").decode().strip() or "Healed successfully."
    except Exception as e:
        return f"Ollama diagnosis timeout/error ({e}); default heuristic executed."


def heal_local_gateway():
    logging.info("[HEAL] Initiating gateway self-healing on node: %s", NODE_NAME)
    if IS_WINDOWS:
        # 1. Kill stale listener on port 4444 gracefully
        try:
            cmd = f'powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort {GATEWAY_PORT} -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            pids = [int(p.strip()) for p in res.stdout.split() if p.strip().isdigit()]
            for pid in pids:
                logging.info("[HEAL] Terminating listener PID %d on port %d", pid, GATEWAY_PORT)
                subprocess.run(f"taskkill /PID {pid} /F", shell=True, capture_output=True)
        except Exception as e:
            logging.warning("[HEAL] Error cleaning listener: %s", e)

        time.sleep(2)

        repo_dir = Path(os.environ.get("USERPROFILE", "C:\\Users\\super")) / "Outpost" / "NouGen"
        if not repo_dir.exists():
            repo_dir = Path(os.environ.get("USERPROFILE", "C:\\Users\\super")) / "Watchtower" / "NouGen" / "NouGenShards-push-main"

        venv_py = repo_dir / ".venv" / "Scripts" / "python.exe"
        py = str(venv_py) if venv_py.exists() else sys.executable

        # 2. Start node: trigger scheduled task NouGenNode (SYSTEM) or fallback to batch / Popen
        schtasks_check = subprocess.run("schtasks /query /tn NouGenNode", shell=True, capture_output=True)
        if schtasks_check.returncode == 0:
            logging.info("[HEAL] Triggering SYSTEM scheduled task NouGenNode")
            subprocess.run("schtasks /run /tn NouGenNode", shell=True, capture_output=True)
        else:
            logging.info("[HEAL] Spawning uvicorn process with %s in %s", py, repo_dir)
            env = os.environ.copy()
            env["PYTHONPATH"] = str(repo_dir / "src") + os.pathsep + env.get("PYTHONPATH", "")
            # CREATE_NEW_PROCESS_GROUP = 0x00000200, DETACHED_PROCESS = 0x00000008
            DETACHED = 0x00000008 | 0x00000200
            cmd = [py, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(GATEWAY_PORT)]
            subprocess.Popen(
                cmd,
                cwd=str(repo_dir),
                env=env,
                creationflags=DETACHED,
                close_fds=True,
            )

    elif IS_MAC:
        # Phoebus self-healing
        try:
            res = subprocess.run(f"lsof -ti:{GATEWAY_PORT}", shell=True, capture_output=True, text=True)
            pids = [int(p.strip()) for p in res.stdout.split() if p.strip().isdigit()]
            for pid in pids:
                logging.info("[HEAL] Killing stale PID %d on port %d", pid, GATEWAY_PORT)
                subprocess.run(f"kill -9 {pid}", shell=True)
        except Exception as e:
            logging.warning("[HEAL] Mac cleanup error: %s", e)

        time.sleep(2)
        repo_dir = Path(os.path.expanduser("~")) / ".nougen" / "src" / "nougenshards"
        py = "/usr/bin/python3"
        logging.info("[HEAL] Launching uvicorn in background on Mac")
        cmd = f"cd {repo_dir} && nohup {py} -m uvicorn app:app --host 127.0.0.1 --port {GATEWAY_PORT} >/dev/null 2>&1 &"
        subprocess.run(cmd, shell=True)

    # Wait and verify (poll every 5s up to 150s to accommodate StreamableHTTP and warmups)
    logging.info("[HEAL] Polling for server readiness on 127.0.0.1:%d...", GATEWAY_PORT)
    for attempt in range(1, 31):
        time.sleep(5)
        ok, status, _ = check_http_endpoint(LOCAL_HEALTH_URL, timeout=4.0)
        if ok:
            logging.info("[HEAL SUCCESS] Node is healthy on 127.0.0.1:%d (HTTP %d, poll attempt %d)", GATEWAY_PORT, status, attempt)
            return
    logging.error("[HEAL TIMEOUT] Node did not respond with 200 within 150s on 127.0.0.1:%d", GATEWAY_PORT)


def run_watchdog():
    logging.info("=== STARTING GATEWAY WATCHDOG CHECK: NODE=%s ===", NODE_NAME)
    is_listening = check_port_listening(GATEWAY_PORT)
    local_ok, local_status, local_resp = check_http_endpoint(LOCAL_HEALTH_URL, timeout=5.0)

    public_url = PUBLIC_ENDPOINTS.get(NODE_NAME)
    public_ok, public_status, public_resp = check_http_endpoint(public_url, timeout=8.0) if public_url else (True, 200, "N/A")

    logging.info(
        "Probe results: port_%d_listening=%s local_health=%s (status=%s) public_health=%s (status=%s)",
        GATEWAY_PORT, is_listening, local_ok, local_status, public_ok, public_status
    )

    if local_ok and public_ok:
        logging.info("[GREEN] All gateway surfaces healthy. No action needed.")
        return 0

    # Degraded or unhealthy: trigger Ollama diagnosis + self-healing
    issue = f"local_listening={is_listening}, local_health={local_status}, public_gateway={public_status}"
    logging.warning("[DEGRADED] Gateway check failed: %s", issue)
    
    diagnosis = ollama_diagnose(issue)
    logging.info("[OLLAMA DIAGNOSIS] %s", diagnosis)

    heal_local_gateway()

    # Re-verify
    re_ok, re_status, _ = check_http_endpoint(LOCAL_HEALTH_URL, timeout=8.0)
    re_pub_ok, re_pub_status, _ = check_http_endpoint(public_url, timeout=10.0) if public_url else (True, 200, "")

    logging.info(
        "[POST-HEAL STATUS] local_health=%s (%s), public_health=%s (%s)",
        re_ok, re_status, re_pub_ok, re_pub_status
    )
    return 0 if (re_ok and re_pub_ok) else 1


if __name__ == "__main__":
    sys.exit(run_watchdog())
