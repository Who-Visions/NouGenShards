# NGS C audit: `ngs.h` and SPEC against the C reference

Applies to: `ngs.h` draft 0.3.1 (0.3.0 plus this pass), SPEC.md draft 0.3.1, PR 1199.
Author: WhoArt claude-app, Sun 2026-11-22. Draft 0.3.0 (the Phoebus review resolutions) landed while this audit was
under way; the audit was redone against it. What 0.3.0 already fixed is marked "0.3.0" below, what this pass added is
marked "0.3.1".

Reference: devdocs C, <https://devdocs.io/c/> (cppreference-derived). The offline copy used is `index.json` +
`db.json` from `https://documents.devdocs.io/c/` (db.json 5,128,537 bytes, fetched 2026-11-22). That snapshot also
documents **C23** on the same pages ("since C23"), so a function being on devdocs does not mean it is in C11. The
checker flags those.

## 0. What was and was not run

| check | result |
|---|---|
| `check/devdocs_c_check.py` against the offline devdocs C (every libc call and header in SPEC section 14) | 0 failures |
| `check/ngs_header_check.c`, MSVC 19.44 x64, `/std:c11 /W4 /WX /permissive-` | clean, ok |
| same, `/std:c17` | clean, ok |
| same, as C++14 (`/TP`: `extern "C"`, the inline function and the `*_INIT` initializers) | clean, ok |
| same, 32-bit x86, `/std:c11` | clean, ok (sizes in section 3) |
| same, with `__STDC_VERSION__` undefined (the C99 negative-array fallback of `NGS_STATIC_ASSERT`) | clean, ok |
| a deliberately false `NGS_STATIC_ASSERT` | fails to compile (C2338), as it must |
| **gcc / clang with `-std=c11 -Wall -Wextra -pedantic`** | **NOT RUN.** This box has no gcc or clang (WSL has only the docker-desktop distro; the Visual Studio Llvm folder has clang-tidy and clang-format, not the compiler). MSVC has no `-pedantic`; `/W4 /WX /permissive-` is the nearest. Phoebus ran `cc -fsyntax-only -std=c11 -Wall -Wextra -pedantic` (Apple clang, x86_64) on draft 0.2 and reported it clean; 0.3.1 needs the same run on a gcc or clang box. The `*_INIT` macros in particular should be tried with `-Wextra -Werror` there, since gcc warns on partly initialised structs (the macros are now fully initialised for that reason). |

## 1. Pinned standard

ISO C11 (ISO/IEC 9899:2011). C17 (9899:2018) defect fixes allowed. Nothing newer. SPEC section 14 has the allowed
header list; it is generated from `check/devdocs_c_check.py`, and section 15 is the platform layer.

## 2. Facts measured on this box (MSVC 19.44, x64 unless noted)

| fact | consequence for NGS |
|---|---|
| `__STDC_VERSION__` is 201112 under `/std:c11`, 201710 under `/std:c17` | the `NGS_STATIC_ASSERT` switch works |
| `__STDC_NO_ATOMICS__` **is defined**; `#include <stdatomic.h>` is `#error "C atomic support is not enabled"` unless `/experimental:c11atomics` | atomics need the shim or that flag; never `#include <stdatomic.h>` unguarded |
| `<threads.h>` compiles and `mtx_init` works in this MSVC | usable here, but not a portable assumption: keep the pthread and Win32 backends |
| `__STDC_NO_VLA__` is defined | no VLAs, anywhere |
| `__STDC_IEC_559__` is **not** defined, yet `float` is binary32 (`FLT_RADIX 2`, `FLT_MANT_DIG 24`, `FLT_MAX_EXP 128`) | do not gate on `__STDC_IEC_559__`; assert the `<float.h>` values (done in `ngs.h`) |
| `FLT_EVAL_METHOD` is 0 on x64 | no x87 excess precision on this target; still not assumed elsewhere |
| `__STDC_LIB_EXT1__` is not defined | no Annex K (`memset_s`, `memcpy_s`); wipe secrets in the platform layer |
| `sizeof(long)` is 4, `sizeof(wchar_t)` is 2, `sizeof(size_t)` is 8 | `long` must never carry a size or file offset (also why `fseek` and `ftell` are out); no `wchar_t` in the API |
| `aligned_alloc` is declared but **fails to link** (LNK2019) | the platform layer wraps `_aligned_malloc` / `posix_memalign` |
| `max_align_t` is **not declared** by `<stddef.h>`, in C11 mode or C++14 mode | use `NGS_ALIGN_MAX` (16) from `ngs.h` |
| `_Thread_local` compiles under `/std:c11` | usable for the per-thread `ngs_errmsg` buffer |
| `alignas` / `alignof` via `<stdalign.h>` compile under `/std:c11` | use the macro form (the keyword form is C23) |
| `alignof(expression)` is rejected | `alignof` takes a type name in ISO C; `alignof(object)` is a GNU extension |

## 3. Header audit (`ngs.h`), item by item

| # | finding | status |
|---|---|---|
| 1 | Exact-width types `uint8_t` ... `int64_t` are optional in ISO C (devdocs: Fixed width integer types) | 0.3.1: accepted as required, `CHAR_BIT == 8` asserted; a platform without them fails to compile at the first use |
| 2 | `float` layout was assumed | 0.3.1: `static_assert` on `sizeof`, `FLT_RADIX`, `FLT_MANT_DIG`, `FLT_MAX_EXP`. On-disk and sync floats are written as `uint32_t` bit patterns via `memcpy`, little-endian by explicit shifts |
| 3 | enums as struct members (an enum's type is implementation-defined) | 0.3.0: `int32_t` fields with `#define` values |
| 4 | size field for growing structs, runtime library version, named arms, one-block ownership, borrowed inputs, per-thread `ngs_errmsg`, abstain and timeout as `NGS_OK` plus flags | 0.3.0 (Phoebus review) |
| 5 | `NGS_FACT_IN_INIT` was `{ sizeof(ngs_fact_in) }`: everything else zero, so `t_event = 0` (1970, not "now") and `salience0 = 0` (not "default 0.5"). Measured: `size=176 t_event=0 salience0=0` | 0.3.1: fully initialised, `t_event` and `valid_from` are `NGS_TIME_NOW`, `salience0` is -1; asserted in `ngs_header_check.c` |
| 6 | `NGS_STATS_INIT` was also partly initialised (gcc `-Wextra` warns on that), and `ngs_scan_opts` had no initializer: a zero `since`/`until` is the window [0, 0], not unbounded | 0.3.1: `NGS_STATS_INIT` complete, new `NGS_SCAN_OPTS_INIT` with `NGS_TIME_MIN` / `NGS_TIME_MAX` |
| 7 | `ngs_time` differences: `a - b` overflows (undefined, ISO C 6.5p5) when a sentinel meets a real time | 0.3.1: `ngs_time_sub_sat()`, tested at both ends |
| 8 | `uint32_t dim`: `dim * sizeof(float)` overflows a 32-bit `size_t` for a hostile `dim` | 0.3.1: `NGS_MAX_DIM` (8192, proposed; SPEC open question 7); every `count * size` is overflow-checked (SPEC 14) |
| 9 | `ngs_vec.v` alignment was unstated; a SIMD scan assuming 16 or 32 bytes would fault or misread | 0.3.1: header says float alignment only and the engine copies before any SIMD scan; never read it through a wider pointer |
| 10 | `NaN` or infinity in caller floats breaks z-scores and ordering (every comparison with NaN is false) | 0.3.1: floats must be finite, `NGS_MISUSE` otherwise (header contract "Input") |
| 11 | `ngs_str` with `p == NULL, n > 0` | 0.3.1: stated as `NGS_MISUSE` |
| 12 | Blocks returned "as one allocation" had no alignment guarantee, and `max_align_t` does not exist on MSVC | 0.3.1: `NGS_ALIGN_MAX` (16), "Align" contract |
| 13 | No export macro for shared builds (needed for the Python, Bun and Go bindings on Windows) | 0.3.1: `NGS_API` on every function (`__declspec` on Windows shared builds, `visibility("default")` on gcc and clang) |
| 14 | Flag fields are `int32_t` (signed): shifting into bit 31 is undefined | left as is: every flag is below bit 8 today; use `uint32_t` if a flag ever reaches bit 31 |
| 15 | `ngs_stats_t` ends in `_t` (POSIX reserves such names for itself in its headers) | left: the typedef cannot be `ngs_stats` because that is the function. The `ngs_` prefix avoids a clash in practice |
| 16 | `typedef struct ngs ngs;`: the type name equals the library prefix, so a C++ user with `namespace ngs` collides | left; note for the bindings |
| 17 | `elapsed_us` is `uint32_t`: wraps after about 71 minutes | left: unsigned wrap is defined, and a recall is bounded by its deadline |

Layout (informational: these structs hold pointers or `size_t`, so they differ between 32-bit and 64-bit and must never
be written to disk or sent in a sync segment; the on-disk format uses its own fixed-width encoding). From
`ngs_header_check layout`:

| struct | x64 | x86 |
|---|---|---|
| `ngs_str` | 16 | 8 |
| `ngs_vec` | 32 | 20 |
| `ngs_open_opts` | 48 | 40 |
| `ngs_fact_in` | 176 | 96 |
| `ngs_fact` | 240 | 192 |
| `ngs_query` | 144 | 96 |
| `ngs_hit` | 136 | 108 |
| `ngs_results` | 64 | 48 |
| `ngs_head` | 56 | 48 |
| `ngs_sync_report` | 48 | 40 |
| `ngs_scan_opts` | 56 | 40 |

Structs made only of fixed-width members have the same size on both: `ngs_stats_t` 104, `ngs_quarantine_entry` 156,
`ngs_id` and `ngs_pubkey` 32. These are the ones a binding can mirror without per-platform code. Every struct is
size-first, so the `size` field is what a binding reads, not a compiled-in constant.

## 4. Undefined-behaviour and portability risks for the implementation (not yet written)

| risk | rule |
|---|---|
| signed overflow in time, token or score arithmetic | do it in `uint64_t` or with a checked or saturating helper; `ngs_time_sub_sat` for times |
| `count * size` overflow in allocation (32-bit `size_t`) | checked multiply before every `malloc`; prefer `calloc` |
| type punning for floats and integers | `memcpy`, never a pointer cast (strict aliasing, ISO C 6.5p7); a union is allowed in C but not in C++ |
| unaligned loads of `uint32_t`, `uint64_t` or `float` from log or caller buffers | `memcpy` into a local, or byte shifts |
| endianness | explicit little-endian shifts on disk; ISO C has no endian macro (the `__STDC_ENDIAN_*` macros are C23) |
| `memcmp` on secrets or signatures | constant-time compare in the crypto module |
| `qsort` equal-element order is unspecified, so ranking would differ by libc | own stable sort; ties break by `fact_id` bytes, so recall order is reproducible |
| implicit fused multiply-add changes scores between compilers | `#pragma STDC FP_CONTRACT OFF` in scoring sources; the differential test (SPEC 8) compares scores with a tolerance and ranks exactly |
| `long` for file offsets (`fseek`, `ftell`) | 64-bit offsets through the platform layer only |
| `fflush` mistaken for durability | it only empties the C buffer; durability is `fsync` or `FlushFileBuffers` in the platform layer |
| Windows paths: `fopen` takes the ANSI code page, the API promises UTF-8 | the platform layer converts UTF-8 to UTF-16 and calls the `W` APIs |
| locale: `printf("%f")` and `strtod` follow `setlocale` | no float text formatting or parsing in the core; `setlocale` banned |
| thread-local error text | `_Thread_local` (C11; verified on MSVC) behind a `NGS_THREAD_LOCAL` macro in the platform layer |

## 5. Left for CI or another box (not verified here)

- gcc and clang with `-std=c11 -Wall -Wextra -pedantic -Werror` (section 0), plus `-std=c17`, plus `c++ -std=c++11`.
- arm64 (macOS, Linux): the same commands.
- Whether `<threads.h>` and `<stdatomic.h>` exist on the macOS and Linux CI images. The design does not depend on the answer.
- macOS durability (`fcntl(F_FULLFSYNC)`) and Windows directory-entry durability: measured on hardware in M1.

## 6. Re-run

```
python docs/memory-engine/check/devdocs_c_check.py <dir with devdocs index.json + db.json>
cd docs/memory-engine/check
cl /std:c11 /W4 /WX /permissive- /I.. ngs_header_check.c            # MSVC
cc -std=c11 -Wall -Wextra -pedantic -Werror -I.. ngs_header_check.c   # gcc / clang
./ngs_header_check layout
```
