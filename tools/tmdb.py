"""TMDB lookup via the keymaker. Usage: python tools/tmdb.py search "<title>" [movie|tv] | find <imdb_id> | check
Reads TMDB_READ_ACCESS_TOKEN (v4 Bearer). Never prints the token."""
import json, sys, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nougen_shards import keymaker  # noqa: E402

BASE = "https://api.themoviedb.org/3/"


def call(path, **params):
    token = keymaker.get_secret("TMDB_READ_ACCESS_TOKEN")
    if not token:
        raise SystemExit("TMDB_READ_ACCESS_TOKEN is not in the keymaker")
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmd = argv[1] if len(argv) > 1 else "check"
    if cmd == "check":
        call("configuration"); print("TMDB ok")
    elif cmd == "search":
        kind = argv[3] if len(argv) > 3 else "multi"
        for r in call(f"search/{kind}", query=argv[2])["results"][:8]:
            print(r.get("media_type", kind), r["id"], r.get("title") or r.get("name"), (r.get("release_date") or r.get("first_air_date") or "")[:4])
    elif cmd == "find":
        print(json.dumps(call(f"find/{argv[2]}", external_source="imdb_id"))[:1500])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
