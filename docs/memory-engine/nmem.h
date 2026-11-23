/*
** nmem.h -- public API for nmem, a memory-native embedded storage engine.
** Draft 0.1 (spec header; no implementation yet). See SPEC.md.
**
** Model: every write is an immutable, signed, hash-chained FACT. Nothing is
** deleted; facts are invalidated. Recall fuses vector, keyword, time,
** salience and link signals into one score.
**
** Licence: Apache-2.0.
*/
#ifndef NMEM_H
#define NMEM_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NMEM_VERSION        "0.1.0-draft"
#define NMEM_VERSION_NUMBER 1000
#define NMEM_FORMAT         1          /* on-disk log format */

/* ---------- result codes ---------- */
#define NMEM_OK            0
#define NMEM_ERROR         1   /* generic */
#define NMEM_NOTFOUND      2
#define NMEM_BUSY          3   /* writer lock held by another process */
#define NMEM_CORRUPT       4   /* CRC, chain or signature check failed */
#define NMEM_NOGRANT       5   /* no write grant for this namespace */
#define NMEM_MISMATCH      6   /* embedding tag does not match the index */
#define NMEM_QUARANTINED   7   /* sync segment rejected and quarantined */
#define NMEM_TIMEOUT       8   /* deadline hit; partial result flagged */
#define NMEM_NOMEM         9
#define NMEM_IOERR        10
#define NMEM_MISUSE       11

/* ---------- open flags ---------- */
#define NMEM_OPEN_READONLY   0x0001
#define NMEM_OPEN_READWRITE  0x0002
#define NMEM_OPEN_CREATE     0x0004   /* generate a node key if none is supplied */

/* ---------- memory kinds ---------- */
typedef enum {
  NMEM_EPISODIC   = 1,   /* what happened */
  NMEM_SEMANTIC   = 2,   /* what is true */
  NMEM_PROCEDURAL = 3    /* how to do things */
} nmem_kind;
#define NMEM_KIND_ALL 0  /* recall filter: every kind */

typedef struct nmem nmem;                 /* database handle (opaque) */
typedef struct { uint8_t b[32]; } nmem_id;    /* BLAKE3 fact id */
typedef struct { uint8_t b[32]; } nmem_pubkey;/* Ed25519 public key */
typedef int64_t nmem_time;                /* microseconds since Unix epoch, UTC */
#define NMEM_TIME_NOW  INT64_MIN          /* sentinel: engine clock */

typedef struct {               /* length-delimited UTF-8 */
  const char *p;
  size_t      n;
} nmem_str;

/* An embedding tagged by the model that produced it. The engine stores and
** searches vectors; it never computes them and never mixes tags in one index. */
typedef struct {
  nmem_str     model_id;   /* e.g. "embeddinggemma-2" */
  uint32_t     dim;
  uint32_t     version;    /* bump when the model or preprocessing changes */
  const float *v;          /* dim floats, L2-normalized by the caller */
} nmem_vec;

/* ---------- opening ---------- */
typedef struct {
  int          flags;          /* NMEM_OPEN_* */
  const uint8_t *node_seckey;  /* 64-byte Ed25519 secret key, or NULL */
  size_t       segment_bytes;  /* 0 = default 64 MiB */
  uint32_t     group_commit_ms;/* 0 = default 2 ms */
  uint32_t     checkpoint_every;/* facts; 0 = default 10000 */
} nmem_open_opts;

int  nmem_open(const char *dir, const nmem_open_opts *opts, nmem **out);
int  nmem_close(nmem *db);
const char *nmem_errmsg(nmem *db);
void nmem_free(void *p);
int  nmem_node_pubkey(nmem *db, nmem_pubkey *out);

/* ---------- writing ---------- */
typedef struct {
  nmem_str   ns;            /* namespace; caller must hold its write grant */
  nmem_kind  kind;
  nmem_time  t_event;       /* NMEM_TIME_NOW for "now" */
  nmem_time  valid_from;    /* NMEM_TIME_NOW = t_event */
  nmem_str   title;
  nmem_str   body;          /* verbatim; never rewritten */
  const nmem_str *tags;  size_t n_tags;
  const uint8_t  *attrs_cbor; size_t attrs_len;  /* optional CBOR map */
  uint16_t   schema;        /* attrs schema version */
  const nmem_vec *vecs;  size_t n_vecs;          /* optional, one per tag */
  const nmem_id  *supersedes;                    /* optional: invalidate this fact */
} nmem_fact_in;

int nmem_remember(nmem *db, const nmem_fact_in *in, nmem_id *out_id);
int nmem_invalidate(nmem *db, const nmem_id *id, nmem_str reason);
int nmem_link(nmem *db, const nmem_id *a, const nmem_id *b,
              nmem_str rel, float weight);
int nmem_redact(nmem *db, const nmem_id *id, nmem_str reason);   /* tombstone body; chain stays valid */
int nmem_grant(nmem *db, nmem_str ns, const nmem_pubkey *writer); /* namespace owner only */

/* ---------- reading ---------- */
typedef struct {
  nmem_id     id;
  nmem_str    ns;
  nmem_kind   kind;
  nmem_pubkey writer;
  uint64_t    seq;
  nmem_time   t_event, t_record, valid_from, valid_to;   /* valid_to = INT64_MAX if open */
  nmem_id     superseded_by;                             /* zero if none */
  nmem_str    title, body;
  const nmem_str *tags; size_t n_tags;
  const uint8_t  *attrs_cbor; size_t attrs_len;
  uint16_t    schema;                                    /* after read-time migration */
  int         redacted;
} nmem_fact;

int nmem_get(nmem *db, const nmem_id *id, nmem_fact **out);   /* free with nmem_free */

typedef enum { NMEM_FUSE_ZSCORE = 0, NMEM_FUSE_RRF = 1 } nmem_fusion;

#define NMEM_RECALL_EXPAND        0x0001  /* follow links one hop */
#define NMEM_RECALL_INCLUDE_INVALID 0x0002 /* return invalidated facts too, flagged */

typedef struct {
  nmem_str        ns;              /* empty = every readable namespace */
  int             kinds;           /* bitmask of 1<<kind, 0 = all */
  nmem_str        text;            /* keyword arm; empty skips it */
  const nmem_vec *vec;             /* vector arm; NULL skips it */
  nmem_time       since, until;    /* t_event window; 0 = unbounded */
  const nmem_str *tags; size_t n_tags;  /* all must match */
  uint32_t        k;               /* results wanted; 0 = 10 */
  uint32_t        deadline_ms;     /* 0 = default 50 ms */
  nmem_fusion     fusion;
  const float    *weights;         /* 5 floats: vec, kw, recency, salience, link; NULL = defaults */
  int             flags;           /* NMEM_RECALL_* */
} nmem_query;

typedef struct {
  nmem_id   id;
  nmem_kind kind;
  float     score;
  float     arm[5];        /* per-arm contribution: vec, kw, recency, salience, link */
  int       invalid;       /* nonzero if invalidated as of the query time */
} nmem_hit;

typedef struct {
  nmem_hit *hits; size_t n;
  int       arms_complete; /* bitmask of arms that finished before the deadline */
  uint32_t  elapsed_us;
} nmem_results;

int nmem_recall(nmem *db, const nmem_query *q, nmem_results **out);
int nmem_as_of(nmem *db, nmem_time t_valid, nmem_time t_record,
               const nmem_query *q, nmem_results **out);

typedef enum { NMEM_MARK_USED = 1, NMEM_MARK_NOT_USED = 0 } nmem_mark_kind;
int nmem_mark(nmem *db, const nmem_id *id, nmem_mark_kind m);  /* feeds salience */

/* ---------- integrity ---------- */
int nmem_checkpoint(nmem *db, uint8_t **ckpt, size_t *len);    /* signed, exportable for off-node anchoring */
int nmem_verify(nmem *db, const uint8_t *ckpt, size_t len);    /* full chain + signature + merkle check */
int nmem_rebuild(nmem *db);                                    /* rebuild every derived file from the log */

/* ---------- federation ---------- */
typedef struct { nmem_pubkey writer; nmem_str ns; uint64_t seq; } nmem_head;

int nmem_heads(nmem *db, nmem_head **heads, size_t *n);
int nmem_sync_export(nmem *db, const nmem_head *since, size_t n_since,
                     uint8_t **segment, size_t *len);
typedef struct {
  uint64_t applied, duplicates, quarantined;
  nmem_str reason;   /* first quarantine reason, if any */
} nmem_sync_report;
int nmem_sync_import(nmem *db, const uint8_t *segment, size_t len,
                     nmem_sync_report *report);

/* ---------- introspection ---------- */
typedef struct {
  uint64_t facts, invalidated, links, redacted;
  uint64_t log_bytes, derived_bytes;
  uint64_t vec_indexes;              /* one per (model, dim, version) tag */
  uint64_t facts_missing_vec;        /* per default tag; NULL coverage is visible */
  uint64_t quarantined_segments;
} nmem_stats_t;
int nmem_stats(nmem *db, nmem_stats_t *out);

#ifdef __cplusplus
}
#endif
#endif /* NMEM_H */
