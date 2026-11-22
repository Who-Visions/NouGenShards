"""Ship the NouGen tester package through Cloudflare R2.

Testers never need access to the owner's GitHub. A fleet box packs each
package repo's committed tree (no git history) into a tarball, scans every
file for leaked keys, writes a manifest with sha256 sums, and uploads all of
it to a private R2 bucket. ``share`` then makes expiring links, and a tester
installs with one link::

    nougen mesh pack    --repos ~/nougen --out ~/.nougen/dist      # tarballs + manifest, refuses on a leaked key
    nougen mesh publish --dist ~/.nougen/dist [--dry-run]          # upload what changed to R2
    nougen mesh share   --days 7                                   # one expiring link for a tester
    nougen mesh install --dir ~/nougen --from '<link>'             # tester side: download, verify, unpack
    nougen mesh sync    --repos ~/nougen                           # pull + pack + publish, for cron or launchd

Everything resolves at runtime. Credentials come from the environment, then
Keymaker; the bucket and prefix from the environment, then ``mesh.json``
(``package.r2``). Nothing here names a node, account, bucket or host.
Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCHEMA = "nougen-package-dist/1"
DEFAULT_PREFIX = "packages/nougen-tester"
MAX_SHARE_DAYS = 7  # SigV4 presigned URLs cannot live longer than 7 days

# Credential names, first hit wins. Values are read, never printed.
CRED_NAMES = {
    "account": ("NOUGEN_R2_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID", "NOUGEN_CF_ACCOUNT_ID"),
    "access_key": ("NOUGEN_R2_ACCESS_KEY_ID", "R2_ACCESS_KEY_ID"),
    "secret_key": ("NOUGEN_R2_SECRET_ACCESS_KEY", "R2_SECRET_ACCESS_KEY"),
    "bucket": ("NOUGEN_R2_BUCKET", "R2_BUCKET"),
}

# ------------------------------------------------------------------ leak scan
SECRET_PATTERNS: Dict[str, str] = {
    "anthropic_key": r"sk-ant-[A-Za-z0-9_\-]{20,}",
    "openrouter_key": r"sk-or-v1-[a-f0-9]{40,}",
    "openai_key": r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,100}\b",
    "github_token": r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{50,}",
    "google_api_key": r"\bAIza[0-9A-Za-z_\-]{35}\b",
    "google_oauth_refresh": r"\b1//0[A-Za-z0-9_\-]{30,}",
    "google_oauth_access": r"\bya29\.[A-Za-z0-9_\-]{30,}",
    "huggingface_token": r"\bhf_[A-Za-z0-9]{30,}\b",
    "aws_key_id": r"\bAKIA[0-9A-Z]{16}\b",
    "slack_token": r"\bxox[abposr]-[A-Za-z0-9\-]{10,}",
    "stripe_live": r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}",
    "nvidia_key": r"\bnvapi-[A-Za-z0-9_\-]{30,}",
    "groq_key": r"\bgsk_[A-Za-z0-9]{40,}",
    "telegram_bot": r"\b\d{8,10}:AA[A-Za-z0-9_\-]{33}\b",
    "private_key_block": r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----\s*[\r\n]+\s*[A-Za-z0-9+/=]{40,}",
    "assigned_secret": r"(?i)[\"']?[a-z0-9_]*(?:api[_-]?key|secret[_-]?(?:key|token)?|access[_-]?token|refresh[_-]?token|password)[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_\-+/=.]{24,}[\"']",
}
_SECRET_RX = {k: re.compile(v) for k, v in SECRET_PATTERNS.items()}
_PLACEHOLDER = re.compile(r"(?i)x{5,}|example|dummy|placeholder|your[_-]?|changeme|fake|sample|redacted|<|\$\{|\{\{|0{10,}|\.{3}")
_TEXT_LIMIT = 8 * 1024 * 1024


_ENV_NAME = re.compile(r"[\"'][A-Z][A-Z0-9_]+[\"']$")  # KEY = "SOME_ENV_VAR_NAME" names a key, it is not one


def value_id(value: str) -> str:
    """A short sha256 of a flagged value: lets a known test fixture be allowed without writing it down."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def scan_text(text: str, allow: Iterable[str] = ()) -> List[Tuple[str, int, str]]:
    """(kind, line, value_id) for each secret-shaped value that is not a placeholder or an allowed fixture."""
    allowed = set(allow)
    hits: List[Tuple[str, int, str]] = []
    for kind, rx in _SECRET_RX.items():
        for m in rx.finditer(text):
            val = m.group(0)
            if _PLACEHOLDER.search(val) or (kind == "assigned_secret" and _ENV_NAME.search(val)):
                continue
            vid = value_id(val)
            if vid in allowed:
                continue
            hits.append((kind, text.count("\n", 0, m.start()) + 1, vid))
    return hits


def scan_tarball(path: Path, allow: Iterable[str] = ()) -> List[Dict[str, Any]]:
    """Scan every text file in a tarball. Findings name the file, line, kind and value id, never the value."""
    allow = list(allow)
    found: List[Dict[str, Any]] = []
    with tarfile.open(path, "r:gz") as tf:
        for member in tf:
            if not member.isfile() or member.size > _TEXT_LIMIT:
                continue
            raw = tf.extractfile(member).read()  # type: ignore[union-attr]
            if b"\x00" in raw[:8192]:
                continue
            for kind, line, vid in scan_text(raw.decode("utf-8", "replace"), allow):
                found.append({"file": member.name, "line": line, "kind": kind, "value_id": vid})
    return found


# ------------------------------------------------------------------ config
def _mesh():
    from . import mesh  # noqa: PLC0415 - lazy, keeps this importable alone
    return mesh


def _secret(names: Iterable[str]) -> Optional[str]:
    for n in names:
        v = os.environ.get(n)
        if v:
            return v.strip()
    try:
        from . import keymaker  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - a tester box has no Keymaker
        return None
    for n in names:
        try:
            v = keymaker.get_secret(n)
        except Exception:  # noqa: BLE001
            v = None
        if v:
            return str(v).strip()
    return None


def r2_settings() -> Dict[str, Any]:
    """Bucket, prefix, endpoint and credentials, resolved at runtime.

    Raises ``R2ConfigError`` naming every missing key and where it may live.
    """
    conf = {}
    try:
        conf = (_mesh().load().get("package") or {}).get("r2") or {}
    except Exception:  # noqa: BLE001
        conf = {}
    account = _secret(CRED_NAMES["account"]) or conf.get("account_id")
    bucket = os.environ.get("NOUGEN_R2_BUCKET") or conf.get("bucket") or _secret(CRED_NAMES["bucket"][1:])
    access = _secret(CRED_NAMES["access_key"])
    secret = _secret(CRED_NAMES["secret_key"])
    endpoint = os.environ.get("NOUGEN_R2_ENDPOINT") or conf.get("endpoint") or (
        f"https://{account}.r2.cloudflarestorage.com" if account else None)
    missing = []
    if not endpoint:
        missing.append("account id: " + " or ".join(CRED_NAMES["account"]) + " (env or Keymaker), or package.r2.account_id in mesh.json")
    if not bucket:
        missing.append("bucket: NOUGEN_R2_BUCKET (env) or package.r2.bucket in mesh.json")
    if not access:
        missing.append("R2 access key id: " + " or ".join(CRED_NAMES["access_key"]) + " (env or Keymaker)")
    if not secret:
        missing.append("R2 secret access key: " + " or ".join(CRED_NAMES["secret_key"]) + " (env or Keymaker)")
    if missing:
        raise R2ConfigError("R2 is not configured. Missing: " + "; ".join(missing))
    prefix = (os.environ.get("NOUGEN_R2_PREFIX") or conf.get("prefix") or DEFAULT_PREFIX).strip("/")
    return {"endpoint": endpoint.rstrip("/"), "bucket": bucket, "prefix": prefix,
            "access_key": access, "secret_key": secret, "region": conf.get("region") or "auto"}


class R2ConfigError(RuntimeError):
    pass


class R2Error(RuntimeError):
    pass


# ------------------------------------------------------------------ SigV4 (S3)
def _h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sign_key(secret: str, date: str, region: str, service: str = "s3") -> bytes:
    k = hmac.new(("AWS4" + secret).encode(), date.encode(), hashlib.sha256).digest()
    for part in (region, service, "aws4_request"):
        k = hmac.new(k, part.encode(), hashlib.sha256).digest()
    return k


def _quote_path(path: str) -> str:
    return urllib.parse.quote(path, safe="/-_.~")


def _canonical_query(params: Dict[str, str]) -> str:
    return "&".join(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
                    for k, v in sorted(params.items()))


def presign(method: str, url: str, access_key: str, secret_key: str, *, expires: int,
            region: str = "auto", now: Optional[_dt.datetime] = None) -> str:
    """A SigV4 query-signed URL (path-style), valid for ``expires`` seconds."""
    if not 1 <= expires <= MAX_SHARE_DAYS * 86400:
        raise ValueError(f"expires must be 1..{MAX_SHARE_DAYS * 86400} seconds")
    now = now or _dt.datetime.now(_dt.timezone.utc)
    amz, date = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    u = urllib.parse.urlsplit(url)
    scope = f"{date}/{region}/s3/aws4_request"
    params = {"X-Amz-Algorithm": "AWS4-HMAC-SHA256", "X-Amz-Credential": f"{access_key}/{scope}",
              "X-Amz-Date": amz, "X-Amz-Expires": str(expires), "X-Amz-SignedHeaders": "host"}
    path = _quote_path(u.path or "/")
    creq = "\n".join([method, path, _canonical_query(params), f"host:{u.netloc}\n", "host", "UNSIGNED-PAYLOAD"])
    sts = "\n".join(["AWS4-HMAC-SHA256", amz, scope, _h(creq.encode())])
    sig = hmac.new(_sign_key(secret_key, date, region), sts.encode(), hashlib.sha256).hexdigest()
    return f"{u.scheme}://{u.netloc}{path}?{_canonical_query(params)}&X-Amz-Signature={sig}"


def _signed_request(method: str, url: str, s: Dict[str, Any], body: bytes = b"",
                    content_type: Optional[str] = None, timeout: float = 120) -> Tuple[int, bytes, Dict[str, str]]:
    now = _dt.datetime.now(_dt.timezone.utc)
    amz, date = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    u = urllib.parse.urlsplit(url)
    payload = _h(body)
    headers = {"host": u.netloc, "x-amz-content-sha256": payload, "x-amz-date": amz}
    if content_type:
        headers["content-type"] = content_type
    signed = ";".join(sorted(headers))
    creq = "\n".join([method, _quote_path(u.path or "/"), u.query,
                      "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)), signed, payload])
    scope = f"{date}/{s['region']}/s3/aws4_request"
    sts = "\n".join(["AWS4-HMAC-SHA256", amz, scope, _h(creq.encode())])
    sig = hmac.new(_sign_key(s["secret_key"], date, s["region"]), sts.encode(), hashlib.sha256).hexdigest()
    hdrs = {k: v for k, v in headers.items() if k != "host"}
    hdrs["Authorization"] = (f"AWS4-HMAC-SHA256 Credential={s['access_key']}/{scope}, "
                             f"SignedHeaders={signed}, Signature={sig}")
    req = urllib.request.Request(url, data=body if method in ("PUT", "POST") else None, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read() or b"", dict(e.headers or {})


def _object_url(s: Dict[str, Any], key: str) -> str:
    return f"{s['endpoint']}/{s['bucket']}/{key}"


# ------------------------------------------------------------------ pack
def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def default_ref(repo: Path) -> str:
    """The remote default branch (origin/HEAD, else origin/main or master), else HEAD."""
    for ref in ("refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/master"):
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", ref], capture_output=True, text=True)
        if r.returncode == 0:
            return ref
    return "HEAD"


def pack(repos_dir: Optional[str] = None, out_dir: Optional[str] = None, *, only: Optional[List[str]] = None,
         ref: str = "HEAD", near: Optional[str] = None) -> Dict[str, Any]:
    """Tarball each package repo's committed tree at ``ref``, scan it, write the manifest.

    ``ref`` is a git ref, or ``"default"`` for each repo's remote default branch.
    A repo whose tarball holds a secret-shaped value is left out of the
    manifest and reported under ``refused``; the whole pack is then not ok.
    Per-repo ``exclude`` globs in the package file keep runtime data (logs,
    handoffs) out of the tarball, and ``scan_allow`` lists the value ids of
    known fake keys in test fixtures. History never ships.
    """
    mesh = _mesh()
    if repos_dir:
        os.environ["NOUGEN_REPOS_DIR"] = str(Path(repos_dir).expanduser())
    pkg = mesh.package(None, near)
    entries = pkg.get("repos") if isinstance(pkg.get("repos"), dict) else {}
    out = Path(out_dir or (mesh.home() / "dist")).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    repos: Dict[str, Any] = {}
    refused: Dict[str, Any] = {}
    missing: List[str] = []
    for name in only or list(mesh.REPOS):
        d = mesh.repo_dir(name, near)
        if d is None:
            missing.append(name)
            continue
        top = mesh._repo_top(d) or d  # noqa: SLF001
        sha = _git(top, "rev-parse", default_ref(top) if ref == "default" else ref)
        when = _git(top, "show", "-s", "--format=%cI", sha)
        spec = entries.get(name) if isinstance(entries.get(name), dict) else {}
        excludes = [f":(exclude,glob){g}" for g in spec.get("exclude") or []]
        folder = mesh.REPOS[name]
        fname = f"{name}-{sha[:12]}.tar.gz"
        target = out / fname
        if not target.exists():
            tmp = target.with_suffix(".part")
            with open(tmp, "wb") as fh:
                subprocess.run(["git", "-C", str(top), "archive", "--format=tar.gz", f"--prefix={folder}/", sha,
                                "--", ".", *excludes], stdout=fh, check=True)
            tmp.replace(target)
        data = target.read_bytes()
        allow = spec.get("scan_allow") or []
        findings = scan_tarball(target, allow)
        row = {"folder": folder, "commit": sha, "committed": when, "file": fname,
               "sha256": _h(data), "bytes": len(data)}
        if findings:
            refused[name] = {**row, "findings": findings[:50], "count": len(findings)}
            target.unlink()
            continue
        repos[name] = {**row, "scan_allow": allow} if allow else row
    manifest = {"schema": SCHEMA, "name": pkg.get("name") or "nougen-tester",
                "built": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat(),
                "repos": repos}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return {"ok": not refused and not missing, "dist": str(out), "repos": repos, "refused": refused,
            "missing": missing}


# ------------------------------------------------------------------ publish / share
def publish(dist: Optional[str] = None, *, dry_run: bool = False, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Upload each tarball the bucket lacks, then the manifest. Refuses a dist that holds a refused repo."""
    d = Path(dist or (_mesh().home() / "dist")).expanduser()
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    for row in manifest["repos"].values():  # re-verify: what goes up is what was scanned
        p = d / row["file"]
        if _h(p.read_bytes()) != row["sha256"]:
            raise R2Error(f"{row['file']} changed since it was packed; pack again")
        if scan_tarball(p, row.get("scan_allow") or []):
            raise R2Error(f"{row['file']} holds a secret-shaped value; nothing was uploaded")
    s = settings or r2_settings()
    plan, done = [], []
    for name, row in sorted(manifest["repos"].items()):
        key = f"{s['prefix']}/{row['file']}"
        if not dry_run:
            code, _, _ = _signed_request("HEAD", _object_url(s, key), s)
            if code == 200:
                plan.append({"key": key, "action": "present"})
                continue
        plan.append({"key": key, "action": "upload", "bytes": row["bytes"]})
    if dry_run:
        return {"dry_run": True, "bucket": s["bucket"], "plan": plan + [
            {"key": f"{s['prefix']}/install.py", "action": "upload"}, {"key": f"{s['prefix']}/manifest.json", "action": "upload"}]}
    for step in plan:
        if step["action"] != "upload":
            continue
        body = (d / step["key"].rsplit("/", 1)[1]).read_bytes()
        code, resp, _ = _signed_request("PUT", _object_url(s, step["key"]), s, body, "application/gzip", timeout=600)
        if code not in (200, 201):
            raise R2Error(f"upload {step['key']} failed: HTTP {code} {resp[:200]!r}")
        done.append(step["key"])
    ikey = f"{s['prefix']}/install.py"  # this file: stdlib only, runs alone as the tester's installer
    code, resp, _ = _signed_request("PUT", _object_url(s, ikey), s, Path(__file__).read_bytes(), "text/x-python")
    if code not in (200, 201):
        raise R2Error(f"upload {ikey} failed: HTTP {code} {resp[:200]!r}")
    done.append(ikey)
    mkey = f"{s['prefix']}/manifest.json"
    code, resp, _ = _signed_request("PUT", _object_url(s, mkey), s, (d / "manifest.json").read_bytes(), "application/json")
    if code not in (200, 201):
        raise R2Error(f"upload {mkey} failed: HTTP {code} {resp[:200]!r}")
    return {"bucket": s["bucket"], "uploaded": done + [mkey], "present": [p["key"] for p in plan if p["action"] == "present"],
            "repos": len(manifest["repos"])}


def share(*, days: float = 7, settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Write a share file of expiring links to the published package; return one expiring link to it."""
    seconds = int(min(days, MAX_SHARE_DAYS) * 86400)
    s = settings or r2_settings()
    code, body, _ = _signed_request("GET", _object_url(s, f"{s['prefix']}/manifest.json"), s)
    if code != 200:
        raise R2Error(f"no published manifest under {s['prefix']}/ (HTTP {code}); run publish first")
    manifest = json.loads(body)
    links = {name: {**row, "url": presign("GET", _object_url(s, f"{s['prefix']}/{row['file']}"),
                                          s["access_key"], s["secret_key"], expires=seconds, region=s["region"])}
             for name, row in manifest["repos"].items()}
    expires_at = (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(seconds=seconds)).replace(microsecond=0)
    sid = hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    share_doc = {**manifest, "repos": links, "expires": expires_at.isoformat()}
    skey = f"{s['prefix']}/shares/{sid}.json"
    code, resp, _ = _signed_request("PUT", _object_url(s, skey), s, json.dumps(share_doc, indent=1).encode(), "application/json")
    if code not in (200, 201):
        raise R2Error(f"upload {skey} failed: HTTP {code} {resp[:200]!r}")
    link = presign("GET", _object_url(s, skey), s["access_key"], s["secret_key"], expires=seconds, region=s["region"])
    installer = presign("GET", _object_url(s, f"{s['prefix']}/install.py"), s["access_key"], s["secret_key"],
                        expires=seconds, region=s["region"])
    command = (f"curl -fsSL '{installer}' -o nougen-install.py && "
               f"python3 nougen-install.py install --dir nougen --from '{link}'")
    return {"link": link, "installer": installer, "command": command, "expires": expires_at.isoformat(),
            "share_key": skey, "repos": sorted(links)}


# ------------------------------------------------------------------ tester install
def _fetch(url: str, timeout: float = 600) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "nougen-mesh"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _safe_extract(tf: tarfile.TarFile, dest: Path) -> None:
    root = dest.resolve()
    for m in tf.getmembers():
        target = (dest / m.name).resolve()
        if not str(target).startswith(str(root) + os.sep) and target != root:
            raise R2Error(f"unsafe path in tarball: {m.name}")
        if m.issym() or m.islnk():
            link = (target.parent / m.linkname).resolve()
            if not str(link).startswith(str(root) + os.sep):
                raise R2Error(f"unsafe link in tarball: {m.name}")
    try:
        tf.extractall(dest, filter="data")  # also refuses device files and absolute paths
    except TypeError:  # Python without extraction filters; every member was checked above
        tf.extractall(dest)  # noqa: S202


def install_from(link: str, dest: str, *, only: Optional[List[str]] = None, force: bool = False) -> Dict[str, Any]:
    """Download the share file at ``link``, then each tarball; verify sha256; unpack side by side."""
    doc = json.loads(_fetch(link, 60))
    if doc.get("schema") != SCHEMA:
        raise R2Error("that link is not a NouGen package share")
    root = Path(dest).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    out: Dict[str, Any] = {}
    for name, row in sorted(doc["repos"].items()):
        if only and name not in only:
            continue
        folder = root / row["folder"]
        if folder.exists() and not force:
            out[name] = {"state": "present", "path": str(folder)}
            continue
        data = _fetch(row["url"])
        if _h(data) != row["sha256"]:
            out[name] = {"state": "checksum_mismatch"}
            continue
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            _safe_extract(tf, root)
        (folder / ".nougen-dist.json").write_text(json.dumps(
            {"commit": row["commit"], "sha256": row["sha256"], "committed": row["committed"]}) + "\n", encoding="utf-8")
        out[name] = {"state": "installed", "path": str(folder), "commit": row["commit"][:12]}
    return {"expires": doc.get("expires"), "repos": out}


# ------------------------------------------------------------------ sync (cron / launchd)
def sync(repos_dir: Optional[str] = None, *, pull: bool = True, dry_run: bool = False,
         near: Optional[str] = None) -> Dict[str, Any]:
    """Fetch each package repo, pack its remote default branch, and publish what changed.

    Working trees are left alone: only ``git fetch`` runs, so a box with a
    feature branch checked out still ships the default branch.
    """
    mesh = _mesh()
    if repos_dir:
        os.environ["NOUGEN_REPOS_DIR"] = str(Path(repos_dir).expanduser())
    pulled: Dict[str, str] = {}
    if pull:
        for name in mesh.REPOS:
            d = mesh.repo_dir(name, near)
            if d is None:
                continue
            r = subprocess.run(["git", "-C", str(d), "fetch", "-q", "origin"], capture_output=True, text=True)
            pulled[name] = "ok" if r.returncode == 0 else (r.stderr or r.stdout).strip()[-200:]
    with tempfile.TemporaryDirectory(prefix="nougen-dist-") as tmp:
        packed = pack(None, tmp, ref="default", near=near)
        if packed["refused"]:
            return {"ok": False, "pulled": pulled, "refused": packed["refused"], "uploaded": []}
        res = publish(tmp, dry_run=dry_run)
    return {"ok": True, "pulled": pulled, "missing": packed["missing"], **res}


# ------------------------------------------------------------------ CLI
VERBS = ("pack", "publish", "share", "sync")


def main(argv: Optional[List[str]] = None) -> int:
    import argparse  # noqa: PLC0415

    ap = argparse.ArgumentParser(prog="nougen mesh", description="Ship the tester package through Cloudflare R2.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack", help="tarball each package repo, scan for keys, write the manifest")
    p.add_argument("--repos", help="folder holding the package repos side by side")
    p.add_argument("--out", help="dist folder (default: ~/.nougen/dist)")
    p.add_argument("--ref", default="HEAD", help="git ref to pack, or 'default' for each remote default branch")
    p.add_argument("--only", nargs="*")
    u = sub.add_parser("publish", help="upload the packed dist to R2")
    u.add_argument("--dist")
    u.add_argument("--dry-run", action="store_true")
    s = sub.add_parser("share", help="one expiring download link for a tester")
    s.add_argument("--days", type=float, default=7)
    y = sub.add_parser("sync", help="fetch, pack the default branches, publish; for cron or launchd")
    y.add_argument("--repos")
    y.add_argument("--no-fetch", action="store_true")
    y.add_argument("--dry-run", action="store_true")
    i = sub.add_parser("install", help="tester side: install the package from a share link")
    i.add_argument("--from", dest="link", required=True)
    i.add_argument("--dir", default=".")
    i.add_argument("--only", nargs="*")
    i.add_argument("--force", action="store_true")
    ns = ap.parse_args(argv)
    try:
        if ns.cmd == "pack":
            out: Any = pack(ns.repos, ns.out, only=ns.only, ref=ns.ref)
        elif ns.cmd == "publish":
            out = publish(ns.dist, dry_run=ns.dry_run)
        elif ns.cmd == "share":
            out = share(days=ns.days)
        elif ns.cmd == "sync":
            out = sync(ns.repos, pull=not ns.no_fetch, dry_run=ns.dry_run)
        else:
            out = install_from(ns.link, ns.dir, only=ns.only, force=ns.force)
    except (R2ConfigError, R2Error, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps(out, indent=2, default=str))
    return 0 if out.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
