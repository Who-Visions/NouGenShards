#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build, test and gate the NGS M1 engine. Standard library only.

  python build.py build     compile the core and its vendored crypto into build/
  python build.py test      build, then run the test suite (unit, API, crash, torture, ABI, threads)
  python build.py amalgam   write dist/nougenshards.c and dist/ngs.h
  python build.py gate      the full gate: strict compile (C11 and C17), header check, amalgamation, tests

Compiler: $CC if set (may contain arguments, e.g. CC="python -m ziglang cc"), else cc, gcc or clang from
PATH, else `python -m ziglang cc`. Every engine and test file builds with
-std=c11 -Wall -Wextra -pedantic -Werror.
"""
import os
import shlex
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
DIST = os.path.join(HERE, "dist")
WIN = sys.platform.startswith("win") or os.environ.get("NGS_TARGET_WIN") == "1"

CORE = ["log.c", "api.c", "cbor.c", "hash.c", "sign.c", "plat_win32.c", "plat_posix.c"]
B3 = ["blake3.c", "blake3_dispatch.c", "blake3_portable.c"]
B3DEF = ["-DBLAKE3_NO_SSE2", "-DBLAKE3_NO_SSE41", "-DBLAKE3_NO_AVX2", "-DBLAKE3_NO_AVX512", "-DBLAKE3_USE_NEON=0"]
ED = ["fe.c", "ge.c", "keypair.c", "sc.c", "sha512.c", "sign.c", "verify.c"]
STRICT = ["-Wall", "-Wextra", "-pedantic", "-Werror"]


def cc():
    env = os.environ.get("CC")
    if env:
        return shlex.split(env)
    for c in ("cc", "gcc", "clang"):
        if shutil.which(c):
            return [c]
    return [sys.executable, "-m", "ziglang", "cc"]


def run(cmd, **kw):
    r = subprocess.run(cmd, cwd=HERE, **kw)
    if r.returncode != 0:
        sys.exit("FAILED: " + " ".join(shlex.quote(c) for c in cmd))
    return r


def compile_one(src, obj, std, extra=()):
    os.makedirs(os.path.dirname(obj), exist_ok=True)
    run(cc() + ["-std=" + std] + STRICT + ["-O2", "-Iinclude", "-Isrc", "-Itest", "-c", src, "-o", obj] + list(extra))


def libs():
    return ["-lbcrypt"] if WIN else ["-lpthread"]


def objects(std="c11"):
    objs = []
    for f in CORE:
        o = os.path.join(BUILD, "core_" + f + ".o")
        compile_one(os.path.join("src", f), o, std)
        objs.append(o)
    for f in B3:
        o = os.path.join(BUILD, "b3_" + f + ".o")
        compile_one(os.path.join("third_party", "blake3", f), o, std, B3DEF)
        objs.append(o)
    for f in ED:
        o = os.path.join(BUILD, "ed_" + f + ".o")
        compile_one(os.path.join("third_party", "ed25519", f), o, std)
        objs.append(o)
    return objs


def build_tests(std="c11"):
    objs = objects(std)
    out = os.path.join(BUILD, "ngs_test" + (".exe" if WIN else ""))
    srcs = ["test_main.c", "simfs.c"]
    tobjs = []
    for f in srcs:
        o = os.path.join(BUILD, "test_" + f + ".o")
        compile_one(os.path.join("test", f), o, std)
        tobjs.append(o)
    run(cc() + objs + tobjs + ["-o", out] + libs())
    return out


def cmd_build():
    objects()
    print("build ok: %d objects in build/" % len(os.listdir(BUILD)))


def cmd_test(args=()):
    exe = build_tests()
    run([exe] + list(args))


def cmd_amalgam():
    run([sys.executable, os.path.join("tool", "amalgamate.py")])


def amalgam_smoke():
    """The amalgamation must build alone: dist/nougenshards.c + dist/ngs.h and a tiny program."""
    smoke = os.path.join(BUILD, "amalgam_smoke.c")
    os.makedirs(BUILD, exist_ok=True)
    with open(smoke, "w") as fh:
        fh.write('#include "ngs.h"\n#include <stdio.h>\n#include <string.h>\n'
                 'int main(void){ ngs *db=0; ngs_fact_in f=NGS_FACT_IN_INIT; ngs_id id; ngs_fact *g=0; ngs_open_opts o=NGS_OPEN_OPTS_INIT;\n'
                 ' unsigned char seed[32]={7}, pk[32], sk[64]; extern void ngs__keypair(unsigned char*,unsigned char*,const unsigned char*);\n'
                 ' ngs__keypair(pk,sk,seed); o.flags=NGS_OPEN_READWRITE|NGS_OPEN_CREATE; o.node_seckey=sk;\n'
                 ' if(ngs_open("build/amalgam_db",&o,&db)){printf("open failed: %s\\n",ngs_errmsg(db));return 1;}\n'
                 ' f.ns.p="ns"; f.ns.n=2; f.kind=NGS_SEMANTIC; f.title.p="t"; f.title.n=1; f.body.p="hello"; f.body.n=5;\n'
                 ' if(ngs_remember(db,&f,0,&id)){printf("remember failed\\n");return 1;}\n'
                 ' if(ngs_get(db,&id,&g)||g->body.n!=5||memcmp(g->body.p,"hello",5)){printf("get failed\\n");return 1;}\n'
                 ' ngs_free(g); if(ngs_verify(db,0,0)){printf("verify failed\\n");return 1;}\n'
                 ' ngs_close(db); printf("amalgamation smoke ok, version %s\\n",ngs_libversion()); return 0; }\n')
    shutil.rmtree(os.path.join(HERE, "build", "amalgam_db"), ignore_errors=True)
    exe = os.path.join(BUILD, "amalgam_smoke" + (".exe" if WIN else ""))
    run(cc() + ["-std=c11"] + STRICT + ["-O2", "-I" + DIST, os.path.join(DIST, "nougenshards.c"), smoke, "-o", exe] + libs())
    run([exe])


def cmd_gate():
    print("== strict compile: C11 and C17 (-Wall -Wextra -pedantic -Werror) ==")
    for std in ("c11", "c17"):
        shutil.rmtree(BUILD, ignore_errors=True)
        os.makedirs(BUILD)
        objects(std)
        print("  %s: core + vendored crypto compile clean" % std)
    check = os.path.join(HERE, "check", "ngs_header_check.c")
    if os.path.exists(check):
        print("== header check (check/ngs_header_check.c) ==")
        for std in ("c11", "c17"):
            exe = os.path.join(BUILD, "hdrcheck" + (".exe" if WIN else ""))
            run(cc() + ["-std=" + std] + STRICT + ["-Iinclude", check, "-o", exe])
            run([exe])
    else:
        print("== header check skipped: check/ngs_header_check.c is not in this tree ==")
    print("== amalgamation ==")
    cmd_amalgam()
    amalgam_smoke()
    print("== tests (C11) ==")
    shutil.rmtree(BUILD, ignore_errors=True)
    os.makedirs(BUILD)
    cmd_test()
    print("GATE PASSED")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    os.makedirs(BUILD, exist_ok=True)
    if cmd == "build":
        cmd_build()
    elif cmd == "test":
        cmd_test(sys.argv[2:])
    elif cmd == "amalgam":
        cmd_amalgam()
    elif cmd == "gate":
        cmd_gate()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
