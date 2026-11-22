"""Shared code must not carry the owner's fleet as defaults.

Anyone who runs this repo (a tester, a tenant, a new box) has to see their own
machines, lanes and hosts, resolved at runtime from env, node.json or the
endpoints file. A fleet hostname, machine name or lane signature baked into
these modules shows up on someone else's machine as if it were theirs.
Extend MODULES as files are swept.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = [
    "src/nougen_shards/tunnel.py",
    "src/nougen_shards/endpoints.py",
]
FLEET = re.compile(r"nougenai\.com|whoentertains|\bg-dave\b|\bblade\b|\bphoebus\b|\bwhoart\b|superdave", re.I)


def test_swept_modules_carry_no_fleet_defaults():
    hits = []
    for rel in MODULES:
        for n, line in enumerate((ROOT / rel).read_text(encoding="utf-8").splitlines(), 1):
            if FLEET.search(line):
                hits.append(f"{rel}:{n}: {line.strip()}")
    assert not hits, "fleet names baked into shared code; resolve them at runtime:\n" + "\n".join(hits)
