"""NouGen mesh: one runtime config and one tool registry for every NouGen repo.

Each repo in the tester package runs alone, and any repo can call any other
repo's tools when both are installed. This file is how they find each other.

Stdlib only, Python 3.10+. It is vendored byte for byte into each repo of the
package as ``nougen_mesh.py`` so no repo needs another one installed to know
who it is. ``python -m nougen_shards.mesh check-vendored <file>`` compares a
copy against this one.

Nothing here names an operator, a machine, a host or a lane. Every value
resolves at runtime, in this order:

1. an environment variable,
2. the mesh file (``NOUGEN_MESH_FILE`` or ``<home>/mesh.json``),
3. the older local files a fleet box already has (``fleet_hosts.json``,
   ``nodes.json``, ``endpoints.json`` under ``<home>``), so an existing node
   keeps its identity without a migration,
4. what the box itself says (git config, hostname),
5. ``standalone`` / ``None``: a fresh clone routes only to itself.

``<home>`` is the runtime home: ``NOUGEN_ROOT``, else ``~/.nougen``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

MESH_VERSION = "1"
MANIFEST_FILE = "nougen.tools.json"
MANIFEST_SCHEMA = "nougen-tools/1"
CONFIG_SCHEMA = "nougen-mesh/1"

#: The ten repos of the tester package: short name -> GitHub repo name.
#: Short names are what tools are addressed by ("open.ask"). Owners are not
#: listed: clone URLs come from the mesh file or the tester's own remote.
REPOS: Dict[str, str] = {
    "shards": "NouGenShards",
    "relay": "NouGenRelay",
    "msg": "NouGenMsg",
    "code": "NouGenCode",
    "design": "nougendesign",
    "tracker": "NouGenTracker",
    "open": "NouGenOpen",
    "fleet-mcp": "nougen-fleet-mcp",
    "claude": "NouGenClaude",
    "portable": "NouGenPortable",
}

#: Loopback ports each local service listens on unless the mesh file or
#: NOUGEN_<SERVICE>_PORT says otherwise. Open's MCP server gets its own port so
#: it no longer collides with ``nougen-open serve``.
DEFAULT_PORTS: Dict[str, int] = {
    "shards": 4444,
    "open": 8765,
    "msg": 8766,
    "open-mcp": 8767,
    "ollama": 11434,
}

_LANE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_NODE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


# ---------------------------------------------------------------- home + file
def home() -> Path:
    """Runtime home: $NOUGEN_ROOT, else ~/.nougen."""
    raw = os.environ.get("NOUGEN_ROOT", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".nougen"


def config_path() -> Path:
    raw = os.environ.get("NOUGEN_MESH_FILE", "").strip()
    return Path(raw).expanduser() if raw else home() / "mesh.json"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load() -> Dict[str, Any]:
    """The mesh file as a dict; {} when absent or unreadable."""
    data = _read_json(config_path())
    return data if isinstance(data, dict) else {}


def _section(name: str) -> Dict[str, Any]:
    value = load().get(name)
    return value if isinstance(value, dict) else {}


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _slug(value: str, pattern: re.Pattern = _NODE_RE) -> str:
    s = re.sub(r"[^a-z0-9_-]+", "-", value.strip().lower()).strip("-_")
    if pattern is _LANE_RE:
        s = re.sub(r"^[^a-z]+", "", s)
    return s[:32]


# ---------------------------------------------------------------- identity
def _git_config(key: str) -> str:
    git = shutil.which("git")
    if not git:
        return ""
    try:
        out = subprocess.run([git, "config", "--get", key], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def _hostname() -> str:
    return (os.environ.get("COMPUTERNAME") if os.name == "nt" else "") or socket.gethostname() or ""


def _legacy_fleet_nodes() -> Dict[str, List[str]]:
    """{node: host_patterns} from an existing box's fleet_hosts.json."""
    raw = _env("NOUGEN_FLEET_HOSTS_FILE")
    data = _read_json(Path(raw).expanduser() if raw else home() / "fleet_hosts.json")
    nodes = data.get("nodes") if isinstance(data, dict) else None
    out: Dict[str, List[str]] = {}
    for node, cfg in nodes.items() if isinstance(nodes, dict) else ():
        name = str(node).strip().lower()
        pats = cfg.get("host_patterns") if isinstance(cfg, dict) else None
        if name:
            out[name] = [str(p).strip().lower() for p in (pats or [name]) if str(p).strip()]
    return out


def nodes() -> Dict[str, Dict[str, Any]]:
    """Every node this box knows about: mesh file first, then fleet_hosts.json.

    A fresh clone knows none, so it only ever routes to itself.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for name, pats in _legacy_fleet_nodes().items():
        out[name] = {"host_patterns": pats}
    for name, cfg in _section("nodes").items():
        key = str(name).strip().lower()
        if key:
            out[key] = dict(cfg) if isinstance(cfg, dict) else {}
    return out


def node() -> str:
    """This box's node name, or "standalone"."""
    for var in ("NOUGEN_FLEET_NODE", "NOUGEN_NODE_NAME"):
        v = _env(var).lower()
        if v:
            return _slug(v) or "standalone"
    v = str(_section("identity").get("node") or "").strip().lower()
    if v:
        return _slug(v) or "standalone"
    host = _hostname().lower()
    for name, cfg in nodes().items():
        pats = cfg.get("host_patterns") or [name]
        if host and any(str(p).lower() in host for p in pats):
            return name
    return "standalone"


def machine() -> str:
    v = _env("NOUGEN_MACHINE") or str(_section("identity").get("machine") or "") or _git_config("nougen.machine")
    return _slug(v or _hostname()) or "unknown-machine"


def agent() -> str:
    v = _env("NOUGEN_AGENT") or str(_section("identity").get("agent") or "") or _git_config("nougen.agent")
    return v.strip() or "unknown-agent"


def tenant() -> Optional[str]:
    v = _env("NOUGEN_TENANT") or str(_section("identity").get("tenant") or "")
    return v.strip() or None


def identity() -> Dict[str, Any]:
    return {"machine": machine(), "agent": agent(), "node": node(), "tenant": tenant()}


def self_address(lane: Optional[str] = None) -> str:
    """This box as a NouGenMsg wire v2 address: ``lane[@node]``."""
    ln = _slug(lane or agent(), _LANE_RE) or "agent"
    nd = node()
    return ln if nd == "standalone" else f"{ln}@{nd}"


# ---------------------------------------------------------------- endpoints
def port(service: str) -> Optional[int]:
    env = _env(f"NOUGEN_{service.upper().replace('-', '_')}_PORT")
    if env.isdigit():
        return int(env)
    v = _section("ports").get(service)
    if isinstance(v, int) or (isinstance(v, str) and v.isdigit()):
        return int(v)
    return DEFAULT_PORTS.get(service)


def ingress() -> Optional[str]:
    """The front door other nodes are reached through, or None (local only)."""
    v = _env("NOUGEN_INGRESS_URL") or str(load().get("ingress") or "")
    if not v:
        legacy = _read_json(Path(_env("NOUGEN_ENDPOINTS_FILE")).expanduser() if _env("NOUGEN_ENDPOINTS_FILE")
                            else home() / "endpoints.json")
        if isinstance(legacy, dict):
            v = str(legacy.get("fleet_gateway_url") or "")
    return v.strip().rstrip("/") or None


def endpoint(service: str, at: Optional[str] = None) -> Optional[str]:
    """Base URL for ``service`` on node ``at`` (default: this box).

    Local: NOUGEN_<SERVICE>_URL, then mesh ``endpoints``, then loopback on the
    service's port. Another node: that node's ``endpoints`` entry in the mesh
    file, then ``<ingress>/<node>/<service>``, then None.
    """
    key = service.upper().replace("-", "_")
    here = node()
    if at in (None, "", here):
        v = _env(f"NOUGEN_{key}_URL") or str(_section("endpoints").get(service) or "")
        if v:
            return v.rstrip("/")
        p = port(service)
        return f"http://127.0.0.1:{p}" if p else None
    target = str(at).strip().lower()
    cfg = nodes().get(target, {})
    eps = cfg.get("endpoints") if isinstance(cfg, dict) else None
    if isinstance(eps, dict) and eps.get(service):
        return str(eps[service]).rstrip("/")
    door = ingress()
    return f"{door}/{target}/{service}" if door else None


# ---------------------------------------------------------------- repos
def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def repo_dir(name: str, near: Optional[str] = None) -> Optional[Path]:
    """Where repo ``name`` is checked out on this box, or None.

    NOUGEN_<NAME>_DIR, then mesh ``repos``, then a sibling of ``near`` (a file
    or dir inside the calling repo), then a sibling of $NOUGEN_REPOS_DIR.
    """
    if name not in REPOS:
        return None
    env = _env(f"NOUGEN_{name.upper().replace('-', '_')}_DIR")
    if env and Path(env).expanduser().is_dir():
        return Path(env).expanduser()
    v = _section("repos").get(name)
    if isinstance(v, dict):
        v = v.get("path")
    if v and Path(str(v)).expanduser().is_dir():
        return Path(str(v)).expanduser()
    want = _norm(REPOS[name])
    roots: List[Path] = []
    if near:
        p = Path(near).resolve()
        top = _repo_top(p)
        if top is not None:
            if _norm(top.name) == want:
                return top
            roots.append(top.parent)
    if _env("NOUGEN_REPOS_DIR"):
        roots.append(Path(_env("NOUGEN_REPOS_DIR")).expanduser())
    for root in roots:
        try:
            for child in root.iterdir():
                if child.is_dir() and _norm(child.name) == want:
                    return child
        except OSError:
            continue
    return None


def _repo_top(p: Path) -> Optional[Path]:
    for cand in [p, *p.parents] if p.is_dir() else list(p.parents):
        if (cand / ".git").exists() or (cand / MANIFEST_FILE).exists():
            return cand
    return None


def installed(near: Optional[str] = None) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    for name in REPOS:
        d = repo_dir(name, near)
        if d is not None:
            out[name] = d
    return out


# ---------------------------------------------------------------- tools
def manifest(repo: Path) -> Dict[str, Any]:
    data = _read_json(Path(repo) / MANIFEST_FILE)
    return data if isinstance(data, dict) and data.get("schema") == MANIFEST_SCHEMA else {}


def tools(near: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Every tool of every installed repo, keyed ``repo.tool``."""
    out: Dict[str, Dict[str, Any]] = {}
    for name, d in installed(near).items():
        m = manifest(d)
        for t in m.get("tools") or []:
            if isinstance(t, dict) and t.get("name"):
                out[f"{name}.{t['name']}"] = {**t, "repo": name, "repo_dir": str(d), "service": m.get("service")}
    return out


class MeshError(RuntimeError):
    pass


def call(qualified: str, args: Optional[Dict[str, Any]] = None, *, near: Optional[str] = None,
         at: Optional[str] = None, timeout: float = 120.0) -> Any:
    """Run tool ``repo.tool`` with ``args`` and return its JSON result.

    A repo installed on this box is called locally (python or cli transport).
    Otherwise, or when ``at`` names another node, an http tool goes to that
    repo's service endpoint.
    """
    args = dict(args or {})
    reg = tools(near)
    spec = reg.get(qualified)
    repo = qualified.split(".", 1)[0]
    if spec is None or at:
        if spec is None:
            raise MeshError(f"{qualified}: not installed here; install {REPOS.get(repo, repo)} or call an http tool with at=<node>")
        if spec.get("transport") != "http":
            raise MeshError(f"{qualified}: only http tools can run on another node")
    transport = spec.get("transport")
    if transport in ("python", "mcp"):
        return _call_python(spec, args, timeout)
    if transport == "cli":
        return _call_cli(spec, args, timeout)
    if transport == "http":
        return _call_http(spec, args, at, timeout)
    raise MeshError(f"{qualified}: unknown transport {transport!r}")


#: Runs one tool in the target repo's own interpreter. "python" tools name a
#: plain function; "mcp" tools name the repo's MCP server (an object, or a
#: function that builds one) and the tool is looked up on it, so every tool a
#: repo already serves over MCP is callable without a second registration.
_PY_RUNNER = (
    "import asyncio,importlib,inspect,json,sys\n"
    "kind,ref,tool=sys.argv[1:4]\n"
    "m,a=ref.split(':',1)\n"
    "obj=getattr(importlib.import_module(m),a)\n"
    "args=json.loads(sys.stdin.read() or '{}')\n"
    "if kind=='mcp':\n"
    "    srv=obj if hasattr(obj,'_tool_manager') else obj()\n"
    "    t=srv._tool_manager.get_tool(tool)\n"
    "    if t is None: raise SystemExit('no tool '+tool)\n"
    "    obj=t.fn\n"
    "r=obj(**args)\n"
    "if inspect.isawaitable(r): r=asyncio.run(r)\n"
    "sys.stdout.write('\\n'+json.dumps(r,default=str))\n"
)


def _call_python(spec: Dict[str, Any], args: Dict[str, Any], timeout: float) -> Any:
    d = Path(spec["repo_dir"])
    paths = [str(d / p) for p in (spec.get("pythonpath") or ["src", "."])]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    py = _repo_python(d)
    try:
        kind = spec.get("transport")
        ref = spec.get("server") if kind == "mcp" else spec.get("entry")
        if not ref:
            raise MeshError(f"{spec['repo']}.{spec['name']}: manifest names no {'server' if kind == 'mcp' else 'entry'}")
        out = subprocess.run([py, "-c", _PY_RUNNER, kind, ref, spec.get("tool") or spec["name"]],
                             input=json.dumps(args), capture_output=True,
                             text=True, cwd=str(d), env=env, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise MeshError(f"{spec['repo']}.{spec['name']}: timed out after {timeout:.0f}s") from exc
    if out.returncode != 0:
        raise MeshError(f"{spec['repo']}.{spec['name']}: {(out.stderr or out.stdout).strip()[-600:]}")
    last = out.stdout.rstrip().rsplit("\n", 1)[-1]
    try:
        return json.loads(last)
    except ValueError:
        return last


def _repo_python(d: Path) -> str:
    for rel in (".venv/bin/python", ".venv/Scripts/python.exe", "venv/bin/python"):
        p = d / rel
        if p.exists():
            return str(p)
    return sys.executable


def _call_cli(spec: Dict[str, Any], args: Dict[str, Any], timeout: float) -> Any:
    argv: List[str] = []
    for part in spec.get("argv") or []:
        m = re.fullmatch(r"\{(\w+)(\?)?\}", str(part))
        if m:
            if m.group(1) in args and args[m.group(1)] is not None:
                argv.append(str(args[m.group(1)]))
            elif not m.group(2):
                raise MeshError(f"{spec['repo']}.{spec['name']}: missing argument {m.group(1)!r}")
        else:
            argv.append(str(part))
    if not argv:
        raise MeshError(f"{spec['repo']}.{spec['name']}: empty argv")
    exe = shutil.which(argv[0]) or argv[0]
    try:
        out = subprocess.run([exe, *argv[1:]], capture_output=True, text=True, cwd=spec["repo_dir"], timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MeshError(f"{spec['repo']}.{spec['name']}: {exc}") from exc
    if out.returncode != 0:
        raise MeshError(f"{spec['repo']}.{spec['name']}: {(out.stderr or out.stdout).strip()[-600:]}")
    try:
        return json.loads(out.stdout)
    except ValueError:
        return out.stdout.strip()


def _call_http(spec: Dict[str, Any], args: Dict[str, Any], at: Optional[str], timeout: float) -> Any:
    service = spec.get("service") or spec["repo"]
    base = endpoint(service, at)
    if not base:
        raise MeshError(f"{spec['repo']}.{spec['name']}: no endpoint for {service}" + (f" on {at}" if at else ""))
    method = str(spec.get("method") or "POST").upper()
    url = base + str(spec.get("path") or "/")
    data = None
    headers = {"User-Agent": f"nougen-mesh/{MESH_VERSION}", "Accept": "application/json"}
    token = _env(f"NOUGEN_{service.upper().replace('-', '_')}_TOKEN") or _env("NOUGEN_MESH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if method == "GET":
        if args:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(args)
    else:
        data = json.dumps(args).encode()
        headers["Content-Type"] = "application/json"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method),
                                    timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise MeshError(f"{spec['repo']}.{spec['name']}: HTTP {exc.code} from {service}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise MeshError(f"{spec['repo']}.{spec['name']}: {service} not reachable ({exc})") from exc
    try:
        return json.loads(body)
    except ValueError:
        return body


def manifest_from_mcp(repo: str, server: str, *, pythonpath: Optional[List[str]] = None,
                      service: Optional[str] = None, version: str = "") -> Dict[str, Any]:
    """Build a repo's nougen.tools.json from the MCP server it already has.

    ``server`` is ``module:attr`` (a FastMCP/MCPServer object, or a function
    that returns one). Run from the repo root with its src importable.
    """
    import importlib

    m, a = server.split(":", 1)
    obj = getattr(importlib.import_module(m), a)
    srv = obj if hasattr(obj, "_tool_manager") else obj()
    out_tools = []
    for t in sorted(srv._tool_manager.list_tools(), key=lambda t: t.name):
        desc = (t.description or "").strip().splitlines()
        out_tools.append({"name": t.name, "transport": "mcp", "server": server,
                          "description": desc[0] if desc else "", "args": t.parameters})
    data: Dict[str, Any] = {"schema": MANIFEST_SCHEMA, "repo": repo, "mesh_version": MESH_VERSION,
                            "tools": out_tools}
    if version:
        data["version"] = version
    if service:
        data["service"] = service
    if pythonpath:
        for t in out_tools:
            t["pythonpath"] = pythonpath
    return data


# ---------------------------------------------------------------- setup
def setup(*, machine_name: Optional[str] = None, agent_name: Optional[str] = None, node_name: Optional[str] = None,
          repos_dir: Optional[str] = None, near: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """First run: write <home>/mesh.json with this tester's own identity.

    Keeps anything already in the file unless ``force``. Never copies another
    box's names: the defaults come from this box (hostname, git config).
    """
    path = config_path()
    cfg = {} if force else load()
    cfg["schema"] = CONFIG_SCHEMA
    ident = cfg.get("identity") if isinstance(cfg.get("identity"), dict) else {}
    ident["machine"] = machine_name or ident.get("machine") or machine()
    ident["agent"] = agent_name or ident.get("agent") or agent()
    ident["node"] = node_name or ident.get("node") or node()
    cfg["identity"] = ident
    if repos_dir:
        os.environ["NOUGEN_REPOS_DIR"] = repos_dir
    found = cfg.get("repos") if isinstance(cfg.get("repos"), dict) else {}
    for name, d in installed(near).items():
        found.setdefault(name, str(d))
    cfg["repos"] = found
    cfg.setdefault("ports", {})
    cfg.setdefault("endpoints", {})
    cfg.setdefault("nodes", {})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return cfg


def doctor(near: Optional[str] = None) -> Dict[str, Any]:
    have = installed(near)
    reg = tools(near)
    return {
        "mesh_version": MESH_VERSION,
        "config": str(config_path()),
        "config_present": config_path().exists(),
        "identity": identity(),
        "address": self_address(),
        "ingress": ingress(),
        "repos": {n: str(have[n]) if n in have else None for n in REPOS},
        "tools": len(reg),
        "repos_without_manifest": sorted(n for n, d in have.items() if not manifest(d)),
    }


def file_digest(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------- install + run
PACKAGE_FILE = "nougen.package.json"


def package(source: Optional[str] = None, near: Optional[str] = None) -> Dict[str, Any]:
    """The package list: which repos, cloned from where. ``source`` is a file;
    otherwise NOUGEN_PACKAGE_FILE, then nougen.package.json in the NouGenShards
    checkout. Clone URLs live in that data file, never in code."""
    for cand in (source, _env("NOUGEN_PACKAGE_FILE")):
        if cand:
            data = _read_json(Path(cand).expanduser())
            if isinstance(data, dict):
                return data
    shards = repo_dir("shards", near)
    data = _read_json(shards / PACKAGE_FILE) if shards is not None else None
    return data if isinstance(data, dict) else {}


def install(dest: str, *, source: Optional[str] = None, only: Optional[List[str]] = None, near: Optional[str] = None,
            deps: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    """Clone each package repo that is missing into ``dest``, side by side.

    Uses the tester's own git and GitHub access. ``deps`` also runs
    ``pip install -e`` for repos that have a pyproject.toml.
    """
    pkg = package(source, near)
    entries = pkg.get("repos") if isinstance(pkg.get("repos"), dict) else {}
    root = Path(dest).expanduser()
    os.environ["NOUGEN_REPOS_DIR"] = str(root)
    out: Dict[str, Any] = {}
    for name in only or list(REPOS):
        have = repo_dir(name, near)
        if have is not None:
            out[name] = {"state": "present", "path": str(have)}
            continue
        url = (entries.get(name) or {}).get("clone") if isinstance(entries.get(name), dict) else entries.get(name)
        if not url:
            out[name] = {"state": "no_source", "fix": f"add repos.{name}.clone to {PACKAGE_FILE}"}
            continue
        target = root / REPOS[name]
        if dry_run:
            out[name] = {"state": "would_clone", "path": str(target)}
            continue
        root.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "clone", "--depth", "1", str(url), str(target)], capture_output=True, text=True)
        out[name] = {"state": "cloned" if r.returncode == 0 else "clone_failed", "path": str(target)}
        if r.returncode != 0:
            out[name]["error"] = (r.stderr or r.stdout).strip()[-300:]
    if deps and not dry_run:
        for name, row in out.items():
            p = Path(row.get("path") or "")
            if row["state"] in ("cloned", "present") and (p / "pyproject.toml").exists():
                r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-e", str(p)],
                                   capture_output=True, text=True)
                row["deps"] = "ok" if r.returncode == 0 else (r.stderr or r.stdout).strip()[-300:]
    return out


def services(near: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Long-running services each installed repo declares in its manifest."""
    out: Dict[str, Dict[str, Any]] = {}
    for name, d in installed(near).items():
        for svc in manifest(d).get("services") or []:
            if isinstance(svc, dict) and svc.get("name") and svc.get("argv"):
                out[svc["name"]] = {**svc, "repo": name, "repo_dir": str(d)}
    return out


def _run_dir() -> Path:
    return home() / "run"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def _service_state(svc: Dict[str, Any]) -> Dict[str, Any]:
    pidfile = _run_dir() / f"{svc['name']}.pid"
    pid = int(pidfile.read_text().strip()) if pidfile.exists() and pidfile.read_text().strip().isdigit() else None
    url = endpoint(svc.get("port_service") or svc["name"])
    health = url + str(svc.get("health") or "/health") if url else None
    answers = False
    if health:
        try:
            with urllib.request.urlopen(health, timeout=1.5):
                answers = True
        except urllib.error.HTTPError:
            answers = True          # something is listening
        except (urllib.error.URLError, OSError):
            answers = False
    return {"repo": svc["repo"], "pid": pid if pid and _pid_alive(pid) else None, "url": url, "answers": answers}


def status(near: Optional[str] = None) -> Dict[str, Any]:
    return {name: _service_state(svc) for name, svc in services(near).items()}


def start(names: Optional[List[str]] = None, near: Optional[str] = None) -> Dict[str, Any]:
    """Start declared services (all, or those named by service or repo) in the background."""
    out: Dict[str, Any] = {}
    run = _run_dir()
    logs = home() / "logs"
    for name, svc in services(near).items():
        if names and name not in names and svc["repo"] not in names:
            continue
        state = _service_state(svc)
        if state["pid"] or state["answers"]:
            out[name] = {**state, "state": "already_up"}
            continue
        missing = [k for k in svc.get("env_required") or [] if not _env(k)]
        if missing:
            out[name] = {"repo": svc["repo"], "state": "needs_config", "set": missing}
            continue
        port_name = svc.get("port_service") or name
        fill = str(port(port_name) or "")
        argv = [str(a).replace("{port}", fill) for a in svc["argv"]]
        d = Path(svc["repo_dir"])
        exe = _repo_python(d) if argv[0] in ("python", "python3") else (shutil.which(argv[0]) or argv[0])
        env = dict(os.environ)
        env.update({str(k): str(v).replace("{port}", fill) for k, v in (svc.get("env") or {}).items()})
        env["PYTHONPATH"] = os.pathsep.join([str(d / "src"), str(d)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        run.mkdir(parents=True, exist_ok=True)
        logs.mkdir(parents=True, exist_ok=True)
        log = open(logs / f"{name}.log", "ab")
        try:
            proc = subprocess.Popen([exe, *argv[1:]], cwd=str(d), env=env, stdout=log, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, start_new_session=os.name != "nt")
        except OSError as exc:
            out[name] = {"repo": svc["repo"], "state": "failed", "error": str(exc)}
            continue
        finally:
            log.close()
        (run / f"{name}.pid").write_text(str(proc.pid))
        out[name] = {"repo": svc["repo"], "state": "started", "pid": proc.pid, "log": str(logs / f"{name}.log")}
    return out


def stop(names: Optional[List[str]] = None, near: Optional[str] = None) -> Dict[str, Any]:
    """Stop services this mesh started (only pids it recorded; never anything else)."""
    import signal

    out: Dict[str, Any] = {}
    for name, svc in services(near).items():
        if names and name not in names and svc["repo"] not in names:
            continue
        pidfile = _run_dir() / f"{name}.pid"
        raw = pidfile.read_text().strip() if pidfile.exists() else ""
        if not raw.isdigit() or not _pid_alive(int(raw)):
            pidfile.unlink(missing_ok=True)
            out[name] = "not_running"
            continue
        try:
            os.kill(int(raw), signal.SIGTERM)
            out[name] = "stopped"
        except OSError as exc:
            out[name] = f"failed: {exc}"
        pidfile.unlink(missing_ok=True)
    return out


def parse_args(tokens: List[str]) -> Dict[str, Any]:
    """CLI arguments for a tool: one JSON object, or key=value pairs (values JSON when they parse)."""
    if len(tokens) == 1 and tokens[0].lstrip().startswith("{"):
        return json.loads(tokens[0])
    out: Dict[str, Any] = {}
    for tok in tokens:
        if "=" not in tok:
            raise ValueError(f"argument {tok!r}: use key=value or one JSON object")
        k, v = tok.split("=", 1)
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


# ---------------------------------------------------------------- CLI
def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="nougen mesh", description="Install, run and call tools across the NouGen repos.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="write this box's mesh.json (first run)")
    s.add_argument("--machine")
    s.add_argument("--agent")
    s.add_argument("--node")
    s.add_argument("--repos-dir")
    s.add_argument("--force", action="store_true")
    sub.add_parser("whoami")
    sub.add_parser("doctor")
    sub.add_parser("tools")
    c = sub.add_parser("call", help="call repo.tool with key=value args or one JSON object")
    c.add_argument("tool")
    c.add_argument("args", nargs="*")
    c.add_argument("--at", help="run on another node through its endpoint")
    g = sub.add_parser("manifest", help="write nougen.tools.json from this repo's MCP server")
    g.add_argument("repo", choices=sorted(REPOS))
    g.add_argument("server", help="module:attr of the MCP server or its builder")
    g.add_argument("--service")
    g.add_argument("--pythonpath", nargs="*")
    g.add_argument("--merge", help="JSON file of extra tools (cli/http) to append")
    i = sub.add_parser("install", help="clone the package repos that are missing, side by side")
    i.add_argument("--dir", default=".", help="where the repos go (default: here)")
    i.add_argument("--source", help="package file (default: nougen.package.json in NouGenShards)")
    i.add_argument("--only", nargs="*", choices=sorted(REPOS))
    i.add_argument("--deps", action="store_true", help="also pip install -e each Python repo")
    i.add_argument("--dry-run", action="store_true")
    for verb in ("up", "down"):
        u = sub.add_parser(verb, help=("start" if verb == "up" else "stop") + " services (all, or the named ones)")
        u.add_argument("names", nargs="*")
    sub.add_parser("status", help="which services are running")
    v = sub.add_parser("check-vendored", help="compare a vendored nougen_mesh.py with this file")
    v.add_argument("paths", nargs="+")
    ns = ap.parse_args(argv)
    here = os.getcwd() if _repo_top(Path(os.getcwd())) is not None else __file__
    if ns.cmd == "setup":
        out: Any = setup(machine_name=ns.machine, agent_name=ns.agent, node_name=ns.node, repos_dir=ns.repos_dir,
                         near=here, force=ns.force)
    elif ns.cmd == "whoami":
        out = {**identity(), "address": self_address()}
    elif ns.cmd == "doctor":
        out = doctor(here)
    elif ns.cmd == "tools":
        out = {k: {"transport": v.get("transport"), "description": v.get("description", "")}
               for k, v in sorted(tools(here).items())}
    elif ns.cmd == "call":
        try:
            out = call(ns.tool, parse_args(ns.args), near=here, at=ns.at)
        except (MeshError, ValueError) as exc:
            print(json.dumps({"error": str(exc)}))
            return 1
    elif ns.cmd == "install":
        out = install(ns.dir, source=ns.source, only=ns.only, near=here, deps=ns.deps, dry_run=ns.dry_run)
    elif ns.cmd == "up":
        out = start(ns.names or None, near=here)
    elif ns.cmd == "down":
        out = stop(ns.names or None, near=here)
    elif ns.cmd == "status":
        out = status(here)
    elif ns.cmd == "manifest":
        data = manifest_from_mcp(ns.repo, ns.server, pythonpath=ns.pythonpath, service=ns.service)
        prev = _read_json(Path(MANIFEST_FILE))
        prev = prev if isinstance(prev, dict) else {}
        # hand-written parts survive a regenerate: services, and tools that are not MCP tools
        extra = [t for t in prev.get("tools") or [] if isinstance(t, dict) and t.get("transport") != "mcp"]
        if ns.merge:
            extra += _read_json(Path(ns.merge)) or []
        names = {t["name"] for t in data["tools"]}
        for t in extra:
            if isinstance(t, dict) and t.get("name") and t["name"] not in names:
                data["tools"].append(t)
                names.add(t["name"])
        if prev.get("services"):
            data["services"] = prev["services"]
        Path(MANIFEST_FILE).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        out = {"wrote": MANIFEST_FILE, "tools": len(data["tools"])}
    else:
        mine = file_digest(__file__)
        bad = [p for p in ns.paths if file_digest(p) != mine]
        out = {"ok": not bad, "differs": bad}
        print(json.dumps(out, indent=2))
        return 0 if not bad else 1
    print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
