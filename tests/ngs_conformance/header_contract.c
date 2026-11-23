/*
** Conformance check for the NGS public header (docs/memory-engine/ngs.h, PR 1199).
** Compile-only: pins every exported signature and the codes/flags bindings rely on,
** so a header change that breaks callers fails here instead of in a binding.
** Engine-independent; links nothing.
*/
#include "ngs.h"

#if defined(__cplusplus)
#define NGS_SA static_assert
#else
#define NGS_SA _Static_assert
#endif

/* result codes are wire values: bindings hard-code them */
NGS_SA(NGS_OK == 0, "NGS_OK");
NGS_SA(NGS_NOTFOUND == 2 && NGS_BUSY == 3 && NGS_CORRUPT == 4, "codes 2-4");
NGS_SA(NGS_TIMEOUT == 8 && NGS_MISUSE == 11 && NGS_ABSTAIN == 12, "codes 8-12");
NGS_SA(NGS_FORMAT == 1, "on-disk format");

/* fixed-size value types */
NGS_SA(sizeof(ngs_id) == 32, "ngs_id is BLAKE3-256");
NGS_SA(sizeof(ngs_pubkey) == 32, "ngs_pubkey is Ed25519");
NGS_SA(sizeof(ngs_time) == 8, "ngs_time is int64 microseconds");
NGS_SA(NGS_TIME_NOW == INT64_MIN, "NGS_TIME_NOW sentinel");

/* memory kinds and the recall kind bitmask (1 << kind) */
NGS_SA(NGS_EPISODIC == 1 && NGS_SEMANTIC == 2 && NGS_PROCEDURAL == 3, "kinds");
NGS_SA(NGS_KIND_ALL == 0, "kind filter all");

/* every exported function, pinned by exact prototype */
/* a redeclaration with a different prototype is a hard compile error */
int ngs_open(const char *, const ngs_open_opts *, NGS **);
int ngs_close(NGS *);
const char * ngs_errmsg(NGS *);
void ngs_free(void *);
int ngs_node_pubkey(NGS *, ngs_pubkey *);
int ngs_remember(NGS *, const ngs_fact_in *, ngs_id *);
int ngs_invalidate(NGS *, const ngs_id *, ngs_str);
int ngs_link(NGS *, const ngs_id *, const ngs_id *, ngs_str, float);
int ngs_redact(NGS *, const ngs_id *, ngs_str);
int ngs_grant(NGS *, ngs_str, const ngs_pubkey *);
int ngs_get(NGS *, const ngs_id *, ngs_fact **);
int ngs_recall(NGS *, const ngs_query *, ngs_results **);
int ngs_as_of(NGS *, ngs_time, ngs_time, const ngs_query *, ngs_results **);
int ngs_mark(NGS *, const ngs_id *, ngs_mark_kind);
int ngs_checkpoint(NGS *, uint8_t **, size_t *);
int ngs_verify(NGS *, const uint8_t *, size_t);
int ngs_rebuild(NGS *);
int ngs_heads(NGS *, ngs_head **, size_t *);
int ngs_sync_export(NGS *, const ngs_head *, size_t, uint8_t **, size_t *);
int ngs_sync_import(NGS *, const uint8_t *, size_t, ngs_sync_report *);
int ngs_stats(NGS *, ngs_stats_t *);

/* score arms: vec, kw, recency, salience, link */
NGS_SA(sizeof(((ngs_hit *)0)->arm) / sizeof(float) == 5, "five recall arms");
