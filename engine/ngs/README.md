# NGS engine, milestone M1 (whoart entry)

Native C11 implementation of the NouGenShards M1 slice against `include/ngs.h` 0.3.1 (byte-identical to
PR 1199 @ 685901a). Signed, hash-chained, append-only log; recovery that cuts a torn tail; `ngs_verify`;
`ngs_remember`, `ngs_remember_many`, `ngs_get`, `ngs_flush`, `ngs_scan`. Everything else returns `NGS_MISUSE` "not in M1".

    python build.py gate     strict C11/C17 (-Wall -Wextra -pedantic -Werror), header check, amalgamation + smoke, tests
    python build.py test     test suite only (--fast skips the crash harness)
    python build.py amalgam  dist/nougenshards.c + dist/ngs.h

`CC` overrides the compiler (any cc/gcc/clang; falls back to `python -m ziglang cc`). Vendored crypto is pinned
in `third_party/VERSIONS`. Spec notes for M2 are in the PR description.
