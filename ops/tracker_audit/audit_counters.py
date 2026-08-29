"""Audit which tracker dailies were exported by a stale usage counter.

Leg 20260829T045305Z: OpenAI-usage counting was fixed (fold_openai_usage,
fingerprint cfae0dd41682). Dailies written before that carry an older counter
id, and a mixed cohort is what blocks trustworthy fleet totals -- you cannot
sum numbers produced by two different counting rules.

Reads only; writes a report. Run: python ops/tracker_audit/audit_counters.py
"""
import json
import sys
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

SPACE = "nougenai/NouGenTracker-node"
FIXED = "cfae0dd41682"
API = f"https://huggingface.co/api/spaces/{SPACE}/tree/main/dailies"
RAW = f"https://huggingface.co/spaces/{SPACE}/resolve/main/dailies"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nougen-audit"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode())


def lanes():
    return [e["path"].split("/")[-1] for e in get(API) if e.get("type") == "directory"]


def dates(lane):
    out = []
    for e in get(f"{API}/{lane}"):
        name = e["path"].split("/")[-1]
        if name.endswith(".json"):
            out.append(name[:-5])
    return sorted(out)


def counter_of(item):
    lane, date = item
    try:
        d = get(f"{RAW}/{lane}/{date}.json")
        return lane, date, d.get("counter") or "<absent>", d.get("schema"), None
    except Exception as exc:  # noqa: BLE001 - report, never abort the sweep
        return lane, date, None, None, type(exc).__name__


def main():
    work = []
    for lane in lanes():
        work += [(lane, d) for d in dates(lane)]
    print(f"auditing {len(work)} dailies across {len({w[0] for w in work})} lanes", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(counter_of, work))

    by_counter = defaultdict(list)
    errors = []
    for lane, date, counter, schema, err in rows:
        if err:
            errors.append((lane, date, err))
        else:
            by_counter[(counter, schema)].append((lane, date))

    print("\n=== counter cohorts ===")
    for (counter, schema), items in sorted(by_counter.items(), key=lambda kv: -len(kv[1])):
        mark = "FIXED " if counter == FIXED else "STALE "
        per_lane = defaultdict(list)
        for lane, date in items:
            per_lane[lane].append(date)
        span = f"{min(d for _, d in items)} .. {max(d for _, d in items)}"
        print(f"{mark}counter={counter} schema={schema}  n={len(items)}  {span}")
        for lane in sorted(per_lane):
            ds = sorted(per_lane[lane])
            print(f"    {lane:<10} {len(ds):>3}  {ds[0]} .. {ds[-1]}")

    stale = [(l, d) for (c, _), items in by_counter.items() if c != FIXED for l, d in items]
    print(f"\n=== summary ===\nfixed={sum(len(v) for (c, _), v in by_counter.items() if c == FIXED)} "
          f"stale={len(stale)} unreadable={len(errors)}")
    if errors:
        print("unreadable:", errors[:10])

    out = "ops/tracker_audit/stale_cohort.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"fixed_counter": FIXED,
                   "stale": sorted(stale),
                   "cohorts": {f"{c}|schema{s}": sorted(v) for (c, s), v in by_counter.items()},
                   "errors": errors}, f, indent=2)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
