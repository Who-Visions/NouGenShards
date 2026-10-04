"""nougenmsg_latest cursor pagination (fleet MCP worker): RELAY DOWN brief 2026-10-04.

Drives the pure paginator exported via __test__ in tools/nougen-fleet-mcp-patched.js under node,
plus a schema check that MCP clients can actually pass ``cursor``.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "tools" / "nougen-fleet-mcp-patched.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

HARNESS = r"""
const mod = await import(process.argv[1]);
const { paginateLegIds: page, orderLegIds } = mod.__test__;
const H = "a".repeat(40), H2 = "b".repeat(40);
const stamp = (i) => { const d = new Date(Date.UTC(2026, 9, 1) + i * 60000); return d.toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z"; };
const mk = (n, from = 0) => Array.from({ length: n }, (_, k) => `${stamp(from + k)}__node__agent${from + k}`);
function walk(ids, head, limit) {
  const out = []; let cur, pages = 0, last;
  for (;;) { const r = page(ids, head, cur, limit); if (r.error) return { error: r.error };
    out.push(...r.pageIds); pages++; last = r; if (r.complete) break; cur = r.nextCursor; if (pages > 10000) break; }
  return { out, pages, last };
}
const R = {};
// 537 seeded, newest first, unique, complete
const ids537 = orderLegIds(mk(537));
const w = walk(ids537, H, 25);
R.seed = { n: w.out.length, uniq: new Set(w.out).size, ordered: JSON.stringify(w.out) === JSON.stringify(ids537), pages: w.pages, lastNull: w.last.nextCursor === null };
// append 20 newer during paging: continuing the pinned snapshot sees no skip/dup
const snap = orderLegIds(mk(100));
const p1 = page(snap, H, undefined, 25);
const grown = orderLegIds([...mk(100), ...mk(20, 1000)]);  // 20 newer legs land at the front
const rest = []; let c = p1.nextCursor;
for (;;) { const r = page(grown, H, c, 25); rest.push(...r.pageIds); if (r.complete) break; c = r.nextCursor; }
const all = [...p1.pageIds, ...rest];
R.append = { n: all.length, uniq: new Set(all).size, equalsSnapshot: JSON.stringify(all) === JSON.stringify(snap) };
// malformed / stale / foreign cursors fail explicitly
R.bad = page(snap, H, "garbage", 10).error || null;
R.foreignHead = page(snap, H2, p1.nextCursor, 10).error || null;
R.staleId = page(orderLegIds(mk(5, 5000)), H, p1.nextCursor, 10).error || null;
// limit boundaries
R.limits = [1, 25, 100, 500, 0].map((l) => page(snap, H, undefined, l).pageIds.length);
// identical stamps -> deterministic by id
const tie = orderLegIds(["20261001T000000Z__b", "20261001T000000Z__a", "20261001T000000Z__c"]);
R.tie = tie;
// empty store
const e = page([], H, undefined, 25);
R.empty = { complete: e.complete, next: e.nextCursor, n: e.pageIds.length };
// no head sha: never hands out an unsafe cursor
const nh = page(snap, null, undefined, 10);
R.noHead = { complete: nh.complete, next: nh.nextCursor, reason: nh.reason || null };
console.log(JSON.stringify(R));
"""


@pytest.fixture(scope="module")
def results():
    out = subprocess.run(["node", "--input-type=module", "-e", HARNESS, WORKER.as_uri()],
                         capture_output=True, text=True, timeout=120, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_seed_537_walks_completely_newest_first(results):
    r = results["seed"]
    assert r["n"] == 537 and r["uniq"] == 537 and r["ordered"] and r["lastNull"]
    assert r["pages"] == 22  # ceil(537/25)


def test_concurrent_append_no_skip_or_dup(results):
    r = results["append"]
    assert r == {"n": 100, "uniq": 100, "equalsSnapshot": True}


def test_bad_cursors_fail_explicitly(results):
    assert "invalid" in results["bad"]
    assert "snapshot" in results["foreignHead"]
    assert "not in its snapshot" in results["staleId"]


def test_limit_boundaries(results):
    assert results["limits"] == [1, 25, 100, 100, 1]


def test_identical_stamps_resolve_by_id(results):
    assert results["tie"] == ["20261001T000000Z__c", "20261001T000000Z__b", "20261001T000000Z__a"]


def test_empty_store(results):
    assert results["empty"] == {"complete": True, "next": None, "n": 0}


def test_missing_head_never_claims_complete(results):
    assert results["noHead"]["complete"] is False and results["noHead"]["next"] is None
    assert results["noHead"]["reason"]


def test_mcp_schema_exposes_cursor():
    src = WORKER.read_text(encoding="utf-8")
    i = src.index('name: "nougenmsg_latest"')
    block = src[i:i + 1200]
    assert "cursor: { type: \"string\"" in block
    assert "maximum: 100" in block
