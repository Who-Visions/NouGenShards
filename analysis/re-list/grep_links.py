"""Extract every link from extremecoders-re/re-list and enrich it.

    python analysis/re-list/grep_links.py     # needs an authenticated gh CLI

The README is fetched live at the current re-list commit, and that SHA is recorded.
re-list carries no license, so its text and tool descriptions are not stored: the
output keeps only tool names, URLs, and facts measured here.
GitHub repos get live metadata via one batched GraphQL call per 40 repos.
Other links get an HTTP liveness check (HEAD, falling back to GET), 10 s timeout.
Writes links.json and links.md next to this script; prints a short summary only.
"""
import concurrent.futures as cf
import datetime as dt
import json
import re
import subprocess
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
REPO = "extremecoders-re/re-list"


def fetch_readme() -> tuple[str, str]:
    """(commit sha, README text) for the current re-list HEAD."""
    sha = subprocess.run(["gh", "api", f"repos/{REPO}/commits/HEAD", "--jq", ".sha"],
                         capture_output=True, text=True, timeout=60, check=True).stdout.strip()
    text = subprocess.run(["gh", "api", f"repos/{REPO}/contents/README.md?ref={sha}",
                           "-H", "Accept: application/vnd.github.raw"],
                          capture_output=True, text=True, encoding="utf-8", timeout=60,
                          check=True).stdout
    return sha, text

ITEM = re.compile(r"^\s*-\s*\*\*\[(?P<name>[^\]]+)\]\((?P<url>[^)\s]+)\)\*\*:?\s*(?P<desc>.*)$")
ANY_LINK = re.compile(r"\[([^\]]*)\]\((https?://[^)\s]+)\)")
GH_REPO = re.compile(r"^https?://(?:www\.)?github\.com/([^/\s#?]+)/([^/\s#?]+)")


def parse(text: str) -> list[dict]:
    rows, seen = [], set()
    for line in text.splitlines():
        m = ITEM.match(line)
        if m:
            d = m.groupdict()
            rows.append({"name": d["name"].strip(), "url": d["url"].strip(), "kind": "tool"})
            seen.add(d["url"].strip())
            # extra links inside the description (papers, mirrors, docs); the text itself is not kept
            for label, url in ANY_LINK.findall(d["desc"]):
                if url not in seen:
                    rows.append({"name": f"{d['name'].strip()} -> {label}", "url": url,
                                 "kind": "inline"})
                    seen.add(url)
            continue
        for label, url in ANY_LINK.findall(line):
            if url not in seen:
                rows.append({"name": label, "url": url, "kind": "other"})
                seen.add(url)
    return rows


def gh_meta(repos: list[tuple[str, str]]) -> dict:
    out = {}
    for i in range(0, len(repos), 40):
        chunk = repos[i:i + 40]
        parts = []
        for j, (o, n) in enumerate(chunk):
            n = n.removesuffix(".git")
            parts.append(
                f'r{j}: repository(owner: {json.dumps(o)}, name: {json.dumps(n)}) '
                '{ nameWithOwner stargazerCount isArchived pushedAt url '
                'licenseInfo { spdxId } primaryLanguage { name } }')
        q = "query {" + " ".join(parts) + "}"
        res = subprocess.run(["gh", "api", "graphql", "-f", f"query={q}"],
                             capture_output=True, text=True, timeout=120)
        try:
            data = json.loads(res.stdout).get("data") or {}
        except json.JSONDecodeError:
            data = {}
        for j, key in enumerate(chunk):
            out[key] = data.get(f"r{j}")  # None = renamed away, deleted, or private
    return out


def alive(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (re-list link check)"}
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                return str(r.status)
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405, 400, 501):
                continue
            return str(e.code)
        except Exception as e:  # DNS, TLS, timeout
            if method == "HEAD":
                continue
            return f"ERR {type(e).__name__}"
    return "ERR"


def main() -> None:
    sha, text = fetch_readme()
    checked = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    rows = parse(text)
    gh_keys = []
    for r in rows:
        m = GH_REPO.match(r["url"])
        if m and m.group(1).lower() not in {"topics", "orgs", "sponsors"}:
            r["gh"] = (m.group(1), m.group(2))
            gh_keys.append(r["gh"])
    meta = gh_meta(sorted(set(gh_keys)))
    for r in rows:
        if "gh" in r:
            m = meta.get(r["gh"])
            r["gh"] = "/".join(r["gh"])
            if m:
                r.update(status="github-ok", stars=m["stargazerCount"], archived=m["isArchived"],
                         pushed=m["pushedAt"][:10], license=(m["licenseInfo"] or {}).get("spdxId"),
                         language=(m["primaryLanguage"] or {}).get("name"),
                         canonical=m["nameWithOwner"])
            else:
                r["status"] = "github-missing"
    others = [r for r in rows if "gh" not in r]
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for r, s in zip(others, ex.map(lambda r: alive(r["url"]), others)):
            r["status"] = f"http {s}"

    (HERE / "links.json").write_text(
        json.dumps({"source": REPO, "commit": sha, "checked_utc": checked, "links": rows}, indent=2) + "\n",
        encoding="utf-8")

    def line(r):
        if r.get("status") == "github-ok":
            flag = " **ARCHIVED**" if r["archived"] else ""
            info = f"★{r['stars']} · {r['language'] or '-'} · {r['license'] or 'no license'} · last push {r['pushed']}{flag}"
        else:
            info = r.get("status", "")
        return f"| [{r['name']}]({r['url']}) | {info} |"

    md = ["# re-list: every link, checked live",
          "",
          f"Source: https://github.com/{REPO} at commit `{sha[:12]}`, checked {checked}. "
          "Generated by `grep_links.py`. re-list has no license, so its descriptions are not reproduced; "
          "follow each link for details.",
          "",
          "| Link | Status (stars · language · license · last push) |", "|---|---|"]
    md += [line(r) for r in sorted(rows, key=lambda r: -(r.get("stars") or 0))]
    (HERE / "links.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    ok = [r for r in rows if r.get("status") == "github-ok"]
    print(f"links total={len(rows)} tools={sum(r['kind']=='tool' for r in rows)} "
          f"inline={sum(r['kind']=='inline' for r in rows)} other={sum(r['kind']=='other' for r in rows)}")
    print(f"github repos ok={len(ok)} missing={sum(r.get('status')=='github-missing' for r in rows)} "
          f"archived={sum(r['archived'] for r in ok)} "
          f"stale(no push since 2023)={sum(r['pushed'] < '2023-01-01' for r in ok)}")
    bad = [r for r in others if not r["status"].startswith("http 2") and not r["status"].startswith("http 3")]
    print(f"non-github links={len(others)} dead_or_error={len(bad)}")
    print("top 15 by stars:")
    for r in sorted(ok, key=lambda r: -r["stars"])[:15]:
        print(f"  {r['stars']:>6}  {r['canonical']}  ({r['language']}, {r['license']}, {r['pushed']})")
    print("missing github repos:", ", ".join(r["gh"] for r in rows if r.get("status") == "github-missing") or "none")
    print("dead/error non-github:", "; ".join(f"{r['name']} [{r['status']}]" for r in bad) or "none")


if __name__ == "__main__":
    main()
