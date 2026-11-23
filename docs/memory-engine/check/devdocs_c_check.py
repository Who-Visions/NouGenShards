#!/usr/bin/env python3
"""Check the NGS C dependency list against the offline devdocs C reference.

Reference: https://devdocs.io/c/ (cppreference-derived). Download once for
offline use (two files, about 5 MB):

    mkdir devdocs-c && cd devdocs-c
    curl -sSLO https://documents.devdocs.io/c/index.json
    curl -sSLO https://documents.devdocs.io/c/db.json

Run:  python devdocs_c_check.py <devdocs-c-dir>      (exit 1 on any FAIL)

The table below is the single source for "which libc calls and headers the
engine may use" (SPEC.md section 13). Policies:

  ALLOW  ISO C11 baseline; the engine core may call it.
  GUARD  ISO C11 but optional (__STDC_NO_ATOMICS__ / __STDC_NO_THREADS__); use only
         behind the platform layer shim, with a fallback.
  PLAT   not usable as ISO C for this engine; the platform layer provides it.
  AVOID  standard but unsuitable (unstable, locale-dependent, optional Annex K, C23).

FAIL means: the page is missing from the reference, the header is not the one
we list, or an ALLOW/GUARD entry is tagged "since C23" (outside the pinned baseline).
"""
import json
import os
import re
import sys

ALLOW, GUARD, PLAT, AVOID = "ALLOW", "GUARD", "PLAT", "AVOID"

# (header, identifier, policy, note)
TABLE = [
    ("stddef.h", "size_t", ALLOW, "sizes and counts in memory only; never on disk"),
    ("stddef.h", "offsetof", ALLOW, "layout checks"),
    ("stddef.h", "max_align_t", AVOID, "C11, but MSVC does not declare it (checked, C11 and C++14); the engine uses NGS_ALIGN_MAX = 16"),
    ("stdalign.h", "alignas", ALLOW, "C11 macro form; the keyword form is C23"),
    ("stdalign.h", "alignof", ALLOW, "C11 macro form"),
    ("assert.h", "static_assert", ALLOW, "C11 macro; C++ and C99 get a fallback in ngs.h"),
    ("string.h", "memcpy", ALLOW, "the only way to read or write unaligned or typed bytes"),
    ("string.h", "memmove", ALLOW, ""),
    ("string.h", "memcmp", ALLOW, "not constant-time: never compare secrets or MACs with it"),
    ("string.h", "memset", ALLOW, "not for wiping secrets (may be optimised away)"),
    ("string.h", "strlen", ALLOW, "only on strings the engine itself NUL-terminated"),
    ("stdlib.h", "malloc", ALLOW, "through the engine allocator hook"),
    ("stdlib.h", "calloc", ALLOW, "preferred: overflow-checked multiply"),
    ("stdlib.h", "realloc", ALLOW, ""),
    ("stdlib.h", "free", ALLOW, ""),
    ("stdlib.h", "abort", ALLOW, "only on internal invariant failure"),
    ("stdlib.h", "bsearch", ALLOW, "deterministic"),
    ("stdlib.h", "qsort", AVOID, "unstable; equal elements get an unspecified order, so ranking would differ by libc; use the engine's own stable sort"),
    ("stdlib.h", "aligned_alloc", PLAT, "C11, but not provided by MSVC; platform layer wraps _aligned_malloc / posix_memalign"),
    ("stdlib.h", "rand", AVOID, "not a CSPRNG; key generation goes through the platform layer"),
    ("stdlib.h", "srand", AVOID, "global state"),
    ("math.h", "expf", ALLOW, "C99"),
    ("math.h", "exp2f", ALLOW, "C99; decay 2^(-dt/half_life)"),
    ("math.h", "logf", ALLOW, "C99"),
    ("math.h", "sqrtf", ALLOW, "C99; correctly rounded, so reproducible"),
    ("math.h", "fabsf", ALLOW, "C99"),
    ("math.h", "ceilf", ALLOW, "C99"),
    ("math.h", "isfinite", ALLOW, "C99 macro; reject NaN or infinite inputs at the API boundary"),
    ("math.h", "isnan", ALLOW, "C99 macro"),
    ("math.h", "fmaf", AVOID, "same result on every platform only if used explicitly; implicit contraction must be off"),
    ("time.h", "timespec_get", ALLOW, "C11; the wall clock (TIME_UTC) for t_record"),
    ("time.h", "time", AVOID, "whole seconds; epoch not guaranteed by ISO C"),
    ("time.h", "clock", AVOID, "CPU time, not wall time"),
    ("time.h", "localtime", AVOID, "locale and zone dependent; not thread-safe"),
    ("stdio.h", "snprintf", ALLOW, "C99; bounded error text only, never for floats on disk"),
    ("stdio.h", "fopen", PLAT, "no durability, ANSI paths on Windows, no positional I/O"),
    ("stdio.h", "fwrite", PLAT, "buffered; see fopen"),
    ("stdio.h", "fflush", PLAT, "flushes the C buffer only; it is not fsync"),
    ("stdio.h", "fseek", PLAT, "offset is long: 32 bits on 64-bit Windows"),
    ("stdio.h", "ftell", PLAT, "offset is long: 32 bits on 64-bit Windows"),
    ("stdio.h", "printf", AVOID, "global stdout; the engine never prints"),
    ("locale.h", "setlocale", AVOID, "global state; changes decimal separator for strtod and printf"),
    ("stdatomic.h", "atomic_load", GUARD, "optional: __STDC_NO_ATOMICS__; MSVC needs /experimental:c11atomics"),
    ("stdatomic.h", "atomic_store", GUARD, ""),
    ("stdatomic.h", "atomic_fetch_add", GUARD, ""),
    ("stdatomic.h", "atomic_compare_exchange_strong", GUARD, ""),
    ("stdatomic.h", "atomic_thread_fence", GUARD, ""),
    ("threads.h", "thrd_create", GUARD, "optional: __STDC_NO_THREADS__; not shipped by every libc"),
    ("threads.h", "thrd_join", GUARD, ""),
    ("threads.h", "mtx_init", GUARD, ""),
    ("threads.h", "mtx_lock", GUARD, ""),
    ("threads.h", "cnd_wait", GUARD, ""),
    ("threads.h", "call_once", GUARD, ""),
    ("string.h", "memset_s", AVOID, "Annex K is optional (__STDC_LIB_EXT1__) and absent from MSVC and glibc; wipe via the platform layer"),
    ("string.h", "memset_explicit", AVOID, "C23; outside the pinned baseline"),
    ("string.h", "strtok", AVOID, "global state"),
    ("errno.h", "errno", GUARD, "only inside platform glue, read right after the failing call"),
]

# Headers the engine core may include (all but the first group are hosted-library headers).
HEADER_PAGES = {
    "stddef.h": "header/stddef", "stdint.h": "header/stdint", "limits.h": "header/limits",
    "float.h": "header/float", "stdalign.h": "header/stdalign", "assert.h": "header/assert",
    "string.h": "header/string", "stdlib.h": "header/stdlib", "math.h": "header/math",
    "time.h": "header/time", "stdio.h": "header/stdio", "stdatomic.h": "header/stdatomic",
    "threads.h": "header/threads", "inttypes.h": "header/inttypes", "errno.h": "header/errno",
    "locale.h": "header/locale",
}

# The C11 spelling of these is a macro on the header page; the keyword page documents the C23 form.
PAGE_OVERRIDE = {"alignas": "header/stdalign", "alignof": "header/stdalign"}

TAG = re.compile(r"\((since|until) (C\d\d)\)")


def load(d):
    with open(os.path.join(d, "index.json"), encoding="utf8") as f:
        idx = json.load(f)
    with open(os.path.join(d, "db.json"), encoding="utf8") as f:
        db = json.load(f)
    by = {}
    for e in idx["entries"]:
        for n in [e["name"]] + [p.strip() for p in e["name"].split(",")]:
            by.setdefault(n, []).append(e)
    return by, db


def text_of(html):
    t = re.sub(r"<[^>]+>", " ", html)
    t = t.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return re.sub(r"\s+", " ", t)


def find_page(by, db, ident):
    if ident in PAGE_OVERRIDE and PAGE_OVERRIDE[ident] in db:
        return PAGE_OVERRIDE[ident], text_of(db[PAGE_OVERRIDE[ident]])
    for e in by.get(ident, []):
        p = e["path"]
        if p in db and not p.startswith("keyword/"):
            return p, text_of(db[p])
    for e in by.get(ident, []):
        if e["path"] in db:
            return e["path"], text_of(db[e["path"]])
    return None, ""


def marker_for(text, ident):
    """Version tags that follow the synopsis line mentioning ident."""
    m = re.search(r"(?:#define\s+)?[\w\s\*,]*\b" + re.escape(ident) + r"\b[^;]{0,200}?;?(.{0,140})", text)
    if not m:
        return ""
    tags = TAG.findall(m.group(0))
    return ",".join(f"{a} {b}" for a, b in tags[:3])


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    by, db = load(argv[1])
    fails = 0
    print(f"{'header':<12}{'identifier':<34}{'policy':<7}{'page':<34}{'tags':<20}status")
    for header, ident, policy, note in TABLE:
        page, text = find_page(by, db, ident)
        status = "ok"
        row_fails = fails
        if page is None:
            status, fails = "FAIL: not in reference", fails + 1
        elif f"<{header}>" not in text:
            status, fails = f"FAIL: header <{header}> not on page", fails + 1
        tags = marker_for(text, ident) if page and ident not in PAGE_OVERRIDE else ""
        if page and ident in PAGE_OVERRIDE and ident not in text:
            status, fails = "FAIL: macro not on header page", fails + 1
        if policy in (ALLOW, GUARD) and ("since C23" in tags or "since C2x" in tags):
            status, fails = "FAIL: C23 only", fails + 1
        if fails > row_fails + 1:
            fails = row_fails + 1
        print(f"{header:<12}{ident:<34}{policy:<7}{(page or '-'):<34}{tags:<20}{status}")
    print()
    for header, path in HEADER_PAGES.items():
        ok = path in db
        if not ok:
            fails += 1
        print(f"header page <{header:<12}> {path:<18} {'ok' if ok else 'FAIL: missing'}")
    # Exact-width types are optional in ISO C: the page must say so.
    fw = text_of(db.get("types/integer", ""))
    print("fixed-width page mentions optional exact-width types:", "optional" in fw)
    print(f"\n{fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
