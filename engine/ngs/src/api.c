/* SPDX-License-Identifier: Apache-2.0 */
/* api.c -- version, error strings, ngs_free, and the entry points M1 does not implement. */
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

#include "ngs_int.h"

int ngs_libversion_number(void) { return NGS_VERSION_NUMBER; }
const char *ngs_libversion(void) { return NGS_VERSION; }

const char *ngs_errstr(int rc) {
  switch (rc) {
    case NGS_OK:          return "ok";
    case NGS_ERROR:       return "error";
    case NGS_NOTFOUND:    return "not found";
    case NGS_BUSY:        return "writer lock held by another process";
    case NGS_CORRUPT:     return "corrupt: CRC, chain or signature check failed";
    case NGS_NOGRANT:     return "no write grant for this namespace";
    case NGS_MISMATCH:    return "embedding tag does not match the index";
    case NGS_QUARANTINED: return "every fact in a sync segment was rejected";
    case NGS_NOMEM:       return "out of memory";
    case NGS_IOERR:       return "I/O error";
    case NGS_MISUSE:      return "misuse (bad argument or struct size)";
    case NGS_TOOBIG:      return "body or attrs over the configured limit";
    default:              return rc >= 100 ? "informational code" : "unknown result code";
  }
}

void ngs_free(void *p) { free(p); }

/* ---- not in M1: each returns NGS_MISUSE with errmsg "not in M1" and clears its out-parameters ---- */
int ngs_invalidate(ngs *db, const ngs_id *id, ngs_str reason) { (void)id; (void)reason; return ngs__not_in_m1(db); }

int ngs_link(ngs *db, const ngs_id *a, const ngs_id *b, ngs_str rel, float weight, ngs_id *out_link_id) {
  (void)a; (void)b; (void)rel; (void)weight; (void)out_link_id;
  return ngs__not_in_m1(db);
}

int ngs_redact(ngs *db, const ngs_id *id, ngs_str reason) { (void)id; (void)reason; return ngs__not_in_m1(db); }

int ngs_grant(ngs *db, ngs_str ns, const ngs_pubkey *writer, ngs_id *out_grant_id) {
  (void)ns; (void)writer; (void)out_grant_id;
  return ngs__not_in_m1(db);
}

int ngs_recall(ngs *db, const ngs_query *q, ngs_results **out) {
  (void)q;
  if (out) *out = NULL;
  return ngs__not_in_m1(db);
}

int ngs_as_of(ngs *db, ngs_time t_valid, ngs_time t_record, const ngs_query *q, ngs_results **out) {
  (void)t_valid; (void)t_record; (void)q;
  if (out) *out = NULL;
  return ngs__not_in_m1(db);
}

int ngs_mark(ngs *db, const ngs_id *id, int32_t mark) { (void)id; (void)mark; return ngs__not_in_m1(db); }

int ngs_checkpoint(ngs *db, uint8_t **ckpt, size_t *len) {
  if (ckpt) *ckpt = NULL;
  if (len) *len = 0;
  return ngs__not_in_m1(db);
}

int ngs_rebuild(ngs *db) { return ngs__not_in_m1(db); }

int ngs_heads(ngs *db, ngs_head **heads, size_t *n) {
  if (heads) *heads = NULL;
  if (n) *n = 0;
  return ngs__not_in_m1(db);
}

int ngs_sync_export(ngs *db, const ngs_head *since, size_t n_since, uint8_t **segment, size_t *len) {
  (void)since; (void)n_since;
  if (segment) *segment = NULL;
  if (len) *len = 0;
  return ngs__not_in_m1(db);
}

int ngs_sync_import(ngs *db, const uint8_t *segment, size_t len, ngs_sync_report **report) {
  (void)segment; (void)len;
  if (report) *report = NULL;
  return ngs__not_in_m1(db);
}

int ngs_stats(ngs *db, ngs_stats_t *out) { (void)out; return ngs__not_in_m1(db); }
