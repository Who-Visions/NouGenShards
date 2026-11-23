/*
** ngs.h -- public API for NouGenShards (NGS): native memory for AI agents.
** Draft 0.3 (spec header; no implementation yet). See SPEC.md.
**
** Model: every write is an immutable, signed, hash-chained FACT. Nothing is
** deleted; facts are invalidated. Recall fuses vector, keyword, time,
** salience and link signals into one score.
**
** Engine vs application: the engine owns time, provenance, decay math, access
** counts, token accounting, abstention and sync. Salience judgement, fact
** extraction, contradiction adjudication and summarisation belong to the
** application. No LLM runs inside the engine.
**
** ---- Contracts (draft 0.3, from the PR 1199 review) ----
** ABI      Every input/output struct begins with `uint32_t size`; callers set it
**          to sizeof(struct) (use the NGS_*_INIT macros). The engine reads only
**          the fields that fit and zero-fills unknown tails on output, so adding
**          a field at the end never breaks a binding. Enum-like fields are int32_t.
** Borrow   Every pointer inside an input struct is borrowed for the duration of
**          the call only. The engine copies what it keeps.
** Own      Every object the engine returns (ngs_fact, ngs_results, segments,
**          checkpoints, head lists) is ONE allocation, interior pointers
**          included, and is released with a single ngs_free(). Returned objects
**          stay valid after ngs_close() of their db until freed.
** Errors   rc 0 = the call worked. 1..99 = errors. 100+ = reserved for
**          informational codes. Abstention and deadline timeouts are NOT error
**          codes: they return NGS_OK with flags in ngs_results.
**          ngs_errmsg(db) is per handle AND per thread, valid until the next call
**          on that handle from the same thread. ngs_errstr(rc) needs no handle
**          (use it when ngs_open fails).
** Threads  An ngs* may be shared by any number of threads; every function is
**          thread-safe on it except ngs_close(), which must not race other calls.
**          A handle must not be used in a forked child.
** Durable  ngs_remember/_many return after the group-commit fdatasync covering
**          their facts, unless NGS_WRITE_NO_SYNC is set (bulk ingest; durable at
**          the next sync point or ngs_flush()).
** Time     One sentinel set everywhere: NGS_TIME_MIN / NGS_TIME_MAX mean
**          unbounded; NGS_TIME_NOW means the engine clock.
**
** Licence: Apache-2.0.
*/
#ifndef NGS_H
#define NGS_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NGS_VERSION        "0.3.0-draft"
#define NGS_VERSION_NUMBER 3000
#define NGS_FORMAT         1          /* on-disk log format */
int         ngs_libversion_number(void);   /* runtime check vs NGS_VERSION_NUMBER */
const char *ngs_libversion(void);

/* ---------- result codes: 0 ok, 1..99 errors, 100+ reserved ---------- */
#define NGS_OK            0
#define NGS_ERROR         1
#define NGS_NOTFOUND      2
#define NGS_BUSY          3   /* writer lock held by another process */
#define NGS_CORRUPT       4   /* CRC, chain or signature check failed */
#define NGS_NOGRANT       5   /* no write grant for this namespace */
#define NGS_MISMATCH      6   /* embedding tag does not match the index */
#define NGS_QUARANTINED   7   /* every fact in a sync segment was rejected */
#define NGS_NOMEM         9
#define NGS_IOERR        10
#define NGS_MISUSE       11   /* includes a struct `size` the engine cannot accept */
#define NGS_TOOBIG       12   /* body/attrs over the configured limit */
const char *ngs_errstr(int rc);

/* ---------- time ---------- */
typedef int64_t ngs_time;                 /* microseconds since Unix epoch, UTC */
#define NGS_TIME_MIN  INT64_MIN           /* unbounded below */
#define NGS_TIME_MAX  INT64_MAX           /* unbounded above / "still valid" */
#define NGS_TIME_NOW  (INT64_MIN + 1)     /* engine clock */

/* ---------- memory kinds (int32_t on the wire) ---------- */
#define NGS_EPISODIC   1   /* what happened */
#define NGS_SEMANTIC   2   /* what is true */
#define NGS_PROCEDURAL 3   /* how to do things */
#define NGS_KIND_BIT(k) (1u << (k))   /* recall filter; 0 = all kinds */

/* ---------- recall arms ---------- */
#define NGS_ARM_VEC       0
#define NGS_ARM_KW        1
#define NGS_ARM_RECENCY   2
#define NGS_ARM_SALIENCE  3
#define NGS_ARM_LINK      4
#define NGS_N_ARMS        5   /* adding a 6th arm is an ABI break; see SPEC 13 */

typedef struct ngs ngs;                       /* database handle (opaque) */
typedef struct { uint8_t b[32]; } ngs_id;     /* BLAKE3 fact id */
typedef struct { uint8_t b[32]; } ngs_pubkey; /* Ed25519 public key */

typedef struct { const char *p; size_t n; } ngs_str;   /* length-delimited UTF-8 */

/* An embedding tagged by its model. Never mixed across tags in one index. */
typedef struct {
  ngs_str      model_id;
  uint32_t     dim;
  uint32_t     version;
  const float *v;          /* dim floats, L2-normalized by the caller */
} ngs_vec;

/* ---------- opening ---------- */
#define NGS_OPEN_READONLY   0x0001
#define NGS_OPEN_READWRITE  0x0002
#define NGS_OPEN_CREATE     0x0004   /* generate a node key if none is supplied */

typedef struct {
  uint32_t       size;              /* sizeof(ngs_open_opts) */
  int32_t        flags;             /* NGS_OPEN_* */
  const uint8_t *node_seckey;       /* 64-byte Ed25519 secret key, or NULL */
  uint64_t       segment_bytes;     /* 0 = 64 MiB */
  uint32_t       group_commit_ms;   /* 0 = 2 ms */
  uint32_t       checkpoint_every;  /* facts; 0 = 10000 */
  uint32_t       shard_vec_split;   /* brute-force ceiling per shard; 0 = 50000 (SPEC 5.6) */
  const ngs_pubkey *root_pubkey;    /* pinned operator root for fleet namespaces, or NULL */
} ngs_open_opts;
#define NGS_OPEN_OPTS_INIT { sizeof(ngs_open_opts), NGS_OPEN_READWRITE, 0, 0, 0, 0, 0, 0 }

/* Always returns a handle unless out of memory; on failure the handle is in an
** error state, ngs_errmsg() explains, and ngs_close() releases it. */
int  ngs_open(const char *dir, const ngs_open_opts *opts, ngs **out);
int  ngs_close(ngs *db);
const char *ngs_errmsg(ngs *db);
void ngs_free(void *p);
int  ngs_node_pubkey(ngs *db, ngs_pubkey *out);
int  ngs_flush(ngs *db);                 /* force a sync point */

/* ---------- writing ---------- */
#define NGS_WRITE_NO_SYNC 0x0001         /* return before fdatasync (bulk ingest) */

typedef struct {
  uint32_t   size;                 /* sizeof(ngs_fact_in) */
  ngs_str    ns;                   /* caller must hold its write grant */
  int32_t    kind;                 /* NGS_EPISODIC | NGS_SEMANTIC | NGS_PROCEDURAL */
  ngs_time   t_event;              /* NGS_TIME_NOW for now */
  ngs_time   valid_from;           /* NGS_TIME_NOW = t_event */
  ngs_str    title;
  ngs_str    body;                 /* verbatim; never rewritten */
  const ngs_str  *tags;        size_t n_tags;
  const uint8_t  *attrs_cbor;  size_t attrs_len;
  uint16_t   schema;
  const ngs_vec  *vecs;        size_t n_vecs;
  const ngs_id   *supersedes;      /* optional: invalidate this fact */
  float      salience0;            /* app's judgement in [0,1]; <0 = 0.5 */
  const ngs_str  *tokenizer_ids;   const uint32_t *token_counts; size_t n_token_counts;
} ngs_fact_in;
#define NGS_FACT_IN_INIT { sizeof(ngs_fact_in) }

int ngs_remember(ngs *db, const ngs_fact_in *in, int32_t flags, ngs_id *out_id);

/* Atomic multi-fact write: all facts become visible (and durable) together or none do. */
int ngs_remember_many(ngs *db, const ngs_fact_in *in, size_t n, int32_t flags,
                      ngs_id *out_ids /* n entries */);

/* Invalidation is how anything is undone, including links and grants:
** ngs_invalidate(link_id) unlinks; ngs_invalidate(grant_id) revokes. */
int ngs_invalidate(ngs *db, const ngs_id *id, ngs_str reason);

/* Links may name ids not yet present locally (they can arrive by sync); the
** link is stored and resolves when the target lands. */
int ngs_link(ngs *db, const ngs_id *a, const ngs_id *b, ngs_str rel, float weight,
             ngs_id *out_link_id);

/* Tombstone a body; signed REDACTION fact syncs to peers. See SPEC 2.2/13. */
int ngs_redact(ngs *db, const ngs_id *id, ngs_str reason);

/* Namespace genesis is a self-signed grant by the creating node. Fleet
** namespaces: the owner grant is signed offline by the pinned root key. */
int ngs_grant(ngs *db, ngs_str ns, const ngs_pubkey *writer, ngs_id *out_grant_id);

/* ---------- reading ---------- */
typedef struct {
  uint32_t   size;
  ngs_id     id;
  ngs_str    ns;
  int32_t    kind;
  ngs_pubkey writer;
  uint64_t   seq;
  ngs_time   t_event, t_record, valid_from, valid_to;   /* valid_to = NGS_TIME_MAX if open */
  ngs_id     superseded_by;                             /* zero if none */
  ngs_str    title, body;
  const ngs_str  *tags; size_t n_tags;
  const uint8_t  *attrs_cbor; size_t attrs_len;
  uint16_t   schema;                                    /* after read-time migration */
  int32_t    redacted;
} ngs_fact;

int ngs_get(ngs *db, const ngs_id *id, ngs_fact **out);   /* one allocation: ngs_free */

#define NGS_FUSE_ZSCORE 0
#define NGS_FUSE_RRF    1

#define NGS_RECALL_EXPAND           0x0001  /* follow links one hop */
#define NGS_RECALL_INCLUDE_INVALID  0x0002  /* return invalidated facts too, flagged */
#define NGS_RECALL_NO_BODY          0x0004  /* hits carry title only */

typedef struct {
  uint32_t        size;            /* sizeof(ngs_query) */
  ngs_str         ns;              /* empty = every readable namespace */
  uint32_t        kinds;           /* NGS_KIND_BIT mask; 0 = all */
  ngs_str         text;            /* keyword arm; empty skips it */
  const ngs_vec  *vec;             /* vector arm; NULL skips it */
  ngs_time        since, until;    /* t_event window; NGS_TIME_MIN/MAX = unbounded */
  const ngs_str  *tags; size_t n_tags;
  uint32_t        k;               /* 0 = 10 */
  uint32_t        deadline_ms;     /* 0 = 50 */
  int32_t         fusion;          /* NGS_FUSE_* */
  const float    *weights;         /* NGS_N_ARMS floats, indexed by NGS_ARM_*; NULL = defaults */
  int32_t         flags;           /* NGS_RECALL_* */
  uint32_t        token_budget;    /* 0 = no budget (use k) */
  ngs_str         tokenizer_id;    /* empty = engine estimate */
  float           min_confidence;  /* <0 = 0.35 */
} ngs_query;
#define NGS_QUERY_INIT { sizeof(ngs_query), {0,0}, 0, {0,0}, 0, NGS_TIME_MIN, NGS_TIME_MAX, 0, 0, 0, 0, 0, 0, 0, 0, {0,0}, -1.0f }

typedef struct {
  uint32_t  size;
  ngs_id    id;
  int32_t   kind;
  ngs_str   ns, title, body;       /* body empty when stub or NGS_RECALL_NO_BODY */
  float     score;
  float     arm[NGS_N_ARMS];       /* per-arm contribution, indexed by NGS_ARM_* */
  int32_t   invalid;
  float     confidence;            /* calibrated percentile in [0,1] */
  uint32_t  tokens;                /* cost charged against the budget */
  int32_t   stub;                  /* 1 = title-only to fit the budget */
  int32_t   tokens_estimated;      /* 1 = engine estimate */
} ngs_hit;

typedef struct {
  uint32_t  size;
  ngs_hit  *hits; size_t n;
  uint32_t  arms_complete;         /* bitmask of NGS_ARM_* that finished before the deadline */
  int32_t   timed_out;             /* 1 = at least one arm hit the deadline */
  uint32_t  elapsed_us;
  int32_t   abstained;             /* 1 = no hit cleared min_confidence; hits = nearest candidates */
  int32_t   confidence_calibrated; /* 0 = cold-start fallback threshold (SPEC 13) */
  float     best_confidence, min_confidence;
  uint32_t  tokens_used, tokens_budget;
} ngs_results;

/* rc NGS_OK even when abstained or timed out; always free *out with ngs_free. */
int ngs_recall(ngs *db, const ngs_query *q, ngs_results **out);
int ngs_as_of(ngs *db, ngs_time t_valid, ngs_time t_record,
              const ngs_query *q, ngs_results **out);

#define NGS_MARK_NOT_USED 0
#define NGS_MARK_USED     1
int ngs_mark(ngs *db, const ngs_id *id, int32_t mark);   /* NGS_NOTFOUND if id unknown locally */

/* ---------- scanning (export, debugging, migration) ---------- */
typedef struct {
  uint32_t        size;
  ngs_str         ns;              /* empty = all */
  const ngs_pubkey *writer;        /* NULL = all */
  ngs_time        since, until;    /* t_record window */
  int32_t         include_derived; /* 1 = also invalidations/links/redactions */
} ngs_scan_opts;
typedef struct ngs_iter ngs_iter;
int  ngs_scan(ngs *db, const ngs_scan_opts *o, ngs_iter **it);
int  ngs_iter_next(ngs_iter *it, ngs_fact **out);   /* NGS_NOTFOUND at end; free each fact */
void ngs_iter_close(ngs_iter *it);

/* ---------- integrity ---------- */
int ngs_checkpoint(ngs *db, uint8_t **ckpt, size_t *len);   /* one allocation */
int ngs_verify(ngs *db, const uint8_t *ckpt, size_t len);
int ngs_rebuild(ngs *db);

/* ---------- federation ---------- */
typedef struct { ngs_pubkey writer; ngs_str ns; uint64_t seq; } ngs_head;

int ngs_heads(ngs *db, ngs_head **heads, size_t *n);          /* one allocation */
int ngs_sync_export(ngs *db, const ngs_head *since, size_t n_since,
                    uint8_t **segment, size_t *len);           /* one allocation */

typedef struct {
  ngs_id   id;
  int32_t  rc;                     /* NGS_CORRUPT / NGS_NOGRANT / ... */
  char     reason[120];
} ngs_quarantine_entry;

typedef struct {
  uint32_t size;
  uint64_t applied, duplicates, quarantined;
  ngs_quarantine_entry *entries; size_t n_entries;   /* every quarantined fact */
} ngs_sync_report;

/* *report is one allocation (entries included); free with ngs_free. */
int ngs_sync_import(ngs *db, const uint8_t *segment, size_t len, ngs_sync_report **report);

/* ---------- introspection ---------- */
typedef struct {
  uint32_t size;
  uint64_t facts, invalidated, links, redacted;
  uint64_t log_bytes, derived_bytes;
  uint64_t vec_indexes, facts_missing_vec;
  uint64_t quarantined_segments;
  uint64_t recalls, abstentions, timeouts;
} ngs_stats_t;
#define NGS_STATS_INIT { sizeof(ngs_stats_t) }
int ngs_stats(ngs *db, ngs_stats_t *out);

#ifdef __cplusplus
}
#endif
#endif /* NGS_H */
