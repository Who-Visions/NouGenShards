"""Native agent surface: automations, boost, plans, compaction, search,
command policy, signed skill bundles, and a local console.

State lives under NOUGEN_SURFACE_HOME (default ~/.nougen/surface), so each
tenant owns its own jobs, plans, keys and receipts.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shlex
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from .gatekeeper import check_mutation_gate

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
RISK_RE = re.compile(r"\b(deploy|delete|drop|migrate|push|secret|credential|production)\b", re.I)
REVIEW_MODES = ("always", "auto", "skip")
OUTPUT_LIMIT = 64_000
CHUNK_CHARS = 12_000


class SurfaceError(RuntimeError):
    pass


def home() -> Path:
    raw = os.environ.get("NOUGEN_SURFACE_HOME", "").strip()
    path = Path(raw).expanduser() if raw else Path.home() / ".nougen" / "surface"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _name(value: str) -> str:
    if not NAME_RE.match(value):
        raise SurfaceError(f"invalid name: {value!r}")
    return value


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def _save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(home() / "runs.db", timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, job TEXT, kind TEXT, lane TEXT,"
        " started TEXT, finished TEXT, status TEXT, exit_code INTEGER, output TEXT)"
    )
    return conn


def _tools() -> Path:
    raw = os.environ.get("NOUGEN_TOOLS_DIR", "").strip()
    candidates = [Path(raw)] if raw else []
    candidates += [Path(__file__).resolve().parents[2] / "tools", Path.home() / "Outpost" / "NouGen" / "tools"]
    for candidate in candidates:
        if (candidate / "coach.py").is_file():
            return candidate
    raise SurfaceError("coach.py not found: set NOUGEN_TOOLS_DIR")


def _coach():
    tools = str(_tools())
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import coach

    return coach


# --- command policy ---------------------------------------------------------

def policy() -> dict:
    return _load(home() / "policy.json", {"allow": [], "review": "auto"})


def set_policy(data: dict) -> None:
    _save(home() / "policy.json", data)


def check_command(command: str) -> list[str]:
    """Return argv when policy allows it. Limits what a job may start, not what
    that program does afterwards: this is not an OS sandbox."""
    argv = shlex.split(command, posix=os.name != "nt")
    if not argv:
        raise SurfaceError("empty command")
    exe = Path(argv[0].strip('"')).stem.lower()
    if exe not in policy()["allow"]:
        raise SurfaceError(f"policy: {exe!r} is not allowed (nougen policy allow {exe})")
    gate = check_mutation_gate(command)
    if not gate.get("allowed", False):
        raise SurfaceError(f"gatekeeper: {gate.get('reason')}")
    return [part.strip('"') for part in argv]


# --- automations -------------------------------------------------------------

def _jobs_path() -> Path:
    return home() / "jobs.json"


def jobs() -> dict:
    return _load(_jobs_path(), {})


def add_job(name: str, command: str = "", prompt: str = "", lane: str = "local", at: str = "") -> dict:
    _name(name)
    if bool(command) == bool(prompt):
        raise SurfaceError("give exactly one of --command or --prompt")
    if lane not in ("local", "boost"):
        raise SurfaceError("lane must be local or boost")
    if at and not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", at):
        raise SurfaceError("--at must be HH:MM")
    data = jobs()
    data[name] = {"command": command, "prompt": prompt, "lane": lane, "at": at}
    _save(_jobs_path(), data)
    return data[name]


def _execute(job: dict) -> tuple[int, str]:
    if job.get("command"):
        argv = check_command(job["command"])
        done = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=3600, check=False)
        return done.returncode, (done.stdout + done.stderr)
    if job.get("lane") == "boost":
        return 0, boost(job["prompt"])["merged"]
    return 0, _coach().local(job["prompt"])


def run_job(name: str) -> dict:
    job = jobs().get(name)
    if job is None:
        raise SurfaceError(f"no such job: {name}")
    with _db() as conn:
        # A killed runner cannot close its own receipt; the job timeout bounds a live one.
        cutoff = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 7200))
        conn.execute("UPDATE runs SET status = 'abandoned' WHERE status = 'running' AND started < ?", (cutoff,))
        run_id = conn.execute(
            "INSERT INTO runs (job, kind, lane, started, status) VALUES (?, ?, ?, ?, 'running')",
            (name, "command" if job.get("command") else "prompt", job.get("lane"), _now()),
        ).lastrowid
    try:
        code, output = _execute(job)
        status = "ok" if code == 0 else "failed"
    except (SurfaceError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        code, output, status = 1, f"{type(exc).__name__}: {exc}", "failed"
    with _db() as conn:
        conn.execute(
            "UPDATE runs SET finished = ?, status = ?, exit_code = ?, output = ? WHERE id = ?",
            (_now(), status, code, output[-OUTPUT_LIMIT:], run_id),
        )
    return {"id": run_id, "job": name, "status": status, "exit_code": code}


def runs(limit: int = 20) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, job, kind, lane, started, finished, status, exit_code FROM runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def task_command(name: str) -> list[str]:
    """schtasks argv for a daily job; conhost --headless keeps it windowless."""
    job = jobs().get(name)
    if job is None or not job.get("at"):
        raise SurfaceError("job needs an --at time before install")
    python = Path(sys.executable)
    windowless = python.with_name("pythonw.exe")
    python = windowless if windowless.exists() else python
    action = f'conhost.exe --headless "{python}" -m nougen_shards.surface auto run {name}'
    return ["schtasks", "/Create", "/F", "/TN", f"NouGen\\Auto\\{name}", "/SC", "DAILY", "/ST", job["at"], "/TR", action]


def install_job(name: str, runner: Callable = subprocess.run) -> None:
    if os.name != "nt":
        raise SurfaceError(f"add to cron: {jobs().get(name, {}).get('at')} daily -> nougen auto run {name}")
    runner(task_command(name), check=True, capture_output=True)


# --- boost --------------------------------------------------------------------

def boost(prompt: str, lanes: int = 4, ask: Optional[Callable] = None, merge: Optional[Callable] = None) -> dict:
    """Answer on several models, cross-critique, then merge locally."""
    if ask is None or merge is None:
        coach = _coach()
        ask, merge = ask or coach.ask, merge or coach.local
    answers = [a for a in ask(prompt, lanes=lanes, why="boost answers") if a.get("text", "").strip()]
    if len({a.get("model") for a in answers}) < 2:
        raise SurfaceError("boost needs answers from at least two distinct models")
    joined = "\n\n".join(f"[{a['model']}]\n{a['text']}" for a in answers)
    critiques = ask(
        f"Question:\n{prompt}\n\nCandidate answers:\n{joined}\n\nList factual errors, gaps and conflicts only.",
        lanes=lanes, why="boost critique",
    )
    notes = "\n\n".join(f"[{c.get('model')}]\n{c.get('text', '')}" for c in critiques)
    merged = merge(
        f"Question:\n{prompt}\n\nAnswers:\n{joined}\n\nCritiques:\n{notes}\n\n"
        "Write the best final answer, then a section titled Disagreements listing every unresolved conflict."
    )
    receipt = {"prompt": prompt, "answers": answers, "critiques": critiques, "merged": merged, "at": _now()}
    _save(home() / "boost" / f"{time.time_ns()}.json", receipt)
    return receipt


# --- plans --------------------------------------------------------------------

def _plan_path(plan_id: str) -> Path:
    return home() / "plans" / f"{_name(plan_id)}.json"


def new_plan(goal: str, body: str = "", draft: Optional[Callable] = None) -> dict:
    text = body or (draft or _coach().local)(f"Write a short numbered implementation plan for: {goal}")
    plan_id = f"p{time.strftime('%Y%m%d%H%M%S', time.gmtime())}-{secrets.token_hex(2)}"
    plan = {"id": plan_id, "goal": goal, "body": text, "status": "draft", "created": _now()}
    _save(_plan_path(plan_id), plan)
    return plan


def get_plan(plan_id: str) -> dict:
    plan = _load(_plan_path(plan_id), None)
    if plan is None:
        raise SurfaceError(f"no such plan: {plan_id}")
    return plan


def _plan_digest(plan: dict) -> str:
    """Digest of everything approval covers: the goal and the body."""
    payload = json.dumps({"goal": plan.get("goal", ""), "body": plan.get("body", "")}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def approve_plan(plan_id: str) -> dict:
    plan = get_plan(plan_id)
    plan["status"] = "approved"
    plan["digest"] = _plan_digest(plan)
    _save(_plan_path(plan_id), plan)
    return plan


def plan_gate(plan_id: str) -> tuple[bool, str]:
    plan = get_plan(plan_id)
    mode = policy().get("review", "auto")
    if mode == "skip":
        return True, "review skipped by policy"
    if mode == "auto" and not RISK_RE.search(plan["goal"] + " " + plan["body"]):
        return True, "low risk"
    digest = _plan_digest(plan)
    if plan["status"] == "approved" and hmac.compare_digest(plan.get("digest", ""), digest):
        return True, "approved"
    return False, "needs approval"


# --- compaction ---------------------------------------------------------------

def compact(name: str, text: str, summarize: Optional[Callable] = None, store: Optional[Callable] = None) -> dict:
    """Summarize on the local lane, then keep the result as a shard."""
    _name(name)
    summarize = summarize or _coach().local
    chunks = [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)] or [""]
    parts = [summarize("Compress this session. Keep decisions, facts, paths and open work:\n\n" + c) for c in chunks]
    summary = parts[0] if len(parts) == 1 else summarize("Merge these session notes:\n\n" + "\n\n".join(parts))
    if not summary.strip():
        raise SurfaceError("local lane returned an empty summary; nothing stored")
    if store is None:
        from .core import capture as store
    store("session_compact", f"Compacted session {name}", summary, domain_key=f"session-compact:{name}")
    return {"name": name, "chars_in": len(text), "chars_out": len(summary), "summary": summary}


def restore(name: str, lookup: Optional[Callable] = None) -> list:
    _name(name)
    if lookup is None:
        from .core import retrieve as lookup
    return lookup(name, limit=1, domain_key=f"session-compact:{name}")


# --- search -------------------------------------------------------------------

def find(query: str, limit: int = 10, shard_search: Optional[Callable] = None) -> list[dict]:
    """Search shards, plans, run receipts and local relay legs."""
    needle = query.lower()
    hits: list[dict] = []
    try:
        if shard_search is None:
            from .core import retrieve as shard_search
        for row in shard_search(query, limit=limit):
            item = row if isinstance(row, dict) else {"title": str(row)}
            hits.append({"source": "shard", "title": str(item.get("title", ""))[:120]})
    except (ImportError, OSError, RuntimeError, sqlite3.Error) as exc:
        hits.append({"source": "shard", "title": f"unavailable: {type(exc).__name__}"})
    for path in (home() / "plans").glob("*.json"):
        plan = _load(path, {})
        if needle in (plan.get("goal", "") + plan.get("body", "")).lower():
            hits.append({"source": "plan", "title": f"{plan['id']} {plan['goal']}"})
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, job FROM runs WHERE instr(lower(output), ?) > 0 ORDER BY id DESC LIMIT ?", (needle, limit)
        ).fetchall()
    hits += [{"source": "run", "title": f"#{row['id']} {row['job']}"} for row in rows]
    legs = Path(os.environ.get("NOUGEN_HANDOFFS_DIR", str(Path.home() / "Outpost/NouGenRelay/.handoffs")))
    for path in sorted(legs.glob("*.json"), reverse=True)[:500]:
        goal = str(_load(path, {}).get("goal", ""))
        if needle in goal.lower():
            hits.append({"source": "relay", "title": f"{path.stem} {goal}"})
    return hits[:limit * 4]


# --- signed skill bundles -----------------------------------------------------

def _trust_path() -> Path:
    return home() / "market" / "trusted.json"


def _write_private(path: Path, data: bytes) -> None:
    """Create a credential file readable by its owner only (0600, directory 0700).

    The file is opened with O_EXCL and mode 0600, so no umask-wide copy ever exists on disk.
    Windows ignores POSIX modes; there the user profile ACL already keeps other accounts out.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def publisher_key() -> str:
    """Create this tenant's signing key on first use; return its public half."""
    path = home() / "market" / "publisher.key"
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    else:
        key = Ed25519PrivateKey.generate()
        _write_private(path, key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ))
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def trust(public: str) -> None:
    Ed25519PublicKey.from_public_bytes(base64.b64decode(public, validate=True))
    keys = _load(_trust_path(), [])
    if public not in keys:
        _save(_trust_path(), keys + [public])


def pack(source: Path, output: Path) -> Path:
    """Bundle a skill directory holding SKILL.md, signed by this tenant."""
    source = Path(source)
    if not (source / "SKILL.md").is_file():
        raise SurfaceError("skill directory has no SKILL.md")
    public = publisher_key()
    key = serialization.load_pem_private_key((home() / "market" / "publisher.key").read_bytes(), password=None)
    files = sorted(p for p in source.rglob("*") if p.is_file() and not p.is_symlink())
    digests = {p.relative_to(source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    manifest = json.dumps({"name": _name(source.name), "files": digests}, sort_keys=True).encode("utf-8")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", manifest)
        bundle.writestr("signature.json", json.dumps({
            "publisher": public, "signature": base64.b64encode(key.sign(manifest)).decode("ascii"),
        }))
        for path in files:
            bundle.write(path, "payload/" + path.relative_to(source).as_posix())
    return Path(output)


def install(bundle_path: Path, skills_dir: Path) -> Path:
    """Verify publisher, signature and every digest before anything is written."""
    with zipfile.ZipFile(bundle_path) as bundle:
        manifest_raw = bundle.read("manifest.json")
        signed = json.loads(bundle.read("signature.json"))
        if signed["publisher"] not in _load(_trust_path(), []):
            raise SurfaceError("publisher is not trusted")
        public = Ed25519PublicKey.from_public_bytes(base64.b64decode(signed["publisher"]))
        try:
            public.verify(base64.b64decode(signed["signature"]), manifest_raw)
        except InvalidSignature as exc:
            raise SurfaceError("bad signature") from exc
        manifest = json.loads(manifest_raw)
        name = _name(manifest["name"])
        payload = {n[len("payload/"):] for n in bundle.namelist() if n.startswith("payload/")}
        if payload != set(manifest["files"]):
            raise SurfaceError("bundle contents do not match manifest")
        contents = {}
        for rel, digest in manifest["files"].items():
            parts = Path(rel).parts
            if Path(rel).is_absolute() or ".." in parts or ":" in rel or "\\" in rel:
                raise SurfaceError(f"unsafe path: {rel}")
            data = bundle.read("payload/" + rel)
            if hashlib.sha256(data).hexdigest() != digest:
                raise SurfaceError(f"digest mismatch: {rel}")
            contents[rel] = data
    target = Path(skills_dir) / name
    staging = Path(skills_dir) / f".{name}.installing"
    shutil.rmtree(staging, ignore_errors=True)
    for rel, data in contents.items():
        path = staging / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    shutil.rmtree(target, ignore_errors=True)
    os.replace(staging, target)
    return target


# --- console ------------------------------------------------------------------

PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>NouGen Console</title>
<style>:root{color-scheme:light dark}body{font:15px system-ui;max-width:900px;margin:0 auto;padding:16px}
table{border-collapse:collapse;width:100%}td,th{padding:6px;text-align:left;border-bottom:1px solid #8884}
iframe{width:100%;height:320px;border:1px solid #8884}input,textarea{width:100%;box-sizing:border-box;margin:4px 0}</style>
<h1>NouGen Console</h1><input id=t type=password placeholder="Console token" aria-label="Console token">
<button id=l>Load</button><h2>Lanes</h2><div id=lanes></div><h2>Runs</h2><table id=r></table>
<h2>Message a lane</h2><input id=to placeholder=Target aria-label=Target><textarea id=m aria-label=Message></textarea>
<button id=s>Send</button><p id=o role=status></p><h2>Generated view</h2>
<textarea id=h aria-label="Generated HTML"></textarea><button id=v>Render</button>
<iframe id=f sandbox title="Generated view"></iframe>
<script>
const $=i=>document.getElementById(i),H=()=>({Authorization:'Bearer '+$('t').value,'Content-Type':'application/json'});
async function load(){const r=await fetch('api/state',{headers:H()});if(!r.ok){$('o').textContent='Unauthorized';return}
const d=await r.json();$('lanes').textContent=d.claims.join(', ')||'No local claims';$('r').replaceChildren(...d.runs.map(x=>{
const w=document.createElement('tr');for(const k of ['id','job','status','started']){const c=document.createElement('td');
c.textContent=x[k];w.append(c)}return w}))}
$('l').onclick=load;$('v').onclick=()=>{$('f').srcdoc=$('h').value};
$('s').onclick=async()=>{const r=await fetch('api/message',{method:'POST',headers:H(),
body:JSON.stringify({target:$('to').value,text:$('m').value})});$('o').textContent=r.ok?'Sent':'Send failed'};
</script>"""


def console_token() -> str:
    path = home() / "console.token"
    if not path.exists():
        _write_private(path, secrets.token_urlsafe(32).encode("ascii"))
    return path.read_text(encoding="ascii").strip()


def console_state() -> dict:
    claims = Path(os.environ.get("NOUGEN_HANDOFFS_DIR", str(Path.home() / "Outpost/NouGenRelay/.handoffs"))) / "claims"
    return {"runs": runs(), "claims": sorted(p.stem for p in claims.glob("*.json"))[:50]}


def send_message(target: str, text: str) -> None:
    from .nougenmsg import NouGenMsgBus

    NouGenMsgBus.emit_node(socket.gethostname().lower(), target, text)


def console_handler(token: str, allowed_hosts: set[str], sender: Callable = send_message):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code: int, body: bytes, kind: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; "
                "frame-src 'self' about: srcdoc:",
            )
            self.end_headers()
            self.wfile.write(body)

        def _allowed(self) -> bool:
            host = self.headers.get("Host", "").rsplit(":", 1)[0].lower()
            if host not in allowed_hosts:
                self._send(403, b'{"error":"host"}')
                return False
            sent = self.headers.get("Authorization", "")
            if self.path.startswith("/api/") and not hmac.compare_digest(sent, f"Bearer {token}"):
                self._send(401, b'{"error":"token"}')
                return False
            return True

        def do_GET(self):
            if not self._allowed():
                return
            if self.path == "/":
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._send(200, json.dumps(console_state()).encode("utf-8"))
            else:
                self._send(404, b'{"error":"not found"}')

        def do_POST(self):
            if not self._allowed():
                return
            if self.path != "/api/message":
                self._send(404, b'{"error":"not found"}')
                return
            try:
                length = min(int(self.headers.get("Content-Length", "0")), 65_536)
                data = json.loads(self.rfile.read(length))
                target, text = str(data["target"]).strip(), str(data["text"]).strip()
                if not target or not text:
                    raise ValueError("empty")
                sender(target, text)
            except (ValueError, KeyError, TypeError):
                self._send(400, b'{"error":"bad request"}')
            except (OSError, RuntimeError):
                self._send(502, b'{"error":"send failed"}')
            else:
                self._send(200, b'{"ok":true}')

    return Handler


def serve_console(port: int, public_host: str = "") -> None:
    hosts = {"127.0.0.1", "localhost"} | ({public_host.lower()} if public_host else set())
    server = ThreadingHTTPServer(("127.0.0.1", port), console_handler(console_token(), hosts))
    print(f"http://127.0.0.1:{port}/  token file: {home() / 'console.token'}")
    server.serve_forever()


# --- CLI ----------------------------------------------------------------------

COMMANDS = {"auto", "boost", "plan", "compact", "find", "policy", "market", "console"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nougen")
    sub = parser.add_subparsers(dest="cmd", required=True)
    auto = sub.add_parser("auto", help="Scheduled jobs with receipts").add_subparsers(dest="action", required=True)
    add = auto.add_parser("add")
    add.add_argument("name")
    add.add_argument("--command", default="")
    add.add_argument("--prompt", default="")
    add.add_argument("--lane", default="local")
    add.add_argument("--at", default="")
    auto.add_parser("list")
    auto.add_parser("runs")
    for action in ("run", "install"):
        auto.add_parser(action).add_argument("name")
    boosted = sub.add_parser("boost", help="Multi-model answer with critique")
    boosted.add_argument("prompt")
    boosted.add_argument("--lanes", type=int, default=4)
    plan = sub.add_parser("plan", help="Reviewable plans").add_subparsers(dest="action", required=True)
    created = plan.add_parser("new")
    created.add_argument("goal")
    created.add_argument("--body", default="")
    for action in ("show", "approve", "gate"):
        plan.add_parser(action).add_argument("id")
    compacted = sub.add_parser("compact", help="Compress a session into a shard")
    compacted.add_argument("name")
    compacted.add_argument("--file")
    compacted.add_argument("--restore", action="store_true")
    found = sub.add_parser("find", help="Search shards, plans, runs and relay")
    found.add_argument("query")
    found.add_argument("--limit", type=int, default=10)
    rules = sub.add_parser("policy", help="Command allowlist and plan review").add_subparsers(dest="action", required=True)
    rules.add_parser("show")
    rules.add_parser("allow").add_argument("exe")
    rules.add_parser("deny").add_argument("exe")
    rules.add_parser("review").add_argument("mode", choices=REVIEW_MODES)
    market = sub.add_parser("market", help="Signed skill bundles").add_subparsers(dest="action", required=True)
    market.add_parser("key")
    market.add_parser("trust").add_argument("public")
    packed = market.add_parser("pack")
    packed.add_argument("source")
    packed.add_argument("output")
    installed = market.add_parser("install")
    installed.add_argument("bundle")
    installed.add_argument("--skills-dir", required=True)
    served = sub.add_parser("console", help="Local web console")
    served.add_argument("--port", type=int, default=4477)
    served.add_argument("--public-host", default="")
    return parser


def _run(args: argparse.Namespace) -> Any:
    if args.cmd == "auto":
        if args.action == "add":
            return add_job(args.name, args.command, args.prompt, args.lane, args.at)
        if args.action == "run":
            return run_job(args.name)
        if args.action == "install":
            install_job(args.name)
            return {"installed": args.name}
        return jobs() if args.action == "list" else runs()
    if args.cmd == "boost":
        return boost(args.prompt, args.lanes)["merged"]
    if args.cmd == "plan":
        if args.action == "new":
            return new_plan(args.goal, args.body)
        if args.action == "approve":
            return approve_plan(args.id)
        if args.action == "gate":
            allowed, reason = plan_gate(args.id)
            if not allowed:
                raise SurfaceError(reason)
            return reason
        return get_plan(args.id)
    if args.cmd == "compact":
        if args.restore:
            return restore(args.name)
        text = Path(args.file).read_text(encoding="utf-8", errors="replace") if args.file else sys.stdin.read()
        return compact(args.name, text)
    if args.cmd == "find":
        return find(args.query, args.limit)
    if args.cmd == "policy":
        data = policy()
        if args.action == "allow":
            data["allow"] = sorted(set(data["allow"]) | {args.exe.lower()})
        elif args.action == "deny":
            data["allow"] = [exe for exe in data["allow"] if exe != args.exe.lower()]
        elif args.action == "review":
            data["review"] = args.mode
        if args.action != "show":
            set_policy(data)
        return data
    if args.cmd == "market":
        if args.action == "key":
            return publisher_key()
        if args.action == "trust":
            trust(args.public)
            return "trusted"
        if args.action == "pack":
            return str(pack(Path(args.source), Path(args.output)))
        return str(install(Path(args.bundle), Path(args.skills_dir)))
    return serve_console(args.port, args.public_host)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _run(args)
    except SurfaceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if result is not None:
        print(result if isinstance(result, str) else json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
