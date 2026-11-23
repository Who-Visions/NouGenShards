/*
** Conformance pins for the NGS public header (docs/memory-engine/ngs.h).
** Target: PR 1199 draft 0.3.1, commit 685901a.
**
** Complements the PR's own check/ngs_header_check.c (layouts, *_INIT macros,
** time helpers). This file pins what that one does not: result-code wire
** values and the exact prototype of every exported function. A redeclaration
** with a different prototype is a hard error in C, so any signature drift in
** ngs.h fails here before it breaks a binding. Compile-only; links nothing.
*/
#include "ngs.h"

#if defined(__cplusplus)
#define PIN_SA static_assert
#else
#define PIN_SA _Static_assert
#endif

/* result codes are wire values: bindings hard-code them */
PIN_SA(NGS_OK == 0 && NGS_ERROR == 1 && NGS_NOTFOUND == 2 && NGS_BUSY == 3, "codes 0-3");
PIN_SA(NGS_CORRUPT == 4 && NGS_NOGRANT == 5 && NGS_MISMATCH == 6 && NGS_QUARANTINED == 7, "codes 4-7");
PIN_SA(NGS_NOMEM == 9 && NGS_IOERR == 10 && NGS_MISUSE == 11 && NGS_TOOBIG == 12, "codes 9-12");
PIN_SA(NGS_FORMAT == 1, "on-disk format");
PIN_SA(NGS_EPISODIC == 1 && NGS_SEMANTIC == 2 && NGS_PROCEDURAL == 3, "kinds");
PIN_SA(NGS_FUSE_ZSCORE == 0 && NGS_FUSE_RRF == 1, "fusion");
PIN_SA(NGS_MARK_NOT_USED == 0 && NGS_MARK_USED == 1, "marks");
PIN_SA(sizeof(ngs_id) == 32 && sizeof(ngs_pubkey) == 32 && sizeof(ngs_time) == 8, "value types");

/* every exported function, pinned by exact prototype */
int ngs_libversion_number(void); 
const char *ngs_libversion(void);
const char *ngs_errstr(int rc);
int ngs_open(const char *dir, const ngs_open_opts *opts, ngs **out);
int ngs_close(ngs *db);
const char *ngs_errmsg(ngs *db);
void ngs_free(void *p);
int ngs_node_pubkey(ngs *db, ngs_pubkey *out);
int ngs_flush(ngs *db); 
int ngs_remember(ngs *db, const ngs_fact_in *in, int32_t flags, ngs_id *out_id);
int ngs_remember_many(ngs *db, const ngs_fact_in *in, size_t n, int32_t flags, ngs_id *out_ids );
int ngs_invalidate(ngs *db, const ngs_id *id, ngs_str reason);
int ngs_link(ngs *db, const ngs_id *a, const ngs_id *b, ngs_str rel, float weight, ngs_id *out_link_id);
int ngs_redact(ngs *db, const ngs_id *id, ngs_str reason);
int ngs_grant(ngs *db, ngs_str ns, const ngs_pubkey *writer, ngs_id *out_grant_id);
int ngs_get(ngs *db, const ngs_id *id, ngs_fact **out); 
int ngs_recall(ngs *db, const ngs_query *q, ngs_results **out);
int ngs_as_of(ngs *db, ngs_time t_valid, ngs_time t_record, const ngs_query *q, ngs_results **out);
int ngs_mark(ngs *db, const ngs_id *id, int32_t mark); 
int ngs_scan(ngs *db, const ngs_scan_opts *o, ngs_iter **it);
int ngs_iter_next(ngs_iter *it, ngs_fact **out); 
void ngs_iter_close(ngs_iter *it);
int ngs_checkpoint(ngs *db, uint8_t **ckpt, size_t *len); 
int ngs_verify(ngs *db, const uint8_t *ckpt, size_t len);
int ngs_rebuild(ngs *db);
int ngs_heads(ngs *db, ngs_head **heads, size_t *n); 
int ngs_sync_export(ngs *db, const ngs_head *since, size_t n_since, uint8_t **segment, size_t *len); 
int ngs_sync_import(ngs *db, const uint8_t *segment, size_t len, ngs_sync_report **report);
int ngs_stats(ngs *db, ngs_stats_t *out);
