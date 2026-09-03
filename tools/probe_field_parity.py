"""Prove a public hostname reaches the origin you think it reaches.

A status code cannot answer that question. On 2026-09-01 phoebus's own tunnel
had been healthy and correctly CNAME'd to ngs.nougenai.com for two weeks while
serving none of that hostname's traffic: Cloudflare Worker routes bound to a
hostname take precedence over its DNS target at the edge, so every request was
answered by blade or the Space instead. Both sides returned 200. Both returned
well-formed JSON of the same shape. Cloudflare's tunnel API called the
connector healthy -- true, and irrelevant, because "the connector is up" and
"traffic arrives here" are different claims.

What exposed it was a FIELD diff of the two /health bodies:

    direct  127.0.0.1:4444    deploy_sha=None    storage=default  persistent=False
    public  ngs.nougenai.com  deploy_sha=5860a5  storage=/data    persistent=True

Same status, same shape, different machine. This probe automates that diff.

Sibling to gateway_probe.py: that one proves an AUTHENTICATED call works, this
one proves WHICH NODE answered. Three states, so a caller never has to infer
one from another:

    MATCH <detail>        exit 0  public and direct report one identity
    MISMATCH <detail>     exit 1  something else is answering the public name
    UNREACHABLE <detail>  exit 3  a side could not be read. NOT a match, and
                                  not proof of a mismatch either.

UNREACHABLE earns its own state for the same reason the other two exist: a
probe that folds "I could not tell" into either verdict rebuilds the false
green it was written to catch.

Usage:
    python tools/probe_field_parity.py --public https://phoebus.nougenai.com \
                                       --direct http://127.0.0.1:4444
"""
import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request

# The three /health fields that differ between any two nodes in this fleet.
# deploy_sha names the code, storage and persistent_storage name the disk --
# a Space answers /data + True, a local node answers default + False.
IDENTITY_FIELDS = ("deploy_sha", "storage", "persistent_storage")

# nougen-shard-failover stamps every response it proxies. Seeing it on the
# public side and not the direct side is independent evidence that a Worker is
# in the path, regardless of whether the identity fields happen to agree.
WORKER_HEADER = "x-nougen-origin"

# Distinguishes "this field is absent here" from "this field is present and
# null" -- deploy_sha is legitimately null on an undeployed node, so the two
# must not compare equal.
ABSENT = "<absent>"

# Cloudflare rejects the default Python-urllib agent with error 1010 on the
# nougenai.com zone, so an unnamed probe reads every public hostname as 403 and
# reports UNREACHABLE forever while curl succeeds from the same shell. Naming
# the tool also leaves an honest trace in the origin's access log.
USER_AGENT = "nougen-probe-field-parity/1.0"


def _ssl_context():
    """Trust store for this interpreter.

    python.org macOS builds do not inherit the system roots, so a bare urllib
    call raises CERTIFICATE_VERIFY_FAILED against hosts `curl` reaches from the
    same shell -- which reads as a network or Cloudflare outage and is neither.
    Prefer certifi's bundle where it is installed; fall back to the default
    context (None) everywhere else.
    """
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def probe(url, timeout=10.0):
    """Read one origin's self-reported identity, or why it could not be read.

    Never raises: an origin that refuses, times out, or answers something other
    than JSON is a result this probe must be able to REPORT, not an exception
    that aborts the comparison and leaves the caller guessing.
    """
    result = {"url": url, "ok": False, "status": None, "fields": {},
              "worker_header": None, "error": None}
    request = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout,
                                    context=_ssl_context()) as response:
            result["status"] = response.status
            result["worker_header"] = response.headers.get(WORKER_HEADER)
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        result["error"] = f"HTTP {result['status']} but body was not JSON"
        return result
    if not isinstance(payload, dict):
        result["error"] = f"HTTP {result['status']} but body was not an object"
        return result

    result["fields"] = {f: payload[f] for f in IDENTITY_FIELDS if f in payload}
    result["ok"] = True
    return result


def compare_identity(public, direct, fields=IDENTITY_FIELDS):
    """Pure verdict over two probe() results -- the testable half, no I/O.

    Returns {"verdict", "differences", "notes"}. differences is a list of
    (field, public_value, direct_value) so a caller can print the evidence
    rather than restate the conclusion.
    """
    notes = []
    for side, result in (("public", public), ("direct", direct)):
        if not result.get("ok"):
            notes.append(f"{side} {result.get('url')}: "
                         f"{result.get('error') or 'unreadable'}")
    if notes:
        return {"verdict": "UNREACHABLE", "differences": [], "notes": notes}

    differences = []
    for field in fields:
        pub = public["fields"].get(field, ABSENT)
        dir_ = direct["fields"].get(field, ABSENT)
        if pub != dir_:
            differences.append((field, pub, dir_))

    if public.get("worker_header") and not direct.get("worker_header"):
        notes.append(
            f"a Worker is in the public path ({WORKER_HEADER}: "
            f"{public['worker_header']}); it answers before the tunnel does")

    verdict = "MISMATCH" if differences else "MATCH"
    if verdict == "MATCH" and notes:
        # Parity through an intermediary is still parity, but the caller should
        # know the identity was vouched for by something other than the origin.
        notes.append("fields agree, but they were relayed, not served direct")
    return {"verdict": verdict, "differences": differences, "notes": notes}


def format_report(public, direct, comparison):
    """One line per fact, every line naming the origin it came from.

    Health claims that do not name their origin are unfalsifiable: two lanes can
    report different health for "the gateway" and both be right, because they
    resolved different gateways.
    """
    lines = []
    verdict = comparison["verdict"]
    if verdict == "MATCH":
        detail = f"{public['url']} and {direct['url']} report one node"
    elif verdict == "MISMATCH":
        detail = (f"{public['url']} is answered by a different node than "
                  f"{direct['url']}")
    else:
        detail = "could not read both origins"
    lines.append(f"{verdict} {detail}")

    for field, pub, dir_ in comparison["differences"]:
        lines.append(f"  {field}: public={pub!r}  direct={dir_!r}")
    for note in comparison["notes"]:
        lines.append(f"  note: {note}")
    return "\n".join(lines)


EXIT_CODES = {"MATCH": 0, "MISMATCH": 1, "UNREACHABLE": 3}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--public", required=True,
                        help="public base URL, e.g. https://phoebus.nougenai.com")
    parser.add_argument("--direct", required=True,
                        help="origin base URL, e.g. http://127.0.0.1:4444")
    parser.add_argument("--path", default="/health",
                        help="path probed on both sides (default: /health)")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--json", action="store_true",
                        help="emit the full comparison as JSON")
    args = parser.parse_args()

    public = probe(args.public.rstrip("/") + args.path, args.timeout)
    direct = probe(args.direct.rstrip("/") + args.path, args.timeout)
    comparison = compare_identity(public, direct)

    if args.json:
        print(json.dumps({"public": public, "direct": direct,
                          "comparison": comparison}, indent=2))
    else:
        print(format_report(public, direct, comparison))
    return EXIT_CODES[comparison["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
