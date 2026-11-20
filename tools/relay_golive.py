#!/usr/bin/env python3
"""One-command relay go-live: gate, deploy, check, print.

Four steps, each gated on the one before. The run stops at the first failure
and says why.

  a) merged     the relay transport PR is merged on main
  b) relay      deploy workers/relay (production env), then probe its health
  c) supervisor is the pinned supervisor release new enough to carry the relay
                transport? Reports only; never cuts a release.
  d) join       prints the join-worker deploy command with the relay URL and
                RELAY_AUTH namespace id resolved from the relay's account

Dry run (the default) changes nothing: step b reports what it would deploy and
probes health read-only. ``--apply`` runs the relay deploy for real.

The Cloudflare token is never read by this process. It reaches the child
process through the keymaker CLI (``keyfor.py NAME --exec --``), and only its
fingerprint is ever printed (by keyfor itself). The account id is resolved at
run time from what the token can see: the account that owns the relay's
RELAY_AUTH namespace wins.

Every environment-shaped value resolves from env first:
  NOUGEN_GOLIVE_REPO            GitHub repo (default Who-Visions/NouGenShards)
  NOUGEN_GOLIVE_PR              PR number to gate on (default 1136)
  NOUGEN_GOLIVE_CF_KEY          keymaker slot for the token
  NOUGEN_GOLIVE_KEYFOR          path to keyfor.py
  NOUGEN_GOLIVE_HEALTH_TIMEOUT  seconds for the health probe
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELAY_DIR = ROOT / "workers" / "relay"
RELAY_CONFIG = RELAY_DIR / "wrangler.jsonc"
RELAY_WORKER = RELAY_DIR / "worker.js"
JOIN_WORKER = ROOT / "workers" / "join" / "worker.js"
CF_API = os.environ.get("NOUGEN_GOLIVE_CF_API", "https://api.cloudflare.com/client/v4")


def _env(name: str, fallback: str) -> str:
    value = (os.environ.get(name) or "").strip()
    return value or fallback


def repo() -> str:
    return _env("NOUGEN_GOLIVE_REPO", "Who-Visions/NouGenShards")


def pr_number() -> str:
    return _env("NOUGEN_GOLIVE_PR", "1136")


def cf_key() -> str:
    return _env("NOUGEN_GOLIVE_CF_KEY", "CLOUDFLARE_API_TOKEN_NOUGEN_FULL")


def keyfor_path() -> str:
    return _env("NOUGEN_GOLIVE_KEYFOR", str(Path.home() / ".nougen" / "bin" / "keyfor.py"))


def health_timeout() -> float:
    try:
        return float(_env("NOUGEN_GOLIVE_HEALTH_TIMEOUT", "15"))
    except ValueError:
        return 15.0


class GateError(RuntimeError):
    """A gate failed; the message is the reason shown to the operator."""


@dataclass
class Ctx:
    apply: bool
    run: callable  # (argv, env=None) -> CompletedProcess
    fetch: callable  # (url, timeout) -> (status, body)
    merge_sha: str = ""
    account_id: str = ""
    kv_id: str = ""
    relay_url: str = ""


def _run(argv, env=None):
    return subprocess.run(argv, capture_output=True, text=True, env=env, cwd=str(ROOT))


def _fetch(url, timeout):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, resp.read(2048).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except (urllib.error.URLError, OSError) as exc:
        return 0, str(exc)


def strip_jsonc(text: str) -> str:
    """Drop // and /* */ comments outside strings, then trailing commas."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            out.append(ch)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def relay_config(path: Path = RELAY_CONFIG) -> tuple[str, str]:
    """(RELAY_AUTH namespace id, relay host) of the production env."""
    cfg = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
    prod = (cfg.get("env") or {}).get("production") or {}
    kv = [k["id"] for k in prod.get("kv_namespaces", []) if k.get("binding") == "RELAY_AUTH"]
    hosts = [r["pattern"] for r in prod.get("routes", []) if r.get("custom_domain")]
    if not kv:
        raise GateError(f"{path.name}: production env has no RELAY_AUTH namespace")
    if not hosts:
        raise GateError(f"{path.name}: production env has no custom-domain route")
    return kv[0], hosts[0]


def relay_paths(path: Path = RELAY_WORKER) -> tuple[str, str]:
    """(connect path, health path) as the relay worker routes them.

    The worker only upgrades on its connect path; a bare origin 404s. Read
    both from the worker source so this tool can never drift from it.
    """
    routes = set(re.findall(r'pathname\s*===\s*"(/[^"]+)"', path.read_text(encoding="utf-8")))
    connect = sorted(r for r in routes if r.endswith("/connect"))
    health = sorted(r for r in routes if r.endswith("/health"))
    if not connect or not health:
        raise GateError(f"{path.name}: could not find the connect and health routes")
    return connect[0], health[0]


def pinned_supervisor(path: Path = JOIN_WORKER) -> str:
    """The supervisor release tag the join worker downloads, e.g. supervisor-v1.3.2."""
    m = re.search(r"releases/download/(supervisor-v[0-9][^/\"']*)/", path.read_text(encoding="utf-8"))
    if not m:
        raise GateError(f"{path.name}: no pinned supervisor release found")
    return m.group(1)


def keyfor_argv(cmd: list[str]) -> list[str]:
    return [sys.executable, keyfor_path(), cf_key(), "--exec", "--as", "CLOUDFLARE_API_TOKEN", "--", *cmd]


# ---- steps -----------------------------------------------------------------

def step_merged(ctx: Ctx) -> str:
    r = ctx.run(["gh", "pr", "view", pr_number(), "-R", repo(), "--json", "state,mergedAt,mergeCommit,baseRefName"])
    if r.returncode != 0:
        raise GateError(f"gh pr view {pr_number()} failed: {(r.stderr or r.stdout).strip()[:200]}")
    data = json.loads(r.stdout or "{}")
    if data.get("state") != "MERGED":
        raise GateError(f"PR {pr_number()} is {data.get('state') or 'unknown'}, not merged; nothing deployed")
    if data.get("baseRefName") not in (None, "", "main"):
        raise GateError(f"PR {pr_number()} merged into {data['baseRefName']}, not main")
    ctx.merge_sha = ((data.get("mergeCommit") or {}).get("oid") or "")
    if not ctx.merge_sha:
        raise GateError(f"PR {pr_number()} has no merge commit to check against this checkout")
    # The deploy uses this checkout's files, so the merge must be in it, not just on GitHub.
    a = ctx.run(["git", "merge-base", "--is-ancestor", ctx.merge_sha, "HEAD"])
    if a.returncode == 1:
        raise GateError(f"this checkout does not contain merge {ctx.merge_sha[:10]}; pull main first")
    if a.returncode != 0:
        raise GateError(f"merge {ctx.merge_sha[:10]} not found locally; git fetch origin main first")
    return f"PR {pr_number()} merged {data.get('mergedAt')} as {ctx.merge_sha[:10] or '?'}"


def step_relay(ctx: Ctx) -> str:
    ctx.kv_id, host = relay_config()
    connect, health = relay_paths()
    ctx.relay_url = f"wss://{host}{connect}"
    r = ctx.run(keyfor_argv([sys.executable, str(Path(__file__).resolve()), "_cf-account", ctx.kv_id]))
    if r.returncode != 0:
        raise GateError(f"account resolve failed: {(r.stderr or r.stdout).strip()[-300:]}")
    ctx.account_id = (r.stdout or "").strip().splitlines()[-1].strip() if r.stdout.strip() else ""
    if not re.fullmatch(r"[0-9a-f]{32}", ctx.account_id):
        raise GateError("account resolve returned no account id")
    deploy = ["npx", "--yes", "wrangler", "deploy", "--env", "production", "--config", str(RELAY_CONFIG)]
    if ctx.apply:
        env = {**os.environ, "CLOUDFLARE_ACCOUNT_ID": ctx.account_id}
        d = ctx.run(keyfor_argv(deploy), env=env)
        if d.returncode != 0:
            raise GateError(f"DEPLOY FAILED (wrangler exit {d.returncode}): {(d.stderr or d.stdout).strip()[-300:]}")
        did = "deployed"
    else:
        did = "dry run, would run: " + " ".join(shlex.quote(a) for a in deploy)
    status, body = ctx.fetch(f"https://{host}{health}", health_timeout())
    healthy = status == 200 and body.strip() == "ok"
    if ctx.apply and not healthy:
        raise GateError(f"HEALTH FAILED after a successful deploy: https://{host}{health} answered {status} {body[:80]!r}")
    return f"account {ctx.account_id[:6]}... owns RELAY_AUTH {ctx.kv_id[:6]}...; {did}; health {status}{' ok' if healthy else ' (not live yet)'}"


def _version(tag: str) -> tuple:
    return tuple(int(p) for p in re.findall(r"\d+", tag.split("-v", 1)[-1])[:3])


def step_supervisor(ctx: Ctx) -> str:
    pinned = pinned_supervisor()
    r = ctx.run(["gh", "release", "list", "-R", repo(), "-L", "50", "--json", "tagName,isDraft"])
    if r.returncode != 0:
        raise GateError(f"gh release list failed: {(r.stderr or r.stdout).strip()[:200]}")
    tags = [x["tagName"] for x in json.loads(r.stdout or "[]")
            if x.get("tagName", "").startswith("supervisor-v") and not x.get("isDraft")]
    if not tags:
        raise GateError("no supervisor releases found")
    latest = max(tags, key=_version)
    notes = [f"pinned {pinned}, latest {latest}"]
    need = _version(latest) > _version(pinned)
    if need:
        notes.append("BUMP NEEDED: pin the join worker to the latest release")
    if ctx.merge_sha:
        a = ctx.run(["git", "merge-base", "--is-ancestor", ctx.merge_sha, latest])
        if a.returncode == 1:
            need = True
            notes.append(f"RELEASE NEEDED: {latest} predates merge {ctx.merge_sha[:10]}; cut a supervisor release, then bump the pin")
        elif a.returncode != 0:
            notes.append("ancestry unknown (fetch tags and main locally to check)")
    if not need:
        notes.append("pin is current")
    return "; ".join(notes)


def step_join(ctx: Ctx) -> str:
    if not (ctx.relay_url and ctx.kv_id):
        ctx.kv_id, host = relay_config()
        ctx.relay_url = f"wss://{host}{relay_paths()[0]}"
    cmd = (f"$env:NOUGEN_JOIN_RELAY_URL='{ctx.relay_url}'; "
           f"$env:NOUGEN_JOIN_RELAY_AUTH_KV_ID='{ctx.kv_id}'; "
           f"python workers/join/deploy.py")
    return "run after the supervisor pin is current:\n    " + cmd


STEPS = [("merged", step_merged), ("relay", step_relay), ("supervisor", step_supervisor), ("join", step_join)]


def run_steps(ctx: Ctx, out=print) -> int:
    for name, fn in STEPS:
        try:
            out(f"[ok]   {name}: {fn(ctx)}")
        except GateError as exc:
            out(f"[STOP] {name}: {exc}")
            return 1
    out("[done] " + ("applied" if ctx.apply else "dry run, nothing changed"))
    return 0


# ---- internal: runs under keyfor --exec with the token in env --------------

def cf_account(kv_id: str, get=None) -> str:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not token:
        raise GateError("CLOUDFLARE_API_TOKEN not in env (run through keyfor --exec)")

    def _get(path):
        req = urllib.request.Request(CF_API + path, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=health_timeout()) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError:
            return {"success": False}
        except (urllib.error.URLError, OSError) as exc:
            raise GateError(f"Cloudflare API unreachable: {exc}") from None

    get = get or _get
    accounts = get("/accounts?per_page=50").get("result") or []
    for acct in accounts:
        if get(f"/accounts/{acct['id']}/storage/kv/namespaces/{kv_id}").get("success"):
            return acct["id"]
    raise GateError(f"none of the token's {len(accounts)} account(s) owns namespace {kv_id[:6]}...")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["_cf-account"]:
        try:
            print(cf_account(argv[1]))
            return 0
        except GateError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="deploy the relay for real (default: dry run)")
    args = ap.parse_args(argv)
    return run_steps(Ctx(apply=args.apply, run=_run, fetch=_fetch))


if __name__ == "__main__":
    sys.exit(main())
