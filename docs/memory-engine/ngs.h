/*
** ngs.h -- public API for NouGenShards (NGS): native memory for AI agents.
** Draft 0.2 (spec header; no implementation yet). See SPEC.md.
**
** NouGenShards: native memory for AI agents.
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
** Licence: Apache-2.0.
*/
#ifndef NGS_H
#define NGS_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define NGS_VERSION        "0.2.0-draft"
#define NGS_VERSION_NUMBER 2000
#define NGS_FORMAT         1          /* on-disk log format */

/* ---------- result codes ---------- */
#define NGS_OK            0
#define NGS_ERROR         1   /* generic */
#define NGS_NOTFOUND      2
#define NGS_BUSY          3   /* writer lock held by another process */
#define NGS_CORRUPT       4   /* CRC, chain or signature check failed */
#define NGS_NOGRANT       5   /* no write grant for this namespace */
#define NGS_MISMATCH      6   /* embedding tag does not match the index */
#define NGS_QUARANTINED   7   /* sync segment rejected and quarantined */
#define NGS_TIMEOUT       8   /* deadline hit; partial result flagged */
#define NGS_NOMEM         9
#define NGS_IOERR        10
#define NGS_MISUSE       11
#define NGS_ABSTAIN      12   /* recall: nothing cleared min_confidence; results still describe why */

/* ---------- open flags ---------- */
#define NGS_OPEN_READONLY   0x0001
#define NGS_OPEN_READWRITE  0x0002
#define NGS_OPEN_CREATE     0x0004   /* generate a node key if none is supplied */

/* ---------- memory kinds ---------- */
typedef enum {
  NGS_EPISODIC   = 1,   /* what happened */
  NGS_SEMANTIC   = 2,   /* what is true */
  NGS_PROCEDURAL = 3    /* how to do things */
} ngs_kind;
#define NGS_KIND_ALL 0  /* recall filter: every kind */

typedef struct NGS NGS;                 /* database handle (opaque) */
typedef struct { uint8_t b[32]; } ngs_id;    /* BLAKE3 fact id */
typedef struct { uint8_t b[32]; } ngs_pubkey;/* Ed25519 public key */
typedef int64_t ngs_time;                /* microseconds since Unix epoch, UTC */
#define NGS_TIME_NOW  INT64_MIN          /* sentinel: engine clock */

typedef struct {               /* length-delimited UTF-8 */
  const char *p;
  size_t      n;
} ngs_str;

/* An embedding tagged by the model that produced it. The engine stores and
** searches vectors; it never computes them and never mixes tags in one index. */
typedef struct {
  ngs_str     model_id;   /* e.g. "embeddinggemma-2" */
  uint32_t     dim;
  uint32_t     version;    /* bump when the model or preprocessing changes */
  const float *v;          /* dim floats, L2-normalized by the caller */
} ngs_vec;

/* ---------- opening ---------- */
typedef struct {
  int          flags;          /* NGS_OPEN_* */
  const uint8_t *node_seckey;  /* 64-byte Ed25519 secret key, or NULL */
  size_t       segment_bytes;  /* 0 = default 64 MiB */
  uint32_t     group_commit_ms;/* 0 = default 2 ms */
  uint32_t     checkpoint_every;/* facts; 0 = default 10000 */
} ngs_open_opts;

int  ngs_open(const char *dir, const ngs_open_opts *opts, NGS **out);
int  ngs_close(NGS *db);
const char *ngs_errmsg(NGS *db);
void ngs_free(void *p);
int  ngs_node_pubkey(NGS *db, ngs_pubkey *out);

/* ---------- writing ---------- */
typedef struct {
  ngs_str   ns;            /* namespace; caller must hold its write grant */
  ngs_kind  kind;
  ngs_time  t_event;       /* NGS_TIME_NOW for "now" */
  ngs_time  valid_from;    /* NGS_TIME_NOW = t_event */
  ngs_str   title;
  ngs_str   body;          /* verbatim; never rewritten */
  const ngs_str *tags;  size_t n_tags;
  const uint8_t  *attrs_cbor; size_t attrs_len;  /* optional CBOR map */
  uint16_t   schema;        /* attrs schema version */
  const ngs_vec *vecs;  size_t n_vecs;          /* optional, one per tag */
  const ngs_id  *supersedes;                    /* optional: invalidate this fact */
  float      salience0;     /* application's importance judgement in [0,1]; <0 = default 0.5 */
  const ngs_str  *tokenizer_ids; const uint32_t *token_counts; size_t n_token_counts;
                            /* exact token cost per tokenizer; none = engine estimate */
} ngs_fact_in;

int ngs_remember(NGS *db, const ngs_fact_in *in, ngs_id *out_id);
int ngs_invalidate(NGS *db, const ngs_id *id, ngs_str reason);
int ngs_link(NGS *db, const ngs_id *a, const ngs_id *b,
              ngs_str rel, float weight);
int ngs_redact(NGS *db, const ngs_id *id, ngs_str reason);   /* tombstone body; chain stays valid */
int ngs_grant(NGS *db, ngs_str ns, const ngs_pubkey *writer); /* namespace owner only */

/* ---------- reading ---------- */
typedef struct {
  ngs_id     id;
  ngs_str    ns;
  ngs_kind   kind;
  ngs_pubkey writer;
  uint64_t    seq;
  ngs_time   t_event, t_record, valid_from, valid_to;   /* valid_to = INT64_MAX if open */
  ngs_id     superseded_by;                             /* zero if none */
  ngs_str    title, body;
  const ngs_str *tags; size_t n_tags;
  const uint8_t  *attrs_cbor; size_t attrs_len;
  uint16_t    schema;                                    /* after read-time migration */
  int         redacted;
} ngs_fact;

int ngs_get(NGS *db, const ngs_id *id, ngs_fact **out);   /* free with ngs_free */

typedef enum { NGS_FUSE_ZSCORE = 0, NGS_FUSE_RRF = 1 } ngs_fusion;

#define NGS_RECALL_EXPAND        0x0001  /* follow links one hop */
#define NGS_RECALL_INCLUDE_INVALID 0x0002 /* return invalidated facts too, flagged */

typedef struct {
  ngs_str        ns;              /* empty = every readable namespace */
  int             kinds;           /* bitmask of 1<<kind, 0 = all */
  ngs_str        text;            /* keyword arm; empty skips it */
  const ngs_vec *vec;             /* vector arm; NULL skips it */
  ngs_time       since, until;    /* t_event window; 0 = unbounded */
  const ngs_str *tags; size_t n_tags;  /* all must match */
  uint32_t        k;               /* results wanted; 0 = 10 */
  uint32_t        deadline_ms;     /* 0 = default 50 ms */
  ngs_fusion     fusion;
  const float    *weights;         /* 5 floats: vec, kw, recency, salience, link; NULL = defaults */
  int             flags;           /* NGS_RECALL_* */
  uint32_t        token_budget;    /* 0 = no budget (use k); else fill this many tokens */
  ngs_str         tokenizer_id;    /* which token counts to use; empty = engine estimate */
  float           min_confidence;  /* abstain below this; <0 = default 0.35 */
} ngs_query;

typedef struct {
  ngs_id   id;
  ngs_kind kind;
  float     score;
  float     arm[5];        /* per-arm contribution: vec, kw, recency, salience, link */
  int       invalid;       /* nonzero if invalidated as of the query time */
  float     confidence;    /* calibrated percentile in [0,1] */
  uint32_t  tokens;        /* cost charged against the budget */
  int       stub;          /* 1 = title-only stub (body omitted to fit the budget) */
  int       tokens_estimated; /* 1 = engine estimate, not an exact count */
} ngs_hit;

typedef struct {
  ngs_hit *hits; size_t n;
  int       arms_complete; /* bitmask of arms that finished before the deadline */
  uint32_t  elapsed_us;
  int       abstained;     /* 1 = no hit cleared min_confidence (rc NGS_ABSTAIN) */
  float     best_confidence, min_confidence;
  uint32_t  tokens_used, tokens_budget;
} ngs_results;

int ngs_recall(NGS *db, const ngs_query *q, ngs_results **out);
int ngs_as_of(NGS *db, ngs_time t_valid, ngs_time t_record,
               const ngs_query *q, ngs_results **out);

typedef enum { NGS_MARK_USED = 1, NGS_MARK_NOT_USED = 0 } ngs_mark_kind;
int ngs_mark(NGS *db, const ngs_id *id, ngs_mark_kind m);  /* feeds salience */

/* ---------- integrity ---------- */
int ngs_checkpoint(NGS *db, uint8_t **ckpt, size_t *len);    /* signed, exportable for off-node anchoring */
int ngs_verify(NGS *db, const uint8_t *ckpt, size_t len);    /* full chain + signature + merkle check */
int ngs_rebuild(NGS *db);                                    /* rebuild every derived file from the log */

/* ---------- federation ---------- */
typedef struct { ngs_pubkey writer; ngs_str ns; uint64_t seq; } ngs_head;

int ngs_heads(NGS *db, ngs_head **heads, size_t *n);
int ngs_sync_export(NGS *db, const ngs_head *since, size_t n_since,
                     uint8_t **segment, size_t *len);
typedef struct {
  uint64_t applied, duplicates, quarantined;
  ngs_str reason;   /* first quarantine reason, if any */
} ngs_sync_report;
int ngs_sync_import(NGS *db, const uint8_t *segment, size_t len,
                     ngs_sync_report *report);

/* ---------- introspection ---------- */
typedef struct {
  uint64_t facts, invalidated, links, redacted;
  uint64_t log_bytes, derived_bytes;
  uint64_t vec_indexes;              /* one per (model, dim, version) tag */
  uint64_t facts_missing_vec;        /* per default tag; NULL coverage is visible */
  uint64_t quarantined_segments;
  uint64_t recalls, abstentions;     /* abstain rate is visible */
} ngs_stats_t;
int ngs_stats(NGS *db, ngs_stats_t *out);

#ifdef __cplusplus
}
#endif
#endif /* NGS_H */
