/*
** ngs_header_check.c -- compile and run check for ngs.h. Not part of the engine.
** A seed for the conformance harness (SPEC 13, "Next"): it covers only what the C
** standard pass changed or asserted. Black-box API contract tests belong to the harness.
**
** Build (all must be warning-free):
**   gcc / clang:  cc -std=c11 -Wall -Wextra -pedantic -Werror -I.. ngs_header_check.c
**   same, C17:    cc -std=c17 -Wall -Wextra -pedantic -Werror -I.. ngs_header_check.c
**   as C++:       c++ -std=c++11 -Wall -Wextra -pedantic -Werror -I.. -x c++ ngs_header_check.c
**   MSVC:         cl /std:c11 /W4 /WX /permissive- /I.. ngs_header_check.c
**   32-bit MSVC:  same from the x86 developer prompt (checks size_t and pointer widths)
**
** Run:  ngs_header_check            -> exit 0 if every check passes
**       ngs_header_check layout     -> also print sizes and offsets of the public structs
*/
#include "ngs.h"

#include <stdio.h>
#include <string.h>

/* Layout facts that must hold on 32-bit and 64-bit targets alike. */
NGS_STATIC_ASSERT(sizeof(int32_t) == 4, "stored flags and kinds are 32-bit");
NGS_STATIC_ASSERT(NGS_MAX_DIM <= 65535u, "dim fits a 16-bit length class");
NGS_STATIC_ASSERT(sizeof(((ngs_hit *)0)->arm) / sizeof(float) == NGS_N_ARMS, "arm[] has one slot per arm");
NGS_STATIC_ASSERT(sizeof(ngs_quarantine_entry) == 32 + 4 + 120, "quarantine entries are fixed-width");

static int failures;
/* A function, not an if-macro: several checks are compile-time constants and
** MSVC /W4 warns (C4127) on a constant condition inside the macro. */
static void check(int ok, int line, const char *expr) {
  if (!ok) { printf("FAIL line %d: %s\n", line, expr); failures++; }
}
#define CHECK(c) check((c) ? 1 : 0, __LINE__, #c)

int main(int argc, char **argv) {
  ngs_open_opts o = NGS_OPEN_OPTS_INIT;
  ngs_fact_in f = NGS_FACT_IN_INIT;
  ngs_query q = NGS_QUERY_INIT;
  ngs_scan_opts sc = NGS_SCAN_OPTS_INIT;
  ngs_stats_t st = NGS_STATS_INIT;
  ngs_fact_in z;
  ngs_time a;

  /* ngs_time_sub_sat: no signed overflow at either end, exact in the middle. */
  CHECK(ngs_time_sub_sat(10, 3) == 7);
  CHECK(ngs_time_sub_sat(-5, 5) == -10);
  CHECK(ngs_time_sub_sat(INT64_MAX, -1) == INT64_MAX);
  CHECK(ngs_time_sub_sat(INT64_MAX, INT64_MIN) == INT64_MAX);
  CHECK(ngs_time_sub_sat(INT64_MIN, 1) == INT64_MIN);
  CHECK(ngs_time_sub_sat(NGS_TIME_NOW, NGS_TIME_MAX) == INT64_MIN);
  CHECK(ngs_time_sub_sat(INT64_MIN, INT64_MIN) == 0);
  CHECK(ngs_time_sub_sat(INT64_MAX, INT64_MAX) == 0);
  CHECK(ngs_time_sub_sat(0, INT64_MIN) == INT64_MAX);
  a = 1700000000000000;
  CHECK(ngs_time_sub_sat(a + 50, a) == 50);

  /* Sentinels are distinct, and kind and arm masks do not collide. */
  CHECK(NGS_TIME_MIN < NGS_TIME_NOW && NGS_TIME_NOW < 0 && NGS_TIME_MAX > 0);
  CHECK(NGS_KIND_BIT(NGS_EPISODIC) == 2u && NGS_KIND_BIT(NGS_SEMANTIC) == 4u && NGS_KIND_BIT(NGS_PROCEDURAL) == 8u);
  CHECK(NGS_ARM_LINK + 1 == NGS_N_ARMS);

  /* The INIT macros: size first, and the non-zero defaults the zero struct would lose. */
  CHECK(o.size == sizeof o && o.flags == NGS_OPEN_READWRITE);
  CHECK(f.size == sizeof f && f.t_event == NGS_TIME_NOW && f.valid_from == NGS_TIME_NOW && f.salience0 < 0.0f);
  CHECK(q.size == sizeof q && q.since == NGS_TIME_MIN && q.until == NGS_TIME_MAX && q.min_confidence < 0.0f);
  CHECK(q.k == 0 && q.deadline_ms == 0 && q.kinds == 0 && q.vec == NULL && q.weights == NULL);
  CHECK(sc.size == sizeof sc && sc.since == NGS_TIME_MIN && sc.until == NGS_TIME_MAX);
  CHECK(st.size == sizeof st && st.facts == 0 && st.timeouts == 0);

  /* A memset struct is not a defaulted one: this is why the INIT macros exist. */
  memset(&z, 0, sizeof z);
  CHECK(z.t_event != NGS_TIME_NOW && z.salience0 == 0.0f && z.size == 0);

  if (argc > 1 && strcmp(argv[1], "layout") == 0) {
    printf("sizeof: size_t=%u ptr=%u ngs_str=%u ngs_vec=%u ngs_open_opts=%u ngs_fact_in=%u ngs_fact=%u\n",
           (unsigned)sizeof(size_t), (unsigned)sizeof(void *), (unsigned)sizeof(ngs_str), (unsigned)sizeof(ngs_vec),
           (unsigned)sizeof(ngs_open_opts), (unsigned)sizeof(ngs_fact_in), (unsigned)sizeof(ngs_fact));
    printf("sizeof: ngs_query=%u ngs_hit=%u ngs_results=%u ngs_head=%u ngs_sync_report=%u ngs_stats_t=%u ngs_scan_opts=%u\n",
           (unsigned)sizeof(ngs_query), (unsigned)sizeof(ngs_hit), (unsigned)sizeof(ngs_results),
           (unsigned)sizeof(ngs_head), (unsigned)sizeof(ngs_sync_report), (unsigned)sizeof(ngs_stats_t),
           (unsigned)sizeof(ngs_scan_opts));
    printf("offsetof ngs_fact_in: ns=%u kind=%u t_event=%u schema=%u salience0=%u\n",
           (unsigned)offsetof(ngs_fact_in, ns), (unsigned)offsetof(ngs_fact_in, kind), (unsigned)offsetof(ngs_fact_in, t_event),
           (unsigned)offsetof(ngs_fact_in, schema), (unsigned)offsetof(ngs_fact_in, salience0));
    printf("offsetof ngs_query: min_confidence=%u  ngs_hit: arm=%u tokens=%u  ngs_results: tokens_budget=%u\n",
           (unsigned)offsetof(ngs_query, min_confidence), (unsigned)offsetof(ngs_hit, arm), (unsigned)offsetof(ngs_hit, tokens),
           (unsigned)offsetof(ngs_results, tokens_budget));
#ifdef __STDC_VERSION__
    printf("__STDC_VERSION__=%ld\n", (long)__STDC_VERSION__);
#endif
  }

  printf("%s\n", failures ? "FAILED" : "ok");
  return failures ? 1 : 0;
}
