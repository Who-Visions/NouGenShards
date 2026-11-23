/*
** log.c -- NGS M1: the signed, hash-chained, append-only fact log and the
** public API over it. Apache-2.0.
**
** On disk (SPEC 3, 3.1):
**   <dir>/LOCK            single-writer lock (advisory)
**   <dir>/KEY             node key: seed(32) | pubkey(32) | crc32c(4)
**   <dir>/log/NNNNNN.seg  segments: 64-byte header, then records
**
** Segment header: "NGSSEG\0\0" | u16 format | u16 flags | u64 first_rec |
**   32 B writer | 8 B zero | u32 crc32c(bytes 0..59). first_rec is the
**   log-wide index of the segment's first record.
** Record: u32 len | u8 type | payload[len] | u32 crc32c(type || payload),
**   integers little-endian. M1 writes type FACT (1) only.
** FACT payload, canonical CBOR array of 5:
**   [ fields, sig (bytes 64), body (bytes), batch_rest (uint), synced_upto (uint) ]
**   fields = map with integer keys 1..16, all present, ascending:
**     1 ns  2 kind  3 writer  4 seq  5 prev  6 t_event  7 t_record  8 valid_from
**     9 title  10 body_hash (BLAKE3 of body)  11 tags [text]  12 attrs (bytes)
**     13 schema  14 salience0 (millionths)  15 vecs [[model, dim, version, f32le bytes]]
**     16 token_counts [[tokenizer, count]]
**   fact_id = BLAKE3(encoded fields); sig = Ed25519(fact_id).
**   batch_rest counts the facts still to come in the same ngs_remember_many
**   write (0 = last), so a torn batch is detected and dropped whole.
**   synced_upto is the segment offset that was durable when the write was
**   issued: a bad record below a later record's synced_upto is corruption of
**   durable data, not a torn tail.
**
** Recovery (open): a short or CRC-failing record in the last segment is a
** torn tail and is truncated back to the start of its batch, unless a later
** valid record proves the damaged bytes were already durable (synced_upto),
** in which case the open fails with NGS_CORRUPT. Any damage outside the last
** segment, any CRC-valid record that fails to decode, a broken chain, a
** duplicate id or a segment-header mismatch is NGS_CORRUPT. Signatures are
** checked by ngs_verify, not on open (cost).
**
** The final record gets one more test (looks_torn): an interrupted append
** leaves the file short or leaves zero-filled sectors, a bit flip does not.
** Only the torn shape is truncated; a flipped final record is refused.
*/
#include "ngs_internal.h"
#include <stdio.h>
#include <time.h>
#include <math.h>

enum { REC_FACT = 1 };
#define SEG_HDR 64u
#define REC_OVERHEAD 9u            /* len(4) + type(1) + crc(4) */
#define KEY_FILE_LEN 68u
#define MAX_BODY (1u << 20)

/* ------------------------------------------------------------------ */
typedef struct {
  ngs_id   id;
  uint32_t seg;          /* index into db->segs */
  uint64_t off;          /* record start within the segment */
  uint32_t len;          /* whole record length incl. overhead */
  ngs_time t_record;
  uint32_t chain;        /* index into db->chains */
} fact_ref;

typedef struct {
  uint8_t  writer[32];
  char    *ns; size_t ns_len;
  uint64_t seq;
  ngs_id   last;
} chain_t;

typedef struct {
  uint32_t   no;          /* file number NNNNNN */
  ngs__file *f;
  uint64_t   size;        /* bytes of valid data */
  uint64_t   synced;      /* bytes known durable */
  uint8_t    writer[32];
} seg_t;

struct ngs {
  const ngs__vfs *vfs;
  ngs__mutex *mu;
  char       *dir;
  int32_t     flags;
  int         state_rc;    /* nonzero: open failed, or a write left the log unsafe */
  uint8_t     seed[32], pub[32];
  int         have_key;
  ngs__file  *lockf;
  uint64_t    seg_bytes;
  seg_t      *segs; size_t n_segs, cap_segs;
  fact_ref   *facts; size_t n_facts, cap_facts;
  uint32_t   *slots; size_t n_slots;   /* hash: fact index + 1, 0 = empty */
  chain_t    *chains; size_t n_chains, cap_chains;
  ngs_time    last_t_record;
  uint64_t    truncated_bytes;
};

struct ngs_iter {
  ngs *db;
  size_t pos;
  ngs_scan_opts o;
  char *ns_copy;
  ngs_pubkey writer;
  int has_writer;
};

/* ------------------------- error messages --------------------------
** Per handle AND per thread (ngs.h contract): each thread keeps a few slots
** keyed by handle. */
typedef struct { const ngs *db; char msg[256]; } err_slot;
static _Thread_local err_slot tls_err[4];
static _Thread_local unsigned tls_next;

static err_slot *slot_for(const ngs *db, int make) {
  unsigned i;
  for (i = 0; i < 4; i++) if (tls_err[i].db == db) return &tls_err[i];
  if (!make) return NULL;
  i = tls_next++ % 4u;
  tls_err[i].db = db;
  return &tls_err[i];
}

/* Messages are fixed text plus the code, which keeps <stdarg.h> out of the core. */
static int fail(ngs *db, int rc, const char *what) {
  err_slot *s = slot_for(db, 1);
  snprintf(s->msg, sizeof s->msg, "%s (%s)", what, ngs_errstr(rc));
  return rc;
}
static void clear_err(ngs *db) {
  err_slot *s = slot_for(db, 0);
  if (s) s->msg[0] = 0;
}

NGS_API const char *ngs_errstr(int rc) {
  switch (rc) {
    case NGS_OK: return "ok";
    case NGS_ERROR: return "error";
    case NGS_NOTFOUND: return "not found";
    case NGS_BUSY: return "writer lock held by another process";
    case NGS_CORRUPT: return "corrupt: CRC, chain or signature check failed";
    case NGS_NOGRANT: return "no write grant for this namespace";
    case NGS_MISMATCH: return "embedding tag does not match the index";
    case NGS_QUARANTINED: return "every fact in the segment was quarantined";
    case NGS_NOMEM: return "out of memory";
    case NGS_IOERR: return "I/O error";
    case NGS_MISUSE: return "misuse";
    case NGS_TOOBIG: return "too big";
    default: return "unknown result code";
  }
}

NGS_API const char *ngs_errmsg(ngs *db) {
  err_slot *s;
  if (!db) return "no handle";
  s = slot_for(db, 0);
  if (s && s->msg[0]) return s->msg;
  return db->state_rc ? ngs_errstr(db->state_rc) : "ok";
}

NGS_API int ngs_libversion_number(void) { return NGS_VERSION_NUMBER; }
NGS_API const char *ngs_libversion(void) { return NGS_VERSION; }
NGS_API void ngs_free(void *p) { free(p); }

/* ----------------------------- helpers ----------------------------- */
static void put_le(uint8_t *p, uint64_t v, int n) { int i; for (i = 0; i < n; i++) { p[i] = (uint8_t)v; v >>= 8; } }
static uint64_t get_le(const uint8_t *p, int n) {
  uint64_t v = 0; int i;
  for (i = n - 1; i >= 0; i--) v = (v << 8) | p[i];
  return v;
}

static int utf8_ok(const char *s, size_t n) {
  const uint8_t *p = (const uint8_t *)s, *e = p + n;
  while (p < e) {
    uint8_t c = *p;
    size_t k;
    uint32_t cp;
    if (c < 0x80) { p++; continue; }
    if ((c & 0xe0) == 0xc0) { k = 1; cp = c & 0x1f; }
    else if ((c & 0xf0) == 0xe0) { k = 2; cp = c & 0x0f; }
    else if ((c & 0xf8) == 0xf0) { k = 3; cp = c & 0x07; }
    else return 0;
    if ((size_t)(e - p) <= k) return 0;
    {
      size_t i;
      for (i = 1; i <= k; i++) { if ((p[i] & 0xc0) != 0x80) return 0; cp = (cp << 6) | (p[i] & 0x3f); }
    }
    if ((k == 1 && cp < 0x80) || (k == 2 && cp < 0x800) || (k == 3 && cp < 0x10000) ||
        cp > 0x10ffff || (cp >= 0xd800 && cp <= 0xdfff)) return 0;
    p += k + 1;
  }
  return 1;
}

static int str_ok(ngs_str s) { return s.p != NULL || s.n == 0; }

static ngs_time wall_us(void) {
  struct timespec ts;
  if (timespec_get(&ts, TIME_UTC) != TIME_UTC) return 0;
  return (ngs_time)ts.tv_sec * 1000000 + (ngs_time)(ts.tv_nsec / 1000);
}

static char *path_join(const char *a, const char *b) {
  size_t na = strlen(a), nb = strlen(b);
  char *p = (char *)malloc(na + nb + 2);
  if (!p) return NULL;
  memcpy(p, a, na); p[na] = '/'; memcpy(p + na + 1, b, nb + 1);
  return p;
}
static char *seg_path(const ngs *db, uint32_t no) {
  char name[32];
  snprintf(name, sizeof name, "log/%06u.seg", (unsigned)no);
  return path_join(db->dir, name);
}

static int grow(void **arr, size_t *cap, size_t need, size_t elem) {
  size_t c;
  void *q;
  if (need <= *cap) return NGS_OK;
  c = *cap ? *cap : 16;
  while (c < need) { if (c > SIZE_MAX / 2 / elem) return NGS_NOMEM; c *= 2; }
  q = realloc(*arr, c * elem);
  if (!q) return NGS_NOMEM;
  *arr = q; *cap = c;
  return NGS_OK;
}

/* --------------------------- id hash index --------------------------- */
static uint64_t id_key(const ngs_id *id) { return get_le(id->b, 8); }

static int idx_rehash(ngs *db, size_t n) {
  uint32_t *s = (uint32_t *)calloc(n, sizeof *s);
  size_t i;
  if (!s) return NGS_NOMEM;
  free(db->slots);
  db->slots = s; db->n_slots = n;
  for (i = 0; i < db->n_facts; i++) {
    size_t h = (size_t)(id_key(&db->facts[i].id) & (n - 1));
    while (s[h]) h = (h + 1) & (n - 1);
    s[h] = (uint32_t)(i + 1);
  }
  return NGS_OK;
}

static long idx_find(const ngs *db, const ngs_id *id) {
  size_t h;
  if (!db->n_slots) return -1;
  h = (size_t)(id_key(id) & (db->n_slots - 1));
  while (db->slots[h]) {
    uint32_t k = db->slots[h] - 1;
    if (memcmp(db->facts[k].id.b, id->b, 32) == 0) return (long)k;
    h = (h + 1) & (db->n_slots - 1);
  }
  return -1;
}

static int idx_add(ngs *db, const fact_ref *r) {
  int rc;
  if (db->n_facts >= UINT32_MAX - 1) return NGS_TOOBIG;
  if ((rc = grow((void **)&db->facts, &db->cap_facts, db->n_facts + 1, sizeof *db->facts))) return rc;
  db->facts[db->n_facts++] = *r;
  if ((db->n_facts + 1) * 10 > db->n_slots * 7) {
    return idx_rehash(db, db->n_slots ? db->n_slots * 2 : 1024);
  }
  {
    size_t h = (size_t)(id_key(&r->id) & (db->n_slots - 1));
    while (db->slots[h]) h = (h + 1) & (db->n_slots - 1);
    db->slots[h] = (uint32_t)db->n_facts;
  }
  return NGS_OK;
}

static long chain_find(const ngs *db, const uint8_t writer[32], const char *ns, size_t n) {
  size_t i;
  for (i = 0; i < db->n_chains; i++) {
    const chain_t *c = &db->chains[i];
    if (c->ns_len == n && memcmp(c->writer, writer, 32) == 0 && memcmp(c->ns, ns, n) == 0) return (long)i;
  }
  return -1;
}

static long chain_get(ngs *db, const uint8_t writer[32], const char *ns, size_t n) {
  long k = chain_find(db, writer, ns, n);
  chain_t *c;
  if (k >= 0) return k;
  if (grow((void **)&db->chains, &db->cap_chains, db->n_chains + 1, sizeof *db->chains)) return -1;
  c = &db->chains[db->n_chains];
  memset(c, 0, sizeof *c);
  c->ns = (char *)malloc(n ? n : 1);
  if (!c->ns) return -1;
  memcpy(c->ns, ns, n);
  c->ns_len = n;
  memcpy(c->writer, writer, 32);
  return (long)db->n_chains++;
}

/* --------------------------- fact decoding --------------------------- */
typedef struct {
  const uint8_t *fields; size_t fields_len;
  const uint8_t *sig;
  const uint8_t *body; size_t body_len;
  uint64_t batch_rest, synced_upto;
  const char *ns; size_t ns_len;
  uint64_t kind;
  const uint8_t *writer;
  uint64_t seq;
  const uint8_t *prev;
  int64_t t_event, t_record, valid_from;
  const char *title; size_t title_len;
  const uint8_t *body_hash;
  const uint8_t *tags; size_t tags_len; uint64_t n_tags;   /* raw CBOR of the tag array items */
  const uint8_t *attrs; size_t attrs_len;
  uint64_t schema;
} dec_t;

static int expect_key(ngs__rd *r, uint64_t k) {
  uint64_t v;
  return ngs__cbor_get_uint(r, &v) || v != k;
}

/* Strict decode of one FACT payload. Returns 0 or -1. */
static int decode_fact(const uint8_t *p, size_t n, dec_t *d) {
  ngs__rd r;
  int m;
  uint64_t v, i;
  size_t sl;
  const uint8_t *b;
  memset(d, 0, sizeof *d);
  r.p = p; r.end = p + n; r.err = 0;
  if (ngs__cbor_get_head(&r, &m, &v) || m != 4 || v != 5) return -1;
  d->fields = r.p;
  if (ngs__cbor_get_head(&r, &m, &v) || m != 5 || v != 16) return -1;
  if (expect_key(&r, 1) || ngs__cbor_get_text(&r, &d->ns, &d->ns_len)) return -1;
  if (expect_key(&r, 2) || ngs__cbor_get_uint(&r, &d->kind)) return -1;
  if (expect_key(&r, 3) || ngs__cbor_get_bytes(&r, &d->writer, &sl) || sl != 32) return -1;
  if (expect_key(&r, 4) || ngs__cbor_get_uint(&r, &d->seq)) return -1;
  if (expect_key(&r, 5) || ngs__cbor_get_bytes(&r, &d->prev, &sl) || sl != 32) return -1;
  if (expect_key(&r, 6) || ngs__cbor_get_int(&r, &d->t_event)) return -1;
  if (expect_key(&r, 7) || ngs__cbor_get_int(&r, &d->t_record)) return -1;
  if (expect_key(&r, 8) || ngs__cbor_get_int(&r, &d->valid_from)) return -1;
  if (expect_key(&r, 9) || ngs__cbor_get_text(&r, &d->title, &d->title_len)) return -1;
  if (expect_key(&r, 10) || ngs__cbor_get_bytes(&r, &d->body_hash, &sl) || sl != 32) return -1;
  if (expect_key(&r, 11) || ngs__cbor_get_head(&r, &m, &d->n_tags) || m != 4) return -1;
  d->tags = r.p;
  for (i = 0; i < d->n_tags; i++) { const char *t; size_t tl; if (ngs__cbor_get_text(&r, &t, &tl)) return -1; }
  d->tags_len = (size_t)(r.p - d->tags);
  if (expect_key(&r, 12) || ngs__cbor_get_bytes(&r, &d->attrs, &d->attrs_len)) return -1;
  if (expect_key(&r, 13) || ngs__cbor_get_uint(&r, &d->schema) || d->schema > 0xffff) return -1;
  if (expect_key(&r, 14) || ngs__cbor_get_uint(&r, &v) || v > 1000000) return -1;
  if (expect_key(&r, 15) || ngs__cbor_skip(&r, 1)) return -1;
  if (expect_key(&r, 16) || ngs__cbor_skip(&r, 1)) return -1;
  d->fields_len = (size_t)(r.p - d->fields);
  if (ngs__cbor_get_bytes(&r, &d->sig, &sl) || sl != 64) return -1;
  if (ngs__cbor_get_bytes(&r, &b, &d->body_len)) return -1;
  d->body = b;
  if (ngs__cbor_get_uint(&r, &d->batch_rest) || ngs__cbor_get_uint(&r, &d->synced_upto)) return -1;
  if (r.err || r.p != r.end) return -1;
  if (d->kind < 1 || d->kind > 3 || d->ns_len == 0 || d->ns_len > NGS_MAX_NS_LEN) return -1;
  {
    uint8_t h[32];
    ngs__blake3_hash(d->body, d->body_len, h);
    if (memcmp(h, d->body_hash, 32) != 0) return -1;
  }
  return 0;
}

/* --------------------------- segments --------------------------- */
static void seg_header(uint8_t h[SEG_HDR], uint64_t first_rec, const uint8_t writer[32]) {
  memset(h, 0, SEG_HDR);
  memcpy(h, "NGSSEG\0\0", 8);
  put_le(h + 8, NGS_FORMAT, 2);
  put_le(h + 12, first_rec, 8);
  memcpy(h + 20, writer, 32);
  put_le(h + 60, ngs__crc32c(0, h, 60), 4);
}

static int seg_header_ok(const uint8_t h[SEG_HDR]) {
  return memcmp(h, "NGSSEG\0\0", 8) == 0 && get_le(h + 8, 2) == NGS_FORMAT &&
         get_le(h + 60, 4) == ngs__crc32c(0, h, 60);
}

static int add_seg(ngs *db, uint32_t no, ngs__file *f, uint64_t size, const uint8_t writer[32]) {
  int rc;
  seg_t *s;
  if ((rc = grow((void **)&db->segs, &db->cap_segs, db->n_segs + 1, sizeof *db->segs))) return rc;
  s = &db->segs[db->n_segs++];
  s->no = no; s->f = f; s->size = size; s->synced = size;
  memcpy(s->writer, writer, 32);
  return NGS_OK;
}

/* Start a new segment owned by this node. */
static int seg_rotate(ngs *db) {
  uint8_t h[SEG_HDR];
  uint32_t no = db->n_segs ? db->segs[db->n_segs - 1].no + 1 : 1;
  char *p = seg_path(db, no), *logdir;
  ngs__file *f = NULL;
  int rc;
  if (!p) return NGS_NOMEM;
  rc = db->vfs->open(p, 1, &f);
  free(p);
  if (rc) return rc;
  seg_header(h, db->n_facts, db->pub);
  if ((rc = db->vfs->truncate(f, 0)) || (rc = db->vfs->pwrite(f, h, SEG_HDR, 0)) || (rc = db->vfs->sync(f))) {
    db->vfs->close(f);
    return rc;
  }
  logdir = path_join(db->dir, "log");
  if (!logdir) { db->vfs->close(f); return NGS_NOMEM; }
  rc = db->vfs->sync_dir(logdir);
  free(logdir);
  if (rc) { db->vfs->close(f); return rc; }
  if ((rc = add_seg(db, no, f, SEG_HDR, db->pub))) { db->vfs->close(f); return rc; }
  return NGS_OK;
}

static int read_all(ngs *db, ngs__file *f, uint64_t size, uint8_t **out) {
  uint8_t *b;
  size_t got;
  int rc;
  *out = NULL;
  if (size > (uint64_t)SIZE_MAX - 1) return NGS_TOOBIG;
  b = (uint8_t *)malloc((size_t)size + 1);
  if (!b) return NGS_NOMEM;
  if ((rc = db->vfs->pread(f, b, (size_t)size, 0, &got))) { free(b); return rc; }
  if (got != size) { free(b); return NGS_IOERR; }
  *out = b;
  return NGS_OK;
}

/* Is there a CRC-valid record anywhere in b[from..n)? Returns the largest
** synced_upto among them, or 0 if none decodes (used to tell a torn tail from
** damage to durable data). */
static uint64_t later_durable_mark(const uint8_t *b, size_t from, size_t n) {
  size_t o;
  uint64_t best = 0;
  for (o = from; o + REC_OVERHEAD <= n; o++) {
    uint64_t len = get_le(b + o, 4);
    dec_t d;
    if (len < 1 || len > n - o - REC_OVERHEAD || b[o + 4] != REC_FACT) continue;
    if (get_le(b + o + 5 + len, 4) != ngs__crc32c(0, b + o + 4, (size_t)len + 1)) continue;
    if (decode_fact(b + o + 5, (size_t)len, &d) == 0 && d.synced_upto > best) best = d.synced_upto;
  }
  return best;
}

/* Is the bad record at `off` shaped like an interrupted append, or like damage
** to bytes that were written whole? An append that never finished leaves the
** file short, or leaves never-written regions as zeros (a later sector reached
** the disk, an earlier one did not). A bit flip leaves a full-length record
** with a few wrong bits. Only the first shape may be truncated; anything else
** is refused, so a flipped final record is reported, not silently dropped. */
#define SECTOR 512u
static int looks_torn(const uint8_t *b, size_t off, size_t n) {
  size_t rem = n - off, end, s, i;
  uint64_t len;
  if (rem < REC_OVERHEAD) return 1;             /* a flip cannot shorten a file */
  len = get_le(b + off, 4);
  if (len == 0) {                               /* a zero length: unwritten bytes? */
    size_t lim = rem < 16 ? rem : 16;
    for (i = 0; i < lim; i++) if (b[off + i]) return 0;
    return 1;
  }
  if (len > rem - REC_OVERHEAD) {               /* claims more bytes than exist */
    size_t alt = rem - REC_OVERHEAD;            /* ...unless only the length flipped */
    if (alt >= 1 && get_le(b + off + 5 + alt, 4) == ngs__crc32c(0, b + off + 4, alt + 1)) return 0;
    return 1;
  }
  /* full length present but the CRC fails: torn only if some sector-aligned
  ** stretch inside the record, at least 32 bytes long, is all zeros */
  end = off + (size_t)len + REC_OVERHEAD;
  for (s = (off / SECTOR + 1) * SECTOR; s < end; s += SECTOR) {
    size_t stop = s + SECTOR < end ? s + SECTOR : end, k;
    if (stop - s < 32) continue;
    for (k = s; k < stop && b[k] == 0; k++) {}
    if (k == stop) return 1;
  }
  return 0;
}

typedef struct { fact_ref ref; uint64_t seq; ngs_id prev; long chain; } pending_t;

/* Replay one segment into the index. `last` = this is the final segment. */
static int replay_seg(ngs *db, uint32_t si, int last, int writable) {
  seg_t *s = &db->segs[si];
  uint8_t *b = NULL;
  uint64_t size;
  size_t off, n;
  pending_t *pend = NULL;
  size_t n_pend = 0, cap_pend = 0, batch_start = SEG_HDR;
  uint64_t expect_rest = 0;
  int rc = NGS_OK, torn = 0;
  size_t bad_at = (size_t)-1;
  if ((rc = db->vfs->size(s->f, &size))) return rc;
  if ((rc = read_all(db, s->f, size, &b))) return rc;
  n = (size_t)size;
  if (n < SEG_HDR || !seg_header_ok(b)) {
    /* a header torn by a crash during rotation: only legal as the last,
    ** record-free segment */
    if (last && n < SEG_HDR + REC_OVERHEAD) {
      free(b);
      if (!writable) { s->size = s->synced = SEG_HDR; return NGS_OK; }
      if ((rc = db->vfs->truncate(s->f, 0)) == 0) {
        uint8_t h[SEG_HDR];
        seg_header(h, db->n_facts, db->pub);
        if ((rc = db->vfs->pwrite(s->f, h, SEG_HDR, 0)) == 0) rc = db->vfs->sync(s->f);
        memcpy(s->writer, db->pub, 32);
      }
      s->size = s->synced = SEG_HDR;
      return rc;
    }
    free(b);
    return fail(db, NGS_CORRUPT, "segment header damaged");
  }
  if (get_le(b + 12, 8) != db->n_facts) { free(b); return fail(db, NGS_CORRUPT, "segment does not start where the previous one ended"); }
  memcpy(s->writer, b + 20, 32);
  off = SEG_HDR;
  while (off < n) {
    uint64_t len;
    dec_t d;
    ngs_id id;
    long ck;
    chain_t *c;
    uint64_t prev_seq;
    const uint8_t *prev_id;
    size_t k;
    if (n - off < REC_OVERHEAD) { torn = 1; bad_at = off; break; }
    len = get_le(b + off, 4);
    if (len < 1 || len > n - off - REC_OVERHEAD || b[off + 4] != REC_FACT ||
        get_le(b + off + 5 + len, 4) != ngs__crc32c(0, b + off + 4, (size_t)len + 1)) { torn = 1; bad_at = off; break; }
    if (decode_fact(b + off + 5, (size_t)len, &d) != 0) { rc = fail(db, NGS_CORRUPT, "a CRC-valid record does not decode"); goto out; }
    if (memcmp(d.writer, s->writer, 32) != 0) { rc = fail(db, NGS_CORRUPT, "fact writer differs from its segment"); goto out; }
    if (n_pend > 0 && d.batch_rest + 1 != expect_rest) { rc = fail(db, NGS_CORRUPT, "batch framing broken"); goto out; }
    ngs__blake3_hash(d.fields, d.fields_len, id.b);
    /* chain: seq gapless per (writer, ns), prev = previous id; pending
    ** facts of the same batch count */
    ck = chain_get(db, d.writer, d.ns, d.ns_len);
    if (ck < 0) { rc = NGS_NOMEM; goto out; }
    c = &db->chains[ck];
    prev_seq = c->seq; prev_id = c->last.b;
    for (k = n_pend; k > 0; k--) {
      if (pend[k - 1].chain == ck) { prev_seq = pend[k - 1].seq; prev_id = pend[k - 1].ref.id.b; break; }
    }
    if (d.seq != prev_seq + 1 || memcmp(d.prev, prev_id, 32) != 0) { rc = fail(db, NGS_CORRUPT, "hash chain broken (seq or prev)"); goto out; }
    if (idx_find(db, &id) >= 0) { rc = fail(db, NGS_CORRUPT, "duplicate fact id"); goto out; }
    for (k = 0; k < n_pend; k++) if (memcmp(pend[k].ref.id.b, id.b, 32) == 0) { rc = fail(db, NGS_CORRUPT, "duplicate fact id"); goto out; }
    if (grow((void **)&pend, &cap_pend, n_pend + 1, sizeof *pend)) { rc = NGS_NOMEM; goto out; }
    if (n_pend == 0) batch_start = off;
    pend[n_pend].ref.id = id;
    pend[n_pend].ref.seg = si;
    pend[n_pend].ref.off = off;
    pend[n_pend].ref.len = (uint32_t)(len + REC_OVERHEAD);
    pend[n_pend].ref.t_record = d.t_record;
    pend[n_pend].ref.chain = (uint32_t)ck;
    pend[n_pend].seq = d.seq;
    pend[n_pend].chain = ck;
    n_pend++;
    expect_rest = d.batch_rest;
    off += (size_t)len + REC_OVERHEAD;
    if (d.batch_rest == 0) {          /* batch complete: publish it */
      for (k = 0; k < n_pend; k++) {
        chain_t *cc = &db->chains[pend[k].chain];
        cc->seq = pend[k].seq;
        cc->last = pend[k].ref.id;
        if ((rc = idx_add(db, &pend[k].ref))) goto out;
        if (pend[k].ref.t_record > db->last_t_record) db->last_t_record = pend[k].ref.t_record;
      }
      n_pend = 0;
      batch_start = off;
    }
  }
  if (n_pend > 0) torn = 1;          /* a batch that never finished */
  if (torn) {
    size_t cut = n_pend > 0 ? batch_start : off;
    if (!last) { rc = fail(db, NGS_CORRUPT, "damaged record before the last segment"); goto out; }
    if (later_durable_mark(b, cut + 1, n) > cut) { rc = fail(db, NGS_CORRUPT, "damage inside data that was already durable"); goto out; }
    if (bad_at != (size_t)-1 && !looks_torn(b, bad_at, n)) { rc = fail(db, NGS_CORRUPT, "the final record is damaged, not torn: refusing to drop it"); goto out; }
    db->truncated_bytes += n - cut;
    if (writable) {
      if ((rc = db->vfs->truncate(s->f, cut)) || (rc = db->vfs->sync(s->f))) goto out;
    }
    n = cut;
  }
  s->size = s->synced = n;
out:
  free(pend);
  free(b);
  return rc;
}

/* ------------------------------ key ------------------------------ */
static int load_or_make_key(ngs *db, const ngs_open_opts *o, int may_create) {
  char *kp;
  ngs__file *f = NULL;
  uint8_t k[KEY_FILE_LEN];
  size_t got = 0;
  int rc, exists;
  if (o->node_seckey) {
    uint8_t pk[32];
    memcpy(db->seed, o->node_seckey, 32);
    ngs__ed25519_pubkey(db->seed, pk);
    if (memcmp(pk, o->node_seckey + 32, 32) != 0) return fail(db, NGS_MISUSE, "node_seckey: public half does not match the seed");
    memcpy(db->pub, pk, 32);
    db->have_key = 1;
    return NGS_OK;
  }
  kp = path_join(db->dir, "KEY");
  if (!kp) return NGS_NOMEM;
  db->vfs->exists(kp, &exists);
  if (exists) {
    if ((rc = db->vfs->open(kp, 0, &f)) == 0) {
      rc = db->vfs->pread(f, k, sizeof k, 0, &got);
      db->vfs->close(f);
    }
    if (rc == 0 && got == KEY_FILE_LEN && get_le(k + 64, 4) == ngs__crc32c(0, k, 64)) {
      uint8_t pk[32];
      int match;
      memcpy(db->seed, k, 32);
      ngs__ed25519_pubkey(db->seed, pk);
      match = memcmp(pk, k + 32, 32) == 0;
      ngs__wipe(k, sizeof k);
      if (!match) { ngs__wipe(db->seed, 32); free(kp); return fail(db, NGS_CORRUPT, "KEY file: public half does not match the seed"); }
      memcpy(db->pub, pk, 32);
      db->have_key = 1;
      free(kp);
      return NGS_OK;
    }
    ngs__wipe(k, sizeof k);
    /* A KEY torn during creation may be replaced, but only while the log is
    ** empty; with facts on disk a damaged KEY is corruption, never reset. */
    if (!may_create || db->n_segs > 0) { free(kp); return rc ? rc : fail(db, NGS_CORRUPT, "KEY file damaged"); }
  }
  if (!may_create) { free(kp); db->have_key = 0; return NGS_OK; }
  if ((rc = db->vfs->random(db->seed, 32))) { free(kp); return rc; }
  ngs__ed25519_pubkey(db->seed, db->pub);
  memcpy(k, db->seed, 32); memcpy(k + 32, db->pub, 32);
  put_le(k + 64, ngs__crc32c(0, k, 64), 4);
  rc = db->vfs->open(kp, 1, &f);
  if (rc == 0) {
    if ((rc = db->vfs->truncate(f, 0)) == 0 && (rc = db->vfs->pwrite(f, k, sizeof k, 0)) == 0) rc = db->vfs->sync(f);
    db->vfs->close(f);
  }
  ngs__wipe(k, sizeof k);
  if (rc == 0) rc = db->vfs->sync_dir(db->dir);
  free(kp);
  if (rc == 0) db->have_key = 1;
  return rc;
}

/* ------------------------------ open ------------------------------ */
NGS_API int ngs_open(const char *dir, const ngs_open_opts *opts, ngs **out) {
  ngs_open_opts o = NGS_OPEN_OPTS_INIT;
  ngs *db;
  int rc, writable, create;
  char *lp = NULL, *logdir = NULL;
  uint32_t no;
  if (!out) return NGS_MISUSE;
  *out = NULL;
  db = (ngs *)calloc(1, sizeof *db);
  if (!db) return NGS_NOMEM;
  *out = db;
  db->vfs = ngs__vfs_get();
  if (opts) {
    if (opts->size < offsetof(ngs_open_opts, node_seckey)) { db->state_rc = fail(db, NGS_MISUSE, "ngs_open_opts.size too small"); return db->state_rc; }
    memcpy(&o, opts, opts->size < sizeof o ? opts->size : sizeof o);
    o.size = sizeof o;
  }
  writable = (o.flags & NGS_OPEN_READWRITE) != 0;
  create = (o.flags & NGS_OPEN_CREATE) != 0;
  if (!dir || !*dir || (writable && (o.flags & NGS_OPEN_READONLY)) || (!writable && create)) {
    db->state_rc = fail(db, NGS_MISUSE, "bad directory or open flags");
    return db->state_rc;
  }
  db->flags = o.flags;
  db->seg_bytes = o.segment_bytes ? o.segment_bytes : (uint64_t)64 << 20;
  if (db->seg_bytes < 4096) db->seg_bytes = 4096;
  if ((rc = ngs__mutex_new(&db->mu))) { db->state_rc = rc; return rc; }
  db->dir = (char *)malloc(strlen(dir) + 1);
  if (!db->dir) { db->state_rc = NGS_NOMEM; return NGS_NOMEM; }
  strcpy(db->dir, dir);
  {
    int ex = 0;
    db->vfs->exists(dir, &ex);
    if (!ex && !create) { db->state_rc = fail(db, NGS_NOTFOUND, "database directory does not exist"); return db->state_rc; }
  }
  logdir = path_join(dir, "log");
  lp = path_join(dir, "LOCK");
  if (!logdir || !lp) { rc = NGS_NOMEM; goto done; }
  if (create) {
    if ((rc = db->vfs->mkdir(dir)) || (rc = db->vfs->mkdir(logdir))) goto done;
  }
  if (writable) {
    if ((rc = db->vfs->open(lp, 1, &db->lockf))) goto done;
    if ((rc = db->vfs->lock(db->lockf))) { rc = fail(db, rc, "another process holds the writer lock"); goto done; }
  }
  /* discover segments 000001.. in order; a gap is corruption */
  for (no = 1;; no++) {
    char *p = seg_path(db, no);
    int ex = 0;
    ngs__file *f;
    if (!p) { rc = NGS_NOMEM; goto done; }
    db->vfs->exists(p, &ex);
    if (!ex) {
      char *q = seg_path(db, no + 1);
      int ex2 = 0;
      free(p);
      if (q) { db->vfs->exists(q, &ex2); free(q); }
      if (ex2) { rc = fail(db, NGS_CORRUPT, "a log segment is missing"); goto done; }
      break;
    }
    rc = db->vfs->open(p, 0, &f);
    free(p);
    if (rc) goto done;
    if ((rc = add_seg(db, no, f, 0, db->pub))) { db->vfs->close(f); goto done; }
  }
  if ((rc = load_or_make_key(db, &o, writable && create))) goto done;
  {
    uint32_t i;
    for (i = 0; i < db->n_segs; i++) {
      if ((rc = replay_seg(db, i, i + 1 == db->n_segs, writable))) goto done;
    }
  }
  if (writable && !db->have_key) { rc = fail(db, NGS_MISUSE, "no node key: pass node_seckey or NGS_OPEN_CREATE"); goto done; }
  /* writes go to a segment owned by this node's key */
  if (writable && (db->n_segs == 0 || memcmp(db->segs[db->n_segs - 1].writer, db->pub, 32) != 0)) {
    if ((rc = seg_rotate(db))) goto done;
  }
  rc = NGS_OK;
done:
  free(lp); free(logdir);
  if (rc) db->state_rc = rc;
  return rc;
}

NGS_API int ngs_close(ngs *db) {
  size_t i;
  int rc = NGS_OK, r;
  err_slot *s;
  if (!db) return NGS_OK;
  for (i = 0; i < db->n_segs; i++) {
    if (db->segs[i].f) {
      if (db->segs[i].synced < db->segs[i].size && !db->state_rc) {
        r = db->vfs->sync(db->segs[i].f);
        if (r && !rc) rc = r;
      }
      db->vfs->close(db->segs[i].f);
    }
  }
  if (db->lockf) db->vfs->close(db->lockf);
  for (i = 0; i < db->n_chains; i++) free(db->chains[i].ns);
  ngs__wipe(db->seed, sizeof db->seed);
  free(db->chains); free(db->segs); free(db->facts); free(db->slots); free(db->dir);
  ngs__mutex_free(db->mu);
  s = slot_for(db, 0);
  if (s) { s->db = NULL; s->msg[0] = 0; }
  free(db);
  return rc;
}

NGS_API int ngs_node_pubkey(ngs *db, ngs_pubkey *out) {
  if (!db || !out) return NGS_MISUSE;
  if (db->state_rc) return db->state_rc;
  if (!db->have_key) return fail(db, NGS_NOTFOUND, "no node key on a read-only handle");
  memcpy(out->b, db->pub, 32);
  return NGS_OK;
}

static int sync_active(ngs *db) {
  seg_t *s;
  int rc;
  if (!db->n_segs) return NGS_OK;
  s = &db->segs[db->n_segs - 1];
  if (s->synced == s->size) return NGS_OK;
  if ((rc = db->vfs->sync(s->f))) { db->state_rc = NGS_IOERR; return fail(db, rc, "fsync failed; the handle is now read-only"); }
  s->synced = s->size;
  return NGS_OK;
}

NGS_API int ngs_flush(ngs *db) {
  int rc;
  if (!db) return NGS_MISUSE;
  if (db->state_rc) return db->state_rc;
  ngs__mutex_lock(db->mu);
  clear_err(db);
  rc = sync_active(db);
  ngs__mutex_unlock(db->mu);
  return rc;
}

/* ----------------------------- writing ----------------------------- */
static int validate_in(ngs *db, const ngs_fact_in *src, ngs_fact_in *in) {
  ngs_fact_in d = NGS_FACT_IN_INIT;
  size_t i;
  if (!src || src->size < offsetof(ngs_fact_in, t_event)) return fail(db, NGS_MISUSE, "ngs_fact_in.size too small");
  memcpy(&d, src, src->size < sizeof d ? src->size : sizeof d);
  d.size = sizeof d;
  *in = d;
  if (!str_ok(in->ns) || !str_ok(in->title) || !str_ok(in->body)) return fail(db, NGS_MISUSE, "ngs_str with p == NULL and n > 0");
  if (in->ns.n == 0 || in->ns.n > NGS_MAX_NS_LEN || !utf8_ok(in->ns.p, in->ns.n)) return fail(db, NGS_MISUSE, "ns must be 1..255 bytes of UTF-8");
  if (in->kind < NGS_EPISODIC || in->kind > NGS_PROCEDURAL) return fail(db, NGS_MISUSE, "kind must be EPISODIC, SEMANTIC or PROCEDURAL");
  if (in->title.n > NGS_MAX_TITLE_LEN) return fail(db, NGS_TOOBIG, "title over NGS_MAX_TITLE_LEN");
  if (!utf8_ok(in->title.p, in->title.n)) return fail(db, NGS_MISUSE, "title is not UTF-8");
  if (in->body.n > MAX_BODY) return fail(db, NGS_TOOBIG, "body over 1 MiB");
  if (!utf8_ok(in->body.p, in->body.n)) return fail(db, NGS_MISUSE, "body is not UTF-8");
  if (in->t_event == NGS_TIME_MIN || in->t_event == NGS_TIME_MAX) return fail(db, NGS_MISUSE, "t_event cannot be an unbounded sentinel");
  if (in->valid_from == NGS_TIME_MIN || in->valid_from == NGS_TIME_MAX) return fail(db, NGS_MISUSE, "valid_from cannot be an unbounded sentinel");
  if (in->n_tags && !in->tags) return fail(db, NGS_MISUSE, "n_tags > 0 with tags == NULL");
  for (i = 0; i < in->n_tags; i++) {
    if (!str_ok(in->tags[i]) || in->tags[i].n > NGS_MAX_NS_LEN || !utf8_ok(in->tags[i].p, in->tags[i].n)) return fail(db, NGS_MISUSE, "a tag is not 0..255 bytes of UTF-8");
  }
  if (in->attrs_len > NGS_MAX_ATTRS_LEN) return fail(db, NGS_TOOBIG, "attrs over NGS_MAX_ATTRS_LEN");
  if (in->attrs_len) {
    ngs__rd r;
    if (!in->attrs_cbor) return fail(db, NGS_MISUSE, "attrs_len > 0 with attrs_cbor == NULL");
    r.p = in->attrs_cbor; r.end = in->attrs_cbor + in->attrs_len; r.err = 0;
    if ((in->attrs_cbor[0] >> 5) != 5 || ngs__cbor_skip(&r, 0) || r.p != r.end) return fail(db, NGS_MISUSE, "attrs must be one canonical CBOR map");
  }
  if (!isfinite(in->salience0) || in->salience0 > 1.0f) return fail(db, NGS_MISUSE, "salience0 must be finite and <= 1");
  if (in->n_vecs && !in->vecs) return fail(db, NGS_MISUSE, "n_vecs > 0 with vecs == NULL");
  for (i = 0; i < in->n_vecs; i++) {
    const ngs_vec *v = &in->vecs[i];
    uint32_t j;
    if (!str_ok(v->model_id) || v->model_id.n == 0 || v->dim < 1 || v->dim > NGS_MAX_DIM || !v->v) return fail(db, NGS_MISUSE, "bad vector");
    for (j = 0; j < v->dim; j++) if (!isfinite(v->v[j])) return fail(db, NGS_MISUSE, "vector holds NaN or infinity");
  }
  if (in->n_token_counts && (!in->tokenizer_ids || !in->token_counts)) return fail(db, NGS_MISUSE, "token counts arrays missing");
  for (i = 0; i < in->n_token_counts; i++) if (!str_ok(in->tokenizer_ids[i])) return fail(db, NGS_MISUSE, "bad tokenizer id");
  if (in->supersedes) return fail(db, NGS_MISUSE, "supersedes (invalidation) is outside M1");
  return NGS_OK;
}

/* Encode one fact; returns the encoded fields in *fields for hashing. */
static void encode_fields(ngs__buf *o, const ngs_fact_in *in, const uint8_t writer[32], uint64_t seq,
                          const uint8_t prev[32], ngs_time t_event, ngs_time t_record, ngs_time valid_from) {
  uint8_t bh[32];
  size_t i;
  uint64_t sal = in->salience0 < 0 ? 500000u : (uint64_t)(in->salience0 * 1000000.0f + 0.5f);
  ngs__blake3_hash(in->body.p, in->body.n, bh);
  ngs__cbor_head(o, 5, 16);
  ngs__cbor_uint(o, 1);  ngs__cbor_text(o, in->ns.p, in->ns.n);
  ngs__cbor_uint(o, 2);  ngs__cbor_uint(o, (uint64_t)in->kind);
  ngs__cbor_uint(o, 3);  ngs__cbor_bytes(o, writer, 32);
  ngs__cbor_uint(o, 4);  ngs__cbor_uint(o, seq);
  ngs__cbor_uint(o, 5);  ngs__cbor_bytes(o, prev, 32);
  ngs__cbor_uint(o, 6);  ngs__cbor_int(o, t_event);
  ngs__cbor_uint(o, 7);  ngs__cbor_int(o, t_record);
  ngs__cbor_uint(o, 8);  ngs__cbor_int(o, valid_from);
  ngs__cbor_uint(o, 9);  ngs__cbor_text(o, in->title.p, in->title.n);
  ngs__cbor_uint(o, 10); ngs__cbor_bytes(o, bh, 32);
  ngs__cbor_uint(o, 11); ngs__cbor_head(o, 4, in->n_tags);
  for (i = 0; i < in->n_tags; i++) ngs__cbor_text(o, in->tags[i].p, in->tags[i].n);
  ngs__cbor_uint(o, 12); ngs__cbor_bytes(o, in->attrs_cbor, in->attrs_len);
  ngs__cbor_uint(o, 13); ngs__cbor_uint(o, in->schema);
  ngs__cbor_uint(o, 14); ngs__cbor_uint(o, sal);
  ngs__cbor_uint(o, 15); ngs__cbor_head(o, 4, in->n_vecs);
  for (i = 0; i < in->n_vecs; i++) {
    const ngs_vec *v = &in->vecs[i];
    uint32_t j;
    ngs__cbor_head(o, 4, 4);
    ngs__cbor_text(o, v->model_id.p, v->model_id.n);
    ngs__cbor_uint(o, v->dim);
    ngs__cbor_uint(o, v->version);
    ngs__cbor_head(o, 2, (uint64_t)v->dim * 4u);
    for (j = 0; j < v->dim; j++) {     /* floats by memcpy + explicit LE (SPEC 14) */
      uint32_t u;
      uint8_t le[4];
      memcpy(&u, &v->v[j], 4);
      put_le(le, u, 4);
      ngs__buf_put(o, le, 4);
    }
  }
  ngs__cbor_uint(o, 16); ngs__cbor_head(o, 4, in->n_token_counts);
  for (i = 0; i < in->n_token_counts; i++) {
    ngs__cbor_head(o, 4, 2);
    ngs__cbor_text(o, in->tokenizer_ids[i].p, in->tokenizer_ids[i].n);
    ngs__cbor_uint(o, in->token_counts[i]);
  }
}

typedef struct { ngs_id id; long chain; uint64_t seq; uint64_t off; uint32_t len; ngs_time t_record; } staged_t;

static int remember_locked(ngs *db, const ngs_fact_in *src, size_t n, int32_t flags, ngs_id *out_ids) {
  ngs__buf rec = {0, 0, 0, 0}, fields = {0, 0, 0, 0};
  staged_t *st = NULL;
  ngs_fact_in in;
  size_t i, k;
  int rc = NGS_OK;
  seg_t *s;
  uint64_t base, synced_upto;
  ngs_time now;
  if (!db->have_key || !(db->flags & NGS_OPEN_READWRITE)) return fail(db, NGS_MISUSE, "handle is read-only");
  if (n == 0) return NGS_OK;
  if (n > SIZE_MAX / sizeof *st) return NGS_NOMEM;
  for (i = 0; i < n; i++) if ((rc = validate_in(db, &src[i], &in))) return rc;
  st = (staged_t *)calloc(n, sizeof *st);
  if (!st) return NGS_NOMEM;
  s = &db->segs[db->n_segs - 1];
  if (s->size > SEG_HDR && s->size >= db->seg_bytes) {
    if ((rc = sync_active(db)) || (rc = seg_rotate(db))) goto out;
    s = &db->segs[db->n_segs - 1];
  }
  base = s->size;
  synced_upto = s->synced;
  now = wall_us();
  for (i = 0; i < n; i++) {
    ngs_time t_record, t_event, valid_from;
    uint64_t seq;
    const uint8_t *prev;
    uint8_t sig[64], hdr[5], crcb[4];
    long ck;
    size_t start;
    uint32_t crc;
    validate_in(db, &src[i], &in);
    /* t_record: the engine clock, strictly increasing per writer */
    t_record = now > db->last_t_record ? now : db->last_t_record + 1;
    db->last_t_record = t_record;     /* stays monotonic even if this write fails */
    t_event = in.t_event == NGS_TIME_NOW ? t_record : in.t_event;
    valid_from = in.valid_from == NGS_TIME_NOW ? t_event : in.valid_from;
    ck = chain_get(db, db->pub, in.ns.p, in.ns.n);
    if (ck < 0) { rc = NGS_NOMEM; goto out; }
    seq = db->chains[ck].seq + 1;
    prev = db->chains[ck].last.b;
    for (k = i; k > 0; k--) if (st[k - 1].chain == ck) { seq = st[k - 1].seq + 1; prev = st[k - 1].id.b; break; }
    fields.n = 0;
    encode_fields(&fields, &in, db->pub, seq, prev, t_event, t_record, valid_from);
    if (fields.oom) { rc = NGS_NOMEM; goto out; }
    ngs__blake3_hash(fields.p, fields.n, st[i].id.b);
    ngs__ed25519_sign(sig, st[i].id.b, 32, db->seed, db->pub);
    /* record: len | type | payload | crc */
    start = rec.n;
    ngs__buf_put(&rec, hdr, 5);                 /* patched below */
    ngs__cbor_head(&rec, 4, 5);
    ngs__buf_put(&rec, fields.p, fields.n);
    ngs__cbor_bytes(&rec, sig, 64);
    ngs__cbor_bytes(&rec, in.body.p, in.body.n);
    ngs__cbor_uint(&rec, (uint64_t)(n - 1 - i));
    ngs__cbor_uint(&rec, synced_upto);
    if (rec.oom) { rc = NGS_NOMEM; goto out; }
    if (rec.n - start - 5 > 0xffffffffu - REC_OVERHEAD) { rc = fail(db, NGS_TOOBIG, "record too large"); goto out; }
    put_le(rec.p + start, (uint64_t)(rec.n - start - 5), 4);
    rec.p[start + 4] = REC_FACT;
    crc = ngs__crc32c(0, rec.p + start + 4, rec.n - start - 4);
    put_le(crcb, crc, 4);
    ngs__buf_put(&rec, crcb, 4);
    if (rec.oom) { rc = NGS_NOMEM; goto out; }
    st[i].chain = ck; st[i].seq = seq; st[i].off = base + start;
    st[i].len = (uint32_t)(rec.n - start); st[i].t_record = t_record;
  }
  /* one write for the whole batch, then the sync that makes it durable */
  rc = db->vfs->pwrite(s->f, rec.p, rec.n, base);
  if (rc == 0 && !(flags & NGS_WRITE_NO_SYNC)) rc = db->vfs->sync(s->f);
  if (rc) {
    /* Nothing was acknowledged. Cut the partial write back off so the log
    ** stays a clean prefix; if even that fails the handle stops writing. */
    if (db->vfs->truncate(s->f, base) != 0) db->state_rc = NGS_IOERR;
    rc = fail(db, rc, "write or fsync failed; nothing from this call was committed");
    goto out;
  }
  s->size = base + rec.n;
  if (!(flags & NGS_WRITE_NO_SYNC)) s->synced = s->size;
  for (i = 0; i < n; i++) {
    fact_ref r;
    chain_t *c = &db->chains[st[i].chain];
    c->seq = st[i].seq;
    c->last = st[i].id;
    r.id = st[i].id; r.seg = (uint32_t)(db->n_segs - 1); r.off = st[i].off; r.len = st[i].len;
    r.t_record = st[i].t_record; r.chain = (uint32_t)st[i].chain;
    if ((rc = idx_add(db, &r))) { db->state_rc = rc; goto out; }
    if (out_ids) out_ids[i] = st[i].id;
  }
out:
  ngs__buf_free(&rec);
  ngs__buf_free(&fields);
  free(st);
  return rc;
}

NGS_API int ngs_remember_many(ngs *db, const ngs_fact_in *in, size_t n, int32_t flags, ngs_id *out_ids) {
  int rc;
  if (!db || (!in && n)) return NGS_MISUSE;
  if (db->state_rc) return db->state_rc;
  if (flags & ~NGS_WRITE_NO_SYNC) return fail(db, NGS_MISUSE, "unknown write flags");
  ngs__mutex_lock(db->mu);
  clear_err(db);
  rc = remember_locked(db, in, n, flags, out_ids);
  ngs__mutex_unlock(db->mu);
  return rc;
}

NGS_API int ngs_remember(ngs *db, const ngs_fact_in *in, int32_t flags, ngs_id *out_id) {
  if (!in) return NGS_MISUSE;
  return ngs_remember_many(db, in, 1, flags, out_id);
}

/* ----------------------------- reading ----------------------------- */
#define ALIGN16(x) (((x) + 15u) & ~(size_t)15u)

/* Read, check and decode the record behind a fact_ref. */
static int load_record(ngs *db, const fact_ref *r, uint8_t **buf, dec_t *d, int check_sig) {
  uint8_t *b;
  size_t got;
  int rc;
  ngs_id id;
  uint64_t len;
  *buf = NULL;
  b = (uint8_t *)malloc(r->len);
  if (!b) return NGS_NOMEM;
  if ((rc = db->vfs->pread(db->segs[r->seg].f, b, r->len, r->off, &got))) { free(b); return rc; }
  len = get_le(b, 4);
  if (got != r->len || len + REC_OVERHEAD != r->len || b[4] != REC_FACT ||
      get_le(b + 5 + len, 4) != ngs__crc32c(0, b + 4, (size_t)len + 1) ||
      decode_fact(b + 5, (size_t)len, d) != 0) { free(b); return fail(db, NGS_CORRUPT, "stored record fails its CRC or decode"); }
  ngs__blake3_hash(d->fields, d->fields_len, id.b);
  if (memcmp(id.b, r->id.b, 32) != 0) { free(b); return fail(db, NGS_CORRUPT, "stored record hashes to a different id"); }
  if (check_sig && ngs__ed25519_verify(d->sig, id.b, 32, d->writer) != 0) { free(b); return fail(db, NGS_CORRUPT, "signature does not verify"); }
  *buf = b;
  return NGS_OK;
}

static int build_fact(const fact_ref *r, const dec_t *d, ngs_fact **out) {
  size_t sz = ALIGN16(sizeof(ngs_fact)), o_tags, o_ns, o_title, o_body, o_attrs, o_tagtxt;
  size_t tag_txt = 0;
  uint64_t i;
  ngs__rd rd;
  uint8_t *p;
  ngs_fact *f;
  ngs_str *tags;
  char *tp;
  if (d->n_tags > (SIZE_MAX / 2) / sizeof(ngs_str)) return NGS_NOMEM;
  rd.p = d->tags; rd.end = d->tags + d->tags_len; rd.err = 0;
  for (i = 0; i < d->n_tags; i++) { const char *t; size_t tl; ngs__cbor_get_text(&rd, &t, &tl); tag_txt += tl + 1; }
  o_tags = sz;   sz = ALIGN16(sz + (size_t)d->n_tags * sizeof(ngs_str));
  o_ns = sz;     sz += d->ns_len + 1;
  o_title = sz;  sz += d->title_len + 1;
  o_body = sz;   sz += d->body_len + 1;
  o_tagtxt = sz; sz += tag_txt;
  sz = ALIGN16(sz);
  o_attrs = sz;  sz += d->attrs_len + 1;
  p = (uint8_t *)calloc(1, sz);
  if (!p) return NGS_NOMEM;
  f = (ngs_fact *)p;
  f->size = sizeof *f;
  f->id = r->id;
  memcpy(p + o_ns, d->ns, d->ns_len);         f->ns.p = (const char *)p + o_ns; f->ns.n = d->ns_len;
  f->kind = (int32_t)d->kind;
  memcpy(f->writer.b, d->writer, 32);
  f->seq = d->seq;
  f->t_event = d->t_event; f->t_record = d->t_record; f->valid_from = d->valid_from;
  f->valid_to = NGS_TIME_MAX;
  memcpy(p + o_title, d->title, d->title_len); f->title.p = (const char *)p + o_title; f->title.n = d->title_len;
  if (d->body_len) memcpy(p + o_body, d->body, d->body_len);
  f->body.p = (const char *)p + o_body; f->body.n = d->body_len;
  tags = (ngs_str *)(p + o_tags);
  tp = (char *)p + o_tagtxt;
  rd.p = d->tags; rd.end = d->tags + d->tags_len; rd.err = 0;
  for (i = 0; i < d->n_tags; i++) {
    const char *t; size_t tl;
    ngs__cbor_get_text(&rd, &t, &tl);
    memcpy(tp, t, tl); tags[i].p = tp; tags[i].n = tl; tp += tl + 1;
  }
  f->tags = d->n_tags ? tags : NULL; f->n_tags = (size_t)d->n_tags;
  if (d->attrs_len) memcpy(p + o_attrs, d->attrs, d->attrs_len);
  f->attrs_cbor = d->attrs_len ? p + o_attrs : NULL; f->attrs_len = d->attrs_len;
  f->schema = (uint16_t)d->schema;
  *out = f;
  return NGS_OK;
}

NGS_API int ngs_get(ngs *db, const ngs_id *id, ngs_fact **out) {
  long k;
  int rc;
  uint8_t *b;
  dec_t d;
  if (!db || !id || !out) return NGS_MISUSE;
  *out = NULL;
  if (db->state_rc && db->state_rc != NGS_IOERR) return db->state_rc;
  ngs__mutex_lock(db->mu);
  clear_err(db);
  k = idx_find(db, id);
  if (k < 0) { rc = NGS_NOTFOUND; goto done; }
  if ((rc = load_record(db, &db->facts[k], &b, &d, 0))) goto done;
  rc = build_fact(&db->facts[k], &d, out);
  free(b);
done:
  ngs__mutex_unlock(db->mu);
  return rc;
}

/* ----------------------------- scanning ----------------------------- */
NGS_API int ngs_scan(ngs *db, const ngs_scan_opts *o, ngs_iter **it) {
  ngs_scan_opts so = NGS_SCAN_OPTS_INIT;
  ngs_iter *x;
  if (!db || !it) return NGS_MISUSE;
  *it = NULL;
  if (db->state_rc && db->state_rc != NGS_IOERR) return db->state_rc;
  if (o) {
    if (o->size < offsetof(ngs_scan_opts, writer)) return fail(db, NGS_MISUSE, "ngs_scan_opts.size too small");
    memcpy(&so, o, o->size < sizeof so ? o->size : sizeof so);
    so.size = sizeof so;
  }
  if (!str_ok(so.ns)) return fail(db, NGS_MISUSE, "ns with p == NULL and n > 0");
  x = (ngs_iter *)calloc(1, sizeof *x);
  if (!x) return NGS_NOMEM;
  x->db = db;
  x->o = so;
  if (so.ns.n) {
    x->ns_copy = (char *)malloc(so.ns.n);
    if (!x->ns_copy) { free(x); return NGS_NOMEM; }
    memcpy(x->ns_copy, so.ns.p, so.ns.n);
    x->o.ns.p = x->ns_copy;
  }
  if (so.writer) { x->writer = *so.writer; x->has_writer = 1; x->o.writer = NULL; }
  *it = x;
  return NGS_OK;
}

NGS_API int ngs_iter_next(ngs_iter *x, ngs_fact **out) {
  ngs *db;
  int rc = NGS_NOTFOUND;
  if (!x || !out) return NGS_MISUSE;
  *out = NULL;
  db = x->db;
  ngs__mutex_lock(db->mu);
  while (x->pos < db->n_facts) {
    const fact_ref *r = &db->facts[x->pos++];
    const chain_t *c = &db->chains[r->chain];
    uint8_t *b;
    dec_t d;
    if (r->t_record < x->o.since || r->t_record > x->o.until) continue;
    if (x->o.ns.n && (c->ns_len != x->o.ns.n || memcmp(c->ns, x->o.ns.p, c->ns_len) != 0)) continue;
    if (x->has_writer && memcmp(c->writer, x->writer.b, 32) != 0) continue;
    if ((rc = load_record(db, r, &b, &d, 0))) break;
    rc = build_fact(r, &d, out);
    free(b);
    break;
  }
  ngs__mutex_unlock(db->mu);
  return rc;
}

NGS_API void ngs_iter_close(ngs_iter *x) {
  if (!x) return;
  free(x->ns_copy);
  free(x);
}

/* ----------------------------- verify ----------------------------- */
/* Full re-read of the log from disk: CRC, decode, id, signature, chain and
** agreement with the in-memory index. A checkpoint argument is outside M1. */
NGS_API int ngs_verify(ngs *db, const uint8_t *ckpt, size_t len) {
  size_t si, fi = 0;
  int rc = NGS_OK;
  chain_t *seen = NULL;
  size_t n_seen = 0, cap_seen = 0, i;
  if (!db) return NGS_MISUSE;
  if (ckpt || len) return fail(db, NGS_MISUSE, "checkpoint verification is outside M1");
  if (db->state_rc && db->state_rc != NGS_IOERR) return db->state_rc;
  ngs__mutex_lock(db->mu);
  clear_err(db);
  for (si = 0; si < db->n_segs && rc == NGS_OK; si++) {
    seg_t *s = &db->segs[si];
    uint8_t *b = NULL;
    size_t off = SEG_HDR, n = (size_t)s->size;
    if ((rc = read_all(db, s->f, s->size, &b))) break;
    if (n < SEG_HDR || !seg_header_ok(b) || memcmp(b + 20, s->writer, 32) != 0) { free(b); rc = fail(db, NGS_CORRUPT, "segment header damaged"); break; }
    while (off < n) {
      uint64_t L;
      dec_t d;
      ngs_id id;
      chain_t *cur = NULL;
      if (n - off < REC_OVERHEAD) { rc = fail(db, NGS_CORRUPT, "short record"); break; }
      L = get_le(b + off, 4);
      if (L < 1 || L > n - off - REC_OVERHEAD || b[off + 4] != REC_FACT ||
          get_le(b + off + 5 + L, 4) != ngs__crc32c(0, b + off + 4, (size_t)L + 1)) { rc = fail(db, NGS_CORRUPT, "record CRC failed"); break; }
      if (decode_fact(b + off + 5, (size_t)L, &d)) { rc = fail(db, NGS_CORRUPT, "record does not decode"); break; }
      ngs__blake3_hash(d.fields, d.fields_len, id.b);
      if (ngs__ed25519_verify(d.sig, id.b, 32, d.writer) != 0) { rc = fail(db, NGS_CORRUPT, "signature does not verify"); break; }
      if (fi >= db->n_facts || memcmp(db->facts[fi].id.b, id.b, 32) != 0 ||
          db->facts[fi].seg != si || db->facts[fi].off != off) { rc = fail(db, NGS_CORRUPT, "log and index disagree"); break; }
      for (i = 0; i < n_seen; i++) {
        if (seen[i].ns_len == d.ns_len && memcmp(seen[i].writer, d.writer, 32) == 0 && memcmp(seen[i].ns, d.ns, d.ns_len) == 0) { cur = &seen[i]; break; }
      }
      if (!cur) {
        if (grow((void **)&seen, &cap_seen, n_seen + 1, sizeof *seen)) { rc = NGS_NOMEM; break; }
        memset(&seen[n_seen], 0, sizeof *seen);
        memcpy(seen[n_seen].writer, d.writer, 32);
        seen[n_seen].ns = (char *)malloc(d.ns_len ? d.ns_len : 1);
        if (!seen[n_seen].ns) { rc = NGS_NOMEM; break; }
        memcpy(seen[n_seen].ns, d.ns, d.ns_len);
        seen[n_seen].ns_len = d.ns_len;
        cur = &seen[n_seen++];
      }
      if (d.seq != cur->seq + 1 || memcmp(d.prev, cur->last.b, 32) != 0) { rc = fail(db, NGS_CORRUPT, "hash chain broken"); break; }
      cur->seq = d.seq;
      cur->last = id;
      fi++;
      off += (size_t)L + REC_OVERHEAD;
    }
    free(b);
  }
  if (rc == NGS_OK && fi != db->n_facts) rc = fail(db, NGS_CORRUPT, "facts missing from the log");
  for (i = 0; i < n_seen; i++) free(seen[i].ns);
  free(seen);
  ngs__mutex_unlock(db->mu);
  return rc;
}

/* ----------------------------- stats ----------------------------- */
NGS_API int ngs_stats(ngs *db, ngs_stats_t *out) {
  ngs_stats_t s = NGS_STATS_INIT;
  size_t i;
  if (!db || !out || out->size < sizeof(uint32_t) + sizeof(uint64_t)) return NGS_MISUSE;
  ngs__mutex_lock(db->mu);
  s.facts = db->n_facts;
  for (i = 0; i < db->n_segs; i++) s.log_bytes += db->segs[i].size;
  ngs__mutex_unlock(db->mu);
  {
    uint32_t want = out->size;
    memset(out, 0, want);
    memcpy(out, &s, want < sizeof s ? want : sizeof s);
    out->size = want;
  }
  return NGS_OK;
}

/* ----------------------- outside M1: NGS_MISUSE ----------------------- */
static int not_m1(ngs *db) { return db ? fail(db, NGS_MISUSE, "not implemented in M1") : NGS_MISUSE; }
NGS_API int ngs_invalidate(ngs *db, const ngs_id *id, ngs_str reason) { (void)id; (void)reason; return not_m1(db); }
NGS_API int ngs_link(ngs *db, const ngs_id *a, const ngs_id *b, ngs_str rel, float weight, ngs_id *out) { (void)a; (void)b; (void)rel; (void)weight; (void)out; return not_m1(db); }
NGS_API int ngs_redact(ngs *db, const ngs_id *id, ngs_str reason) { (void)id; (void)reason; return not_m1(db); }
NGS_API int ngs_grant(ngs *db, ngs_str ns, const ngs_pubkey *w, ngs_id *out) { (void)ns; (void)w; (void)out; return not_m1(db); }
NGS_API int ngs_recall(ngs *db, const ngs_query *q, ngs_results **out) { (void)q; if (out) *out = NULL; return not_m1(db); }
NGS_API int ngs_as_of(ngs *db, ngs_time a, ngs_time b, const ngs_query *q, ngs_results **out) { (void)a; (void)b; (void)q; if (out) *out = NULL; return not_m1(db); }
NGS_API int ngs_mark(ngs *db, const ngs_id *id, int32_t mark) { (void)id; (void)mark; return not_m1(db); }
NGS_API int ngs_checkpoint(ngs *db, uint8_t **c, size_t *len) { (void)c; (void)len; return not_m1(db); }
NGS_API int ngs_rebuild(ngs *db) { return not_m1(db); }
NGS_API int ngs_heads(ngs *db, ngs_head **h, size_t *n) { (void)h; (void)n; return not_m1(db); }
NGS_API int ngs_sync_export(ngs *db, const ngs_head *s, size_t n, uint8_t **seg, size_t *len) { (void)s; (void)n; (void)seg; (void)len; return not_m1(db); }
NGS_API int ngs_sync_import(ngs *db, const uint8_t *seg, size_t len, ngs_sync_report **r) { (void)seg; (void)len; if (r) *r = NULL; return not_m1(db); }
