#!/bin/sh
# NGS M1 gate (bake-off rule 4) plus this entry's own tests. Run from engine/ngs.
set -eu
CC=${CC:-cc}
W="-std=c11 -Wall -Wextra -pedantic -Werror"
T=${TMPDIR:-/tmp}/ngs-gate.$$; mkdir -p "$T"; trap 'rm -rf "$T"' EXIT
echo "1. header byte-identical to PR 1199 head 685901aa (sha256 pinned)"
echo "$(cat check/ngs.h.sha256)  include/ngs.h" | shasum -a 256 -c -
echo "2. check/ngs_header_check.c (C11, C17, C++11)"
$CC $W -Iinclude check/ngs_header_check.c -o "$T/hc" && "$T/hc"
$CC -std=c17 -Wall -Wextra -pedantic -Werror -Iinclude -fsyntax-only check/ngs_header_check.c
printf '#include "ngs.h"\nint main(void) { return ngs_time_sub_sat(1, 0) == 1 ? 0 : 1; }\n' | c++ -std=c++11 -Wall -Wextra -pedantic -Werror -x c++ -Iinclude -fsyntax-only -
echo "3. core sources, C11 and C17, warnings as errors"
for f in src/*.c; do $CC $W -Iinclude -c "$f" -o "$T/$(basename "$f").o"; $CC -std=c17 -Wall -Wextra -pedantic -Werror -Iinclude -fsyntax-only "$f"; done
echo "4. forbidden includes outside the platform layer"
if grep -nE '#include <(unistd|windows|locale|signal|setjmp|ctype|wchar|fenv|tgmath|complex)\.h>' src/crypto.c src/cbor.c src/log.c src/ngs_internal.h; then echo "forbidden include"; exit 1; fi
echo "5. amalgamation builds alone"
python3 tool/amalgamate.py
cmp -s dist/ngs.h include/ngs.h
(cd dist && $CC $W -c nougenshards.c -o "$T/amal.o")
echo "6. crypto against independent oracles"
$CC $W -O2 -Iinclude test/crypto_vec.c src/crypto.c src/plat_posix.c -o "$T/cv"
python3 test/crypto_oracle.py "$T/cv"
echo "7. M1 tests with ASan + UBSan (API, misuse, bit flips, live corruption, threads, crash suite)"
$CC $W -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all -Iinclude test/test_ngs.c src/log.c src/cbor.c src/crypto.c src/plat_posix.c -lpthread -o "$T/t"
"$T/t" 2>/dev/null
echo "8. the same tests against the amalgamation, real filesystem smoke"
$CC $W -O2 -Idist -Iinclude test/smoke_posix.c dist/nougenshards.c -lpthread -o "$T/s"
"$T/s" "$T/db"
echo "GATE GREEN"
