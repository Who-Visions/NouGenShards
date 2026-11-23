/* SPDX-License-Identifier: Apache-2.0 */
/*
** log.c -- the NGS M1 core: signed, hash-chained, append-only log.
**
**   log/NNNNNN.seg   segment: 64 B header, then frames  u32 len | u8 type | payload | u32 crc32c
**   LOCK             single-writer lock
**   NODEKEY          node secret key (64 B) + public key (32 B), created by NGS_OPEN_CREATE
**
** Durability: every commit is ONE pwrite of all its frames followed by fsync. A batch
** (ngs_remember_many) marks every frame but the last with NGS_REC_PENDING, so a torn batch
** is a run of pending frames with no closing frame and is discarded whole on open.
**
** Recovery: the last segment may end in a torn tail. The first bad record there (short,
** oversize or CRC failure) and everything after it is cut, a copy of the cut bytes is kept in
** <segment>.torn, and ngs_errmsg() reports it. A bad record in any earlier segment, a chain break,
** an id or header mismatch is NGS_CORRUPT and the open is refused. M1 has no manifest, so it
** cannot tell a torn write from media damage inside the last segment; SPEC 3.2's manifest
** (M2) gives that distinction a durable watermark.
*/
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ngs_int.h"

#define DEF_SEG_BYTES   (64ull * 1024ull * 1024ull)
#define FR_BAD          (-1)

typedef struct { uint32_t num; ngs_file *f; uint64_t size; uint64_t first_ord; uint8_t writer[32]; } seg_t;
typedef struct { uint8_t id[32]; uint32_t seg; uint32_t len; uint64_t off; uint32_t head; int64_t t_record; } ent_t;
typedef struct { char *ns; size_t nslen; uint64_t seq; uint8_t last[32]; } head_t;
typedef struct { head_t *h; size_t n, cap; } chain_t;

struct ngs {
  uint64_t gen;
  ngs_vfs *vfs;
  ngs_mutex *mu;
  char *dir, *logdir;
  int failed, ro, broken, registered, have_key;
  char err[200];
  uint8_t sk[64], pk[32];
  ngs_file *lockf;
  uint64_t seg_limit;
  seg_t *segs; size_t nsegs, capsegs;
  ent_t *ents; size_t nents, capents;
  uint32_t *htab; size_t hcap;
  chain_t chain;
  uint64_t ord;
  int64_t last_t;
  unsigned iters;
};

struct ngs_iter {
  ngs *db;
  size_t pos, end;
  char *ns; size_t nslen;
  int have_writer; uint8_t writer[32];
  int64_t since, until;
};

/* ------------------------------------------------------------ errors */
/* keyed by a never-reused handle generation, not the pointer: a freed handle's address can be reused */
static _Thread_local struct { uint64_t gen; char msg[200]; } tls_err;
static uint64_t g_gen;

static int fail(const ngs *db, int rc, const char *msg) {
  tls_err.gen = db->gen;
  snprintf(tls_err.msg, sizeof tls_err.msg, "%s", msg);
  return rc;
}

const char *ngs_errmsg(ngs *db) {
  if (!db) return "";
  if (db->failed) return db->err;
  return tls_err.gen == db->gen ? tls_err.msg : "";
}

static int open_fail(ngs *db, int rc, const char *msg) {
  db->failed = 1;
  snprintf(db->err, sizeof db->err, "%s", msg);
  return rc;
}

/* -------------------------------------------------------- small helpers */
static uint32_t le32(const uint8_t *d) { return (uint32_t)d[0] | ((uint32_t)d[1] << 8) | ((uint32_t)d[2] << 16) | ((uint32_t)d[3] << 24); }
static uint64_t le64(const uint8_t *d) { uint64_t v = 0; int i; for (i = 7; i >= 0; i--) v = (v << 8) | d[i]; return v; }

static char *dup_n(const char *s, size_t n) {
  char *p = (char *)malloc(n + 1);
  if (p) { if (n) memcpy(p, s, n); p[n] = 0; }
  return p;
}

static int path_join(char **out, const char *a, const char *b) {
  size_t la = strlen(a), lb = strlen(b);
  char *p;
  if (la > SIZE_MAX - lb - 2) return NGS_NOMEM;
  p = (char *)malloc(la + lb + 2);
  if (!p) return NGS_NOMEM;
  memcpy(p, a, la); p[la] = '/'; memcpy(p + la + 1, b, lb); p[la + 1 + lb] = 0;
  *out = p;
  return NGS_OK;
}

static int seg_path(const ngs *db, uint32_t num, char **out) {
  char name[32];
  snprintf(name, sizeof name, "%06u.seg", (unsigned)num);
  return path_join(out, db->logdir, name);
}

static int str_ok(ngs_str s) { return s.p != NULL || s.n == 0; }

/* ------------------------------------------------------ open-dir table */
static char **g_dirs;
static size_t g_ndirs;

static int dir_register(const char *dir) {
  size_t i;
  char **nd, *c;
  int rc = NGS_OK;
  ngs__global_lock();
  for (i = 0; i < g_ndirs; i++) if (strcmp(g_dirs[i], dir) == 0) { rc = NGS_BUSY; break; }
  if (rc == NGS_OK) {
    c = dup_n(dir, strlen(dir));
    nd = c ? (char **)realloc(g_dirs, (g_ndirs + 1) * sizeof *nd) : NULL;
    if (!c || !nd) { free(c); rc = NGS_NOMEM; }
    else { g_dirs = nd; g_dirs[g_ndirs++] = c; }
  }
  ngs__global_unlock();
  return rc;
}

static void dir_unregister(const char *dir) {
  size_t i;
  ngs__global_lock();
  for (i = 0; i < g_ndirs; i++) {
    if (strcmp(g_dirs[i], dir) == 0) {
      free(g_dirs[i]);
      g_dirs[i] = g_dirs[--g_ndirs];
      break;
    }
  }
  ngs__global_unlock();
}

/* -------------------------------------------------- chain (ns -> head) */
static int chain_find(const chain_t *c, const uint8_t *ns, size_t n) {
  size_t i;
  for (i = 0; i < c->n; i++) if (c->h[i].nslen == n && memcmp(c->h[i].ns, ns, n) == 0) return (int)i;
  return -1;
}

static int chain_set(chain_t *c, const uint8_t *ns, size_t n, uint64_t seq, const uint8_t last[32], uint32_t *idx) {
  int i = chain_find(c, ns, n);
  if (i < 0) {
    head_t *nh;
    char *d;
    if (c->n == c->cap) {
      size_t nc = c->cap ? c->cap * 2 : 8;
      nh = (head_t *)realloc(c->h, nc * sizeof *nh);
      if (!nh) return NGS_NOMEM;
      c->h = nh; c->cap = nc;
    }
    d = dup_n((const char *)ns, n);
    if (!d) return NGS_NOMEM;
    c->h[c->n].ns = d; c->h[c->n].nslen = n;
    i = (int)c->n++;
  }
  c->h[i].seq = seq;
  memcpy(c->h[i].last, last, 32);
  if (idx) *idx = (uint32_t)i;
  return NGS_OK;
}

static void chain_free(chain_t *c) {
  size_t i;
  for (i = 0; i < c->n; i++) free(c->h[i].ns);
  free(c->h);
  c->h = NULL; c->n = c->cap = 0;
}

/* ------------------------------------------------------- id hash table */
static size_t ht_slot(const uint8_t id[32], size_t cap) { return (size_t)(le64(id) & (uint64_t)(cap - 1)); }

static int ht_grow(ngs *db) {
  size_t ncap = db->hcap ? db->hcap * 2 : 1024, i;
  uint32_t *nt = (uint32_t *)calloc(ncap, sizeof *nt);
  if (!nt) return NGS_NOMEM;
  for (i = 0; i < db->nents; i++) {
    size_t s = ht_slot(db->ents[i].id, ncap);
    while (nt[s]) s = (s + 1) & (ncap - 1);
    nt[s] = (uint32_t)(i + 1);
  }
  free(db->htab);
  db->htab = nt; db->hcap = ncap;
  return NGS_OK;
}

static int ht_find(const ngs *db, const uint8_t id[32], size_t *out) {
  size_t s;
  if (!db->hcap) return 0;
  s = ht_slot(id, db->hcap);
  while (db->htab[s]) {
    size_t e = db->htab[s] - 1;
    if (memcmp(db->ents[e].id, id, 32) == 0) { *out = e; return 1; }
    s = (s + 1) & (db->hcap - 1);
  }
  return 0;
}

/* appends the entry; the caller has checked the id is new */
static int ent_add(ngs *db, const ent_t *e) {
  size_t s;
  if (db->nents == db->capents) {
    size_t nc = db->capents ? db->capents * 2 : 1024;
    ent_t *ne = (ent_t *)realloc(db->ents, nc * sizeof *ne);
    if (!ne) return NGS_NOMEM;
    db->ents = ne; db->capents = nc;
  }
  if ((db->nents + 1) * 2 > db->hcap) { int rc = ht_grow(db); if (rc) return rc; }
  db->ents[db->nents] = *e;
  s = ht_slot(e->id, db->hcap);
  while (db->htab[s]) s = (s + 1) & (db->hcap - 1);
  db->htab[s] = (uint32_t)(db->nents + 1);
  db->nents++;
  return NGS_OK;
}

/* ----------------------------------------------------------- frame I/O */
static int ensure_cap(ngs_buf *b, size_t need) {
  uint8_t *np;
  if (need <= b->cap) return NGS_OK;
  np = (uint8_t *)realloc(b->p, need);
  if (!np) return NGS_NOMEM;
  b->p = np; b->cap = need;
  return NGS_OK;
}

/* 0 = good frame (payload in b->p, b->n = len, *flen = whole frame size); FR_BAD = short,
** oversize or bad CRC; any positive code is an I/O or memory error. `limit` is the logical end. */
static int read_frame_at(ngs_file *f, uint64_t off, uint64_t limit, uint8_t *type, ngs_buf *b, uint64_t *flen) {
  uint8_t h[5];
  size_t got = 0;
  uint32_t len, crc;
  uint64_t rem;
  int rc;
  if (off > limit) return FR_BAD;
  rem = limit - off;
  if (rem < NGS_FRAME_OVERHEAD) return FR_BAD;
  rc = f->vfs->pread(f, h, 5, off, &got);
  if (rc) return rc;
  if (got != 5) return FR_BAD;
  len = le32(h);
  if (len > NGS_MAX_REC || rem < (uint64_t)NGS_FRAME_OVERHEAD + len) return FR_BAD;
  rc = ensure_cap(b, (size_t)len + 4);
  if (rc) return rc;
  rc = f->vfs->pread(f, b->p, (size_t)len + 4, off + 5, &got);
  if (rc) return rc;
  if (got != (size_t)len + 4) return FR_BAD;
  crc = ngs__crc32c(ngs__crc32c(0, &h[4], 1), b->p, len);
  if (crc != le32(b->p + len)) return FR_BAD;
  *type = h[4];
  b->n = len;
  *flen = (uint64_t)NGS_FRAME_OVERHEAD + len;
  return NGS_OK;
}

/* ------------------------------------------------------------ recovery */
typedef struct { uint32_t *v; size_t n, cap; } numlist;

static int collect_seg(void *arg, const char *name) {
  numlist *l = (numlist *)arg;
  size_t i, len = strlen(name);
  uint32_t v = 0;
  if (len != 10 || strcmp(name + 6, ".seg") != 0) return NGS_OK;          /* ignores *.torn and strangers */
  for (i = 0; i < 6; i++) {
    if (name[i] < '0' || name[i] > '9') return NGS_OK;
    v = v * 10u + (uint32_t)(name[i] - '0');
  }
  if (l->n == l->cap) {
    size_t nc = l->cap ? l->cap * 2 : 8;
    uint32_t *nv = (uint32_t *)realloc(l->v, nc * sizeof *nv);
    if (!nv) return NGS_NOMEM;
    l->v = nv; l->cap = nc;
  }
  l->v[l->n++] = v;
  return NGS_OK;
}

typedef struct { uint8_t id[32]; uint64_t off; uint32_t len; int64_t t_record; char *ns; size_t nslen; uint64_t seq; } tent_t;

static void tents_free(tent_t *t, size_t n) {
  size_t i;
  for (i = 0; i < n; i++) free(t[i].ns);
}

static int push_seg(ngs *db, const seg_t *s) {
  if (db->nsegs == db->capsegs) {
    size_t nc = db->capsegs ? db->capsegs * 2 : 4;
    seg_t *ns = (seg_t *)realloc(db->segs, nc * sizeof *ns);
    if (!ns) return NGS_NOMEM;
    db->segs = ns; db->capsegs = nc;
  }
  db->segs[db->nsegs++] = *s;
  return NGS_OK;
}

static void note_tail(ngs *db, uint32_t num, uint64_t bytes) {
  char m[200];
  snprintf(m, sizeof m, "recovered: cut %llu torn bytes from %06u.seg (kept in %06u.seg.torn)",
           (unsigned long long)bytes, (unsigned)num, (unsigned)num);
  (void)fail(db, NGS_OK, m);
}

/* Cut the tail [T, size) of the last segment: keep a copy, truncate, make it durable. */
static void cut_tail(ngs *db, seg_t *s, uint64_t T, uint64_t size) {
  char *tp = NULL, *p2 = NULL;
  ngs_file *tf = NULL;
  uint8_t *buf = NULL;
  size_t got = 0;
  if (seg_path(db, s->num, &tp) == NGS_OK) {
    size_t l = strlen(tp);
    p2 = (char *)malloc(l + 6);
    if (p2) { memcpy(p2, tp, l); memcpy(p2 + l, ".torn", 6); }
    free(tp);
  }
  if (p2 && size - T <= (64u * 1024u * 1024u)) {                       /* evidence copy, best effort */
    buf = (uint8_t *)malloc((size_t)(size - T));
    if (buf && s->f->vfs->pread(s->f, buf, (size_t)(size - T), T, &got) == NGS_OK && got == (size_t)(size - T)) {
      if (db->vfs->open(db->vfs, p2, NGS_VF_RDWR | NGS_VF_CREATE, &tf) == NGS_OK) {
        (void)tf->vfs->truncate(tf, 0);
        if (tf->vfs->pwrite(tf, buf, got, 0) == NGS_OK) (void)tf->vfs->fsync(tf);
        (void)tf->vfs->close(tf);
      }
    }
  }
  free(buf); free(p2);
}

static int recover(ngs *db, const uint32_t *nums, size_t n) {
  ngs_buf pay = { NULL, 0, 0 };
  tent_t *tent = NULL;
  size_t ntent = 0, captent = 0, i;
  uint8_t first_writer[32];
  int have_writer = 0, rc = NGS_OK;
  for (i = 0; i < n && rc == NGS_OK; i++) {
    int last = (i == n - 1);
    seg_t s;
    char *path = NULL;
    uint8_t hdr[NGS_SEG_HDR];
    uint64_t size = 0, off, batch_off = 0, T;
    size_t got = 0, seg_idx;
    int hdr_ok, in_batch = 0, tail = 0;
    ngs_file *f = NULL;
    memset(&s, 0, sizeof s);
    s.num = nums[i];
    rc = seg_path(db, s.num, &path);
    if (rc) break;
    rc = db->vfs->open(db->vfs, path, (!db->ro && last) ? NGS_VF_RDWR : NGS_VF_RDONLY, &f);
    if (rc) { free(path); rc = open_fail(db, rc, "cannot open a segment"); break; }
    rc = f->vfs->size(f, &size);
    if (!rc) rc = f->vfs->pread(f, hdr, size < NGS_SEG_HDR ? (size_t)size : NGS_SEG_HDR, 0, &got);
    if (rc) { f->vfs->close(f); free(path); rc = open_fail(db, NGS_IOERR, "cannot read a segment"); break; }
    hdr_ok = (size >= NGS_SEG_HDR && got == NGS_SEG_HDR && ngs__seg_hdr_decode(hdr, &s.first_ord, s.writer) == NGS_OK);
    if (!hdr_ok) {
      if (last) {                                                 /* torn segment creation: no records yet */
        f->vfs->close(f);
        if (!db->ro) (void)db->vfs->unlink(db->vfs, path);
        free(path);
        break;
      }
      f->vfs->close(f); free(path);
      rc = open_fail(db, NGS_CORRUPT, "segment header is damaged");
      break;
    }
    free(path);
    s.f = f;
    if (s.first_ord != db->ord) { rc = open_fail(db, NGS_CORRUPT, "segment ordinal does not continue the log"); f->vfs->close(f); break; }
    if (have_writer && memcmp(first_writer, s.writer, 32) != 0) { rc = open_fail(db, NGS_CORRUPT, "segments name different writers"); f->vfs->close(f); break; }
    if (!have_writer) { memcpy(first_writer, s.writer, 32); have_writer = 1; }
    if (!db->ro && memcmp(s.writer, db->pk, 32) != 0) { rc = open_fail(db, NGS_NOGRANT, "node key is not the writer of this database"); f->vfs->close(f); break; }
    s.size = size;
    rc = push_seg(db, &s);
    if (rc) { f->vfs->close(f); rc = open_fail(db, NGS_NOMEM, "out of memory"); break; }
    seg_idx = db->nsegs - 1;
    off = NGS_SEG_HDR;
    T = size;
    for (;;) {
      uint8_t type;
      uint64_t flen = 0;
      ngs_rec r;
      int fr, pend;
      int64_t prev_t;
      uint64_t want_seq;
      const uint8_t *want_prev;
      static const uint8_t zero32[32] = { 0 };
      size_t k;
      if (off == size) break;
      fr = read_frame_at(f, off, size, &type, &pay, &flen);
      if (fr > 0) { rc = open_fail(db, fr, "I/O error while reading the log"); break; }
      if (fr == FR_BAD) { tail = 1; T = in_batch ? batch_off : off; break; }
      pend = (type & NGS_REC_PENDING) != 0;
      type = (uint8_t)(type & 0x7Fu);
      if (type == NGS_REC_PAD) { off += flen; continue; }
      if (type != NGS_REC_FACT) { rc = open_fail(db, NGS_CORRUPT, "unknown record type"); break; }
      if (ngs__rec_decode(pay.p, pay.n, &r) != NGS_OK) { rc = open_fail(db, NGS_CORRUPT, "record does not decode in canonical form"); break; }
      if (memcmp(r.writer, s.writer, 32) != 0) { rc = open_fail(db, NGS_CORRUPT, "record writer differs from its segment"); break; }
      if (ngs__rec_check_id(&r) != NGS_OK) { rc = open_fail(db, NGS_CORRUPT, "record id does not match its content"); break; }
      /* continuity against the tentative batch first, then the committed chain */
      want_seq = 1; want_prev = zero32; prev_t = db->last_t;
      {
        int ci = chain_find(&db->chain, r.ns, r.ns_len);
        if (ci >= 0) { want_seq = db->chain.h[ci].seq + 1; want_prev = db->chain.h[ci].last; }
      }
      if (ntent) prev_t = tent[ntent - 1].t_record;
      for (k = ntent; k > 0; k--) {
        if (tent[k - 1].nslen == r.ns_len && memcmp(tent[k - 1].ns, r.ns, r.ns_len) == 0) { want_seq = tent[k - 1].seq + 1; want_prev = tent[k - 1].id; break; }
      }
      if (r.seq != want_seq || memcmp(r.prev, want_prev, 32) != 0) { rc = open_fail(db, NGS_CORRUPT, "sequence or previous-hash chain is broken"); break; }
      if (r.t_record <= prev_t && (db->ord > 0 || ntent > 0)) { rc = open_fail(db, NGS_CORRUPT, "record time goes backwards"); break; }
      if (ntent == captent) {
        size_t nc = captent ? captent * 2 : 8;
        tent_t *nt = (tent_t *)realloc(tent, nc * sizeof *nt);
        if (!nt) { rc = open_fail(db, NGS_NOMEM, "out of memory"); break; }
        tent = nt; captent = nc;
      }
      memcpy(tent[ntent].id, r.id, 32);
      tent[ntent].off = off; tent[ntent].len = (uint32_t)pay.n; tent[ntent].t_record = r.t_record;
      tent[ntent].seq = r.seq; tent[ntent].nslen = r.ns_len;
      tent[ntent].ns = dup_n((const char *)r.ns, r.ns_len);
      if (!tent[ntent].ns) { rc = open_fail(db, NGS_NOMEM, "out of memory"); break; }
      ntent++;
      if (pend) {
        if (!in_batch) { in_batch = 1; batch_off = off; }
        off += flen;
        continue;
      }
      /* a frame without the pending bit closes the batch: commit every tentative record */
      for (k = 0; k < ntent && rc == NGS_OK; k++) {
        ent_t e;
        size_t dup;
        uint32_t hidx = 0;
        if (ht_find(db, tent[k].id, &dup)) { rc = open_fail(db, NGS_CORRUPT, "duplicate fact id"); break; }
        rc = chain_set(&db->chain, (const uint8_t *)tent[k].ns, tent[k].nslen, tent[k].seq, tent[k].id, &hidx);
        if (rc) { rc = open_fail(db, rc, "out of memory"); break; }
        memcpy(e.id, tent[k].id, 32);
        e.seg = (uint32_t)seg_idx; e.len = tent[k].len; e.off = tent[k].off; e.head = hidx; e.t_record = tent[k].t_record;
        rc = ent_add(db, &e);
        if (rc) { rc = open_fail(db, rc, "out of memory"); break; }
        db->ord++;
        db->last_t = tent[k].t_record;
      }
      tents_free(tent, ntent); ntent = 0; in_batch = 0;
      if (rc) break;
      off += flen;
    }
    if (rc) break;
    if (!tail && in_batch) { tail = 1; T = batch_off; }          /* torn batch at the very end */
    tents_free(tent, ntent); ntent = 0;
    if (tail) {
      if (!last) { rc = open_fail(db, NGS_CORRUPT, "bad record inside a completed segment"); break; }
      if (T < size) {
        if (!db->ro) {
          cut_tail(db, &db->segs[seg_idx], T, size);
          if (f->vfs->truncate(f, T) != NGS_OK || f->vfs->fsync(f) != NGS_OK) { rc = open_fail(db, NGS_IOERR, "cannot truncate the torn tail"); break; }
        }
        db->segs[seg_idx].size = T;
        note_tail(db, s.num, size - T);
      }
    }
  }
  tents_free(tent, ntent); free(tent); free(pay.p);
  return rc;
}

/* --------------------------------------------------------------- open */
static int load_or_make_key(ngs *db, const ngs_open_opts *o, int create) {
  char *kp = NULL, *tp = NULL;
  ngs_file *f = NULL;
  uint8_t buf[96], seed[32];
  size_t got = 0;
  int rc;
  if (o->node_seckey) {
    memcpy(db->sk, o->node_seckey, 64);
    ngs__pub_from_sk(db->pk, db->sk);
    db->have_key = 1;
    return NGS_OK;
  }
  rc = path_join(&kp, db->dir, "NODEKEY");
  if (rc) return rc;
  rc = db->vfs->open(db->vfs, kp, NGS_VF_RDONLY, &f);
  if (rc == NGS_OK) {
    rc = f->vfs->pread(f, buf, sizeof buf, 0, &got);
    f->vfs->close(f);
    if (rc == NGS_OK && got == sizeof buf) {
      uint8_t pk[32];
      ngs__pub_from_sk(pk, buf);
      if (memcmp(pk, buf + 64, 32) != 0) rc = NGS_CORRUPT;
      else { memcpy(db->sk, buf, 64); memcpy(db->pk, buf + 64, 32); db->have_key = 1; rc = NGS_OK; }
    } else if (rc == NGS_OK) rc = NGS_CORRUPT;
    ngs__wipe(buf, sizeof buf);
    free(kp);
    return rc;
  }
  if (rc != NGS_NOTFOUND || !create) { free(kp); return rc == NGS_NOTFOUND ? NGS_NOTFOUND : rc; }
  /* generate: temp file, fsync, rename over NODEKEY, fsync the directory */
  rc = db->vfs->random(db->vfs, seed, sizeof seed);
  if (rc) { free(kp); return rc; }
  ngs__keypair(db->pk, db->sk, seed);
  ngs__wipe(seed, sizeof seed);
  memcpy(buf, db->sk, 64); memcpy(buf + 64, db->pk, 32);
  rc = path_join(&tp, db->dir, "NODEKEY.tmp");
  if (rc) { free(kp); return rc; }
  rc = db->vfs->open(db->vfs, tp, NGS_VF_RDWR | NGS_VF_CREATE, &f);
  if (!rc) {
    rc = f->vfs->truncate(f, 0);
    if (!rc) rc = f->vfs->pwrite(f, buf, sizeof buf, 0);
    if (!rc) rc = f->vfs->fsync(f);
    f->vfs->close(f);
  }
  if (!rc) rc = db->vfs->rename(db->vfs, tp, kp);
  if (!rc) rc = db->vfs->fsync_dir(db->vfs, db->dir);
  ngs__wipe(buf, sizeof buf);
  free(kp); free(tp);
  if (rc) return rc;
  db->have_key = 1;
  return NGS_OK;
}

int ngs__open_vfs(const char *dir, const ngs_open_opts *opts, ngs_vfs *vfs, ngs **out) {
  ngs *db;
  ngs_open_opts o;
  numlist nl = { NULL, 0, 0 };
  size_t i, j;
  int rc, create, rw;
  *out = NULL;
  db = (ngs *)calloc(1, sizeof *db);
  if (!db) return NGS_NOMEM;
  db->vfs = vfs;
  ngs__global_lock(); db->gen = ++g_gen; ngs__global_unlock();
  db->mu = ngs__mutex_new();
  if (!db->mu) { free(db); return NGS_NOMEM; }
  *out = db;
  memset(&o, 0, sizeof o);
  if (opts) {
    if (opts->size < offsetof(ngs_open_opts, node_seckey)) return open_fail(db, NGS_MISUSE, "ngs_open_opts size is too small");
    memcpy(&o, opts, opts->size < sizeof o ? opts->size : sizeof o);
  } else {
    o.flags = NGS_OPEN_READWRITE;
  }
  if (!dir || !dir[0]) return open_fail(db, NGS_MISUSE, "directory is empty");
  rw = (o.flags & NGS_OPEN_READWRITE) != 0;
  create = (o.flags & NGS_OPEN_CREATE) != 0;
  db->ro = (o.flags & NGS_OPEN_READONLY) != 0;
  if (db->ro == rw || (create && !rw)) return open_fail(db, NGS_MISUSE, "flags must be READONLY or READWRITE, CREATE needs READWRITE");
  db->seg_limit = o.segment_bytes ? o.segment_bytes : DEF_SEG_BYTES;
  db->dir = dup_n(dir, strlen(dir));
  if (!db->dir) return open_fail(db, NGS_NOMEM, "out of memory");
  rc = path_join(&db->logdir, db->dir, "log");
  if (rc) return open_fail(db, rc, "out of memory");
  if (!db->ro) {
    if (create) {
      rc = vfs->mkdir(vfs, db->dir);
      if (!rc) rc = vfs->mkdir(vfs, db->logdir);
      if (rc) return open_fail(db, rc, "cannot create the database directory");
    }
    rc = dir_register(db->dir);
    if (rc == NGS_BUSY) return open_fail(db, NGS_BUSY, "database is already open in this process");
    if (rc) return open_fail(db, rc, "out of memory");
    db->registered = 1;
    {
      char *lp = NULL;
      rc = path_join(&lp, db->dir, "LOCK");
      if (!rc) { rc = vfs->lock(vfs, lp, &db->lockf); free(lp); }
      if (rc == NGS_BUSY) return open_fail(db, NGS_BUSY, "writer lock is held by another process");
      if (rc) return open_fail(db, rc, "cannot take the writer lock");
    }
    rc = load_or_make_key(db, &o, create);
    if (rc == NGS_NOTFOUND) return open_fail(db, NGS_NOTFOUND, "no node key (use NGS_OPEN_CREATE or supply node_seckey)");
    if (rc) return open_fail(db, rc, "cannot load the node key");
  }
  rc = vfs->list(vfs, db->logdir, collect_seg, &nl);
  if (rc == NGS_NOTFOUND) { free(nl.v); return open_fail(db, NGS_NOTFOUND, "no database at this directory"); }
  if (rc) { free(nl.v); return open_fail(db, rc, "cannot list the log directory"); }
  for (i = 1; i < nl.n; i++) {                                    /* ascending by number */
    uint32_t v = nl.v[i];
    for (j = i; j > 0 && nl.v[j - 1] > v; j--) nl.v[j] = nl.v[j - 1];
    nl.v[j] = v;
  }
  for (i = 0; i < nl.n; i++) {
    if (nl.v[i] != (uint32_t)(i + 1)) { free(nl.v); return open_fail(db, NGS_CORRUPT, "segment numbers are not consecutive"); }
  }
  rc = recover(db, nl.v, nl.n);
  free(nl.v);
  if (rc) return rc;
  return NGS_OK;
}

int ngs_open(const char *dir, const ngs_open_opts *opts, ngs **out) {
  if (!out) return NGS_MISUSE;
  return ngs__open_vfs(dir, opts, ngs__default_vfs(), out);
}

int ngs_close(ngs *db) {
  size_t i;
  if (!db) return NGS_OK;
  if (db->iters) return fail(db, NGS_MISUSE, "iterators are still open");
  for (i = 0; i < db->nsegs; i++) if (db->segs[i].f) db->segs[i].f->vfs->close(db->segs[i].f);
  if (db->lockf) db->lockf->vfs->close(db->lockf);
  if (db->registered) dir_unregister(db->dir);
  free(db->segs); free(db->ents); free(db->htab);
  chain_free(&db->chain);
  free(db->dir); free(db->logdir);
  ngs__wipe(db->sk, sizeof db->sk);
  ngs__mutex_free(db->mu);
  free(db);
  return NGS_OK;
}

#define CHECK_HANDLE(db) do { if (!(db)) return NGS_MISUSE; if ((db)->failed) return NGS_MISUSE; } while (0)

int ngs_node_pubkey(ngs *db, ngs_pubkey *out) {
  CHECK_HANDLE(db);
  if (!out) return fail(db, NGS_MISUSE, "out is NULL");
  if (!db->have_key) return fail(db, NGS_NOTFOUND, "no node key on a read-only handle");
  memcpy(out->b, db->pk, 32);
  return NGS_OK;
}

/* --------------------------------------------------------- read a fact */
static int ent_payload(ngs *db, const ent_t *e, ngs_buf *pay, ngs_rec *r) {
  uint8_t type;
  uint64_t flen;
  int rc = read_frame_at(db->segs[e->seg].f, e->off, db->segs[e->seg].size, &type, pay, &flen);
  if (rc > 0) return rc == NGS_NOMEM ? NGS_NOMEM : NGS_IOERR;
  if (rc == FR_BAD || (type & 0x7Fu) != NGS_REC_FACT) return NGS_CORRUPT;
  if (ngs__rec_decode(pay->p, pay->n, r) != NGS_OK) return NGS_CORRUPT;
  if (memcmp(r->id, e->id, 32) != 0 || ngs__rec_check_id(r) != NGS_OK) return NGS_CORRUPT;
  return NGS_OK;
}

static int al8(size_t v, size_t *out) {
  if (v > SIZE_MAX - 7) return 0;
  *out = (v + 7) & ~(size_t)7;
  return 1;
}

/* one allocation: [ngs_fact][ngs_str tags[n]][bytes: ns, title, body, attrs, each tag] */
static int make_view(const ngs_rec *r, ngs_fact **out) {
  size_t head, strs, total, i;
  ngs_fact *f;
  uint8_t *base, *w;
  ngs_cur c;
  int major;
  uint64_t v;
  if (!al8(sizeof(ngs_fact), &head)) return NGS_NOMEM;
  strs = (size_t)r->n_tags * sizeof(ngs_str);
  if (strs / sizeof(ngs_str) != (size_t)r->n_tags) return NGS_NOMEM;     /* overflow on 32-bit size_t */
  total = head;
  if (strs > SIZE_MAX - total) return NGS_NOMEM;
  total += strs;
  if (r->ns_len > SIZE_MAX - total) return NGS_NOMEM;
  total += r->ns_len;
  if (r->title_len > SIZE_MAX - total) return NGS_NOMEM;
  total += r->title_len;
  if (r->body_len > SIZE_MAX - total) return NGS_NOMEM;
  total += r->body_len;
  if (r->attrs_len > SIZE_MAX - total) return NGS_NOMEM;
  total += r->attrs_len;
  if (r->tags_len > SIZE_MAX - total) return NGS_NOMEM;
  total += r->tags_len;                                    /* upper bound for the tag texts */
  base = (uint8_t *)calloc(1, total ? total : 1);
  if (!base) return NGS_NOMEM;
  f = (ngs_fact *)base;
  w = base + head + strs;
  f->size = (uint32_t)sizeof(ngs_fact);
  memcpy(f->id.b, r->id, 32);
  f->ns.p = (const char *)w; f->ns.n = r->ns_len; memcpy(w, r->ns, r->ns_len); w += r->ns_len;
  f->kind = r->kind;
  memcpy(f->writer.b, r->writer, 32);
  f->seq = r->seq;
  f->t_event = r->t_event; f->t_record = r->t_record; f->valid_from = r->valid_from; f->valid_to = NGS_TIME_MAX;
  f->title.p = (const char *)w; f->title.n = r->title_len; memcpy(w, r->title, r->title_len); w += r->title_len;
  f->body.p = (const char *)w; f->body.n = r->body_len; memcpy(w, r->body, r->body_len); w += r->body_len;
  f->attrs_cbor = r->attrs_len ? w : NULL; f->attrs_len = r->attrs_len;
  if (r->attrs_len) { memcpy(w, r->attrs, r->attrs_len); w += r->attrs_len; }
  f->schema = r->schema;
  f->redacted = 0;
  f->n_tags = r->n_tags;
  if (r->n_tags) {
    ngs_str *ts = (ngs_str *)(base + head);
    const uint8_t *s;
    size_t sn;
    c.p = r->tags; c.n = r->tags_len; c.i = 0; c.bad = 0;
    if (ngs__cur_head(&c, &major, &v)) { free(base); return NGS_CORRUPT; }
    for (i = 0; i < r->n_tags; i++) {
      if (ngs__cur_text(&c, &s, &sn)) { free(base); return NGS_CORRUPT; }
      ts[i].p = (const char *)w; ts[i].n = sn;
      if (sn) memcpy(w, s, sn);
      w += sn;
    }
    f->tags = ts;
  }
  *out = f;
  return NGS_OK;
}

int ngs_get(ngs *db, const ngs_id *id, ngs_fact **out) {
  size_t e;
  ngs_buf pay = { NULL, 0, 0 };
  ngs_rec r;
  int rc;
  CHECK_HANDLE(db);
  if (!id || !out) return fail(db, NGS_MISUSE, "id or out is NULL");
  *out = NULL;
  ngs__mutex_lock(db->mu);
  if (!ht_find(db, id->b, &e)) { ngs__mutex_unlock(db->mu); return fail(db, NGS_NOTFOUND, "no such fact"); }
  rc = ent_payload(db, &db->ents[e], &pay, &r);
  if (rc == NGS_OK) rc = make_view(&r, out);
  free(pay.p);
  ngs__mutex_unlock(db->mu);
  if (rc == NGS_CORRUPT) return fail(db, rc, "stored record failed its checks");
  if (rc) return fail(db, rc, "cannot read the record");
  return NGS_OK;
}

/* ---------------------------------------------------------------- write */
typedef struct { const uint8_t *ns; size_t n; uint64_t seq; uint8_t last[32]; } bhead_t;

static int take_in(ngs_fact_in *dst, const ngs_fact_in *src) {
  if (src->size < offsetof(ngs_fact_in, t_event)) return NGS_MISUSE;
  memset(dst, 0, sizeof *dst);
  memcpy(dst, src, src->size < sizeof *dst ? src->size : sizeof *dst);
  return NGS_OK;
}

static int validate_in(const ngs_fact_in *f, const char **why) {
  size_t i;
  if (!str_ok(f->ns) || !str_ok(f->title) || !str_ok(f->body)) { *why = "a string has a NULL pointer with a length"; return NGS_MISUSE; }
  if (f->kind < NGS_EPISODIC || f->kind > NGS_PROCEDURAL) { *why = "kind must be EPISODIC, SEMANTIC or PROCEDURAL"; return NGS_MISUSE; }
  if (f->ns.n < 1 || f->ns.n > NGS_MAX_NS_LEN) { *why = "namespace length must be 1..255"; return NGS_MISUSE; }
  if (!ngs__utf8_ok((const uint8_t *)f->ns.p, f->ns.n) || memchr(f->ns.p, 0, f->ns.n)) { *why = "namespace must be UTF-8 without NUL"; return NGS_MISUSE; }
  if (f->title.n > NGS_MAX_TITLE_LEN) { *why = "title over 1024 bytes"; return NGS_TOOBIG; }
  if (!ngs__utf8_ok((const uint8_t *)f->title.p, f->title.n)) { *why = "title is not valid UTF-8"; return NGS_MISUSE; }
  if (f->body.n > NGS_MAX_BODY) { *why = "body over the limit"; return NGS_TOOBIG; }
  if (!ngs__utf8_ok((const uint8_t *)f->body.p, f->body.n)) { *why = "body is not valid UTF-8"; return NGS_MISUSE; }
  if (f->t_event == NGS_TIME_MIN || f->t_event == NGS_TIME_MAX || f->valid_from == NGS_TIME_MIN || f->valid_from == NGS_TIME_MAX) {
    *why = "t_event and valid_from must be an instant or NGS_TIME_NOW"; return NGS_MISUSE;
  }
  if (f->n_tags > NGS_MAX_TAGS || (f->tags == NULL && f->n_tags != 0)) { *why = "too many tags or NULL tag array"; return NGS_MISUSE; }
  for (i = 0; i < f->n_tags; i++) {
    if (!str_ok(f->tags[i]) || f->tags[i].n > NGS_MAX_TAG) { *why = "tag is NULL or over 1024 bytes"; return NGS_MISUSE; }
    if (!ngs__utf8_ok((const uint8_t *)f->tags[i].p, f->tags[i].n)) { *why = "tag is not valid UTF-8"; return NGS_MISUSE; }
  }
  if (f->attrs_len > NGS_MAX_ATTRS_LEN) { *why = "attrs over 64 KiB"; return NGS_TOOBIG; }
  if ((f->attrs_cbor == NULL && f->attrs_len != 0)) { *why = "attrs has a NULL pointer with a length"; return NGS_MISUSE; }
  if (f->attrs_len && ((f->attrs_cbor[0] >> 5) != 5 || ngs__cbor_wellformed(f->attrs_cbor, f->attrs_len))) { *why = "attrs is not one well-formed CBOR map (definite lengths)"; return NGS_MISUSE; }
  if (f->n_vecs || f->vecs) { *why = "not in M1: vectors"; return NGS_MISUSE; }
  if (f->supersedes) { *why = "not in M1: supersedes"; return NGS_MISUSE; }
  if (!(f->salience0 == f->salience0) || isinf(f->salience0)) { *why = "salience0 must be finite"; return NGS_MISUSE; }
  return NGS_OK;
}

static int make_segment(ngs *db) {
  char *path = NULL;
  ngs_file *f = NULL;
  uint8_t hdr[NGS_SEG_HDR];
  seg_t s;
  uint32_t num = db->nsegs ? db->segs[db->nsegs - 1].num + 1 : 1;
  int rc;
  memset(&s, 0, sizeof s);
  rc = seg_path(db, num, &path);
  if (rc) return rc;
  rc = db->vfs->open(db->vfs, path, NGS_VF_RDWR | NGS_VF_CREATE, &f);
  if (!rc) rc = f->vfs->truncate(f, 0);
  ngs__seg_hdr_encode(hdr, db->ord, db->pk);
  if (!rc) rc = f->vfs->pwrite(f, hdr, sizeof hdr, 0);
  if (!rc) rc = f->vfs->fsync(f);
  if (!rc) rc = db->vfs->fsync_dir(db->vfs, db->logdir);
  if (!rc) {
    s.num = num; s.f = f; s.size = NGS_SEG_HDR; s.first_ord = db->ord; memcpy(s.writer, db->pk, 32);
    rc = push_seg(db, &s);
  }
  if (rc) {
    if (f) f->vfs->close(f);
    (void)db->vfs->unlink(db->vfs, path);
    free(path);
    return rc == NGS_NOMEM ? NGS_NOMEM : NGS_IOERR;
  }
  free(path);
  return NGS_OK;
}

static int do_remember(ngs *db, const ngs_fact_in *src, size_t n, int32_t flags, ngs_id *out_ids) {
  ngs_buf frames = { NULL, 0, 0 };
  ngs_buf *tagbufs = NULL, pay = { NULL, 0, 0 };
  bhead_t *bh = NULL;
  size_t nbh = 0, i, *foff = NULL, *flen = NULL;
  ngs_rec *recs = NULL;
  int64_t t = db->last_t, now;
  const char *why = "";
  int rc = NGS_OK;
  uint8_t zero32[32] = { 0 };
  uint64_t total, at;
  seg_t *sg;
  if (n == 0) return fail(db, NGS_MISUSE, "no facts");
  if (n > SIZE_MAX / sizeof *recs || n > UINT32_MAX / 2) return fail(db, NGS_TOOBIG, "batch too large");
  recs = (ngs_rec *)calloc(n, sizeof *recs);
  tagbufs = (ngs_buf *)calloc(n, sizeof *tagbufs);
  bh = (bhead_t *)calloc(n, sizeof *bh);
  foff = (size_t *)calloc(n, sizeof *foff);
  flen = (size_t *)calloc(n, sizeof *flen);
  if (!recs || !tagbufs || !bh || !foff || !flen) { rc = fail(db, NGS_NOMEM, "out of memory"); goto done; }
  now = db->vfs->now_us(db->vfs);
  for (i = 0; i < n; i++) {
    ngs_fact_in f;
    ngs_rec *r = &recs[i];
    int ci, k, found = 0;
    rc = take_in(&f, &src[i]);
    if (rc) { rc = fail(db, NGS_MISUSE, "ngs_fact_in size is too small"); goto done; }
    rc = validate_in(&f, &why);
    if (rc) { rc = fail(db, rc, why); goto done; }
    t = (now > t) ? now : t + 1;                           /* strictly increasing record time */
    memcpy(r->writer, db->pk, 32);
    r->ns = (const uint8_t *)f.ns.p; r->ns_len = f.ns.n; r->kind = f.kind;
    r->t_record = t;
    r->t_event = (f.t_event == NGS_TIME_NOW) ? t : f.t_event;
    r->valid_from = (f.valid_from == NGS_TIME_NOW) ? r->t_event : f.valid_from;
    r->title = (const uint8_t *)f.title.p; r->title_len = f.title.n;
    r->body = (const uint8_t *)f.body.p; r->body_len = f.body.n;
    r->attrs = f.attrs_cbor; r->attrs_len = f.attrs_len; r->schema = f.schema;
    rc = ngs__encode_tags(&tagbufs[i], f.tags, f.n_tags);
    if (rc) { rc = fail(db, NGS_NOMEM, "out of memory"); goto done; }
    r->tags = tagbufs[i].p; r->tags_len = tagbufs[i].n; r->n_tags = (uint32_t)f.n_tags;
    /* chain position: earlier facts of this batch first, then the committed chain */
    for (k = (int)nbh - 1; k >= 0; k--) {
      if (bh[k].n == r->ns_len && memcmp(bh[k].ns, r->ns, r->ns_len) == 0) { r->seq = bh[k].seq + 1; memcpy(r->prev, bh[k].last, 32); found = 1; break; }
    }
    if (!found) {
      ci = chain_find(&db->chain, r->ns, r->ns_len);
      if (ci >= 0) { r->seq = db->chain.h[ci].seq + 1; memcpy(r->prev, db->chain.h[ci].last, 32); }
      else { r->seq = 1; memcpy(r->prev, zero32, 32); }
    }
    rc = ngs__rec_seal(r, db->sk);
    if (rc) { rc = fail(db, NGS_NOMEM, "out of memory"); goto done; }
    bh[nbh].ns = r->ns; bh[nbh].n = r->ns_len; bh[nbh].seq = r->seq; memcpy(bh[nbh].last, r->id, 32); nbh++;
    pay.n = 0;
    rc = ngs__rec_encode(&pay, r);
    if (rc || pay.n > NGS_MAX_REC) { rc = fail(db, rc ? NGS_NOMEM : NGS_TOOBIG, "record too large"); goto done; }
    foff[i] = frames.n;
    flen[i] = NGS_FRAME_OVERHEAD + pay.n;
    {
      static const uint8_t z9[NGS_FRAME_OVERHEAD] = { 0 };
      size_t before = frames.n;
      rc = ngs__buf_put(&frames, pay.p, pay.n);                       /* reserve the whole frame ... */
      if (!rc) rc = ngs__buf_put(&frames, z9, NGS_FRAME_OVERHEAD);
      if (rc) { rc = fail(db, NGS_NOMEM, "out of memory"); goto done; }
      /* ... and fill it in place; every frame of a batch but the last is marked pending */
      ngs__frame_encode(frames.p + before, (uint8_t)(NGS_REC_FACT | ((i + 1 < n) ? NGS_REC_PENDING : 0)),
                        pay.p, (uint32_t)pay.n);
    }
  }
  total = frames.n;
  /* pick or create the segment; a batch never spans two segments */
  if (!db->nsegs || (db->segs[db->nsegs - 1].size + total > db->seg_limit && db->segs[db->nsegs - 1].size > NGS_SEG_HDR)) {
    rc = make_segment(db);
    if (rc) { rc = fail(db, rc, "cannot create a log segment"); goto done; }
  }
  sg = &db->segs[db->nsegs - 1];
  at = sg->size;
  rc = sg->f->vfs->pwrite(sg->f, frames.p, frames.n, at);
  if (rc) {
    if (sg->f->vfs->truncate(sg->f, at) != NGS_OK) db->broken = 1;   /* cannot restore the tail: stop writing */
    rc = fail(db, NGS_IOERR, "write failed");
    goto done;
  }
  if (!(flags & NGS_WRITE_NO_SYNC)) {
    rc = sg->f->vfs->fsync(sg->f);
    if (rc) { db->broken = 1; rc = fail(db, NGS_IOERR, "fsync failed; reopen the database"); goto done; }
  }
  /* durable: make the facts visible */
  for (i = 0; i < n; i++) {
    ent_t e;
    uint32_t hidx = 0;
    rc = chain_set(&db->chain, recs[i].ns, recs[i].ns_len, recs[i].seq, recs[i].id, &hidx);
    if (!rc) {
      memcpy(e.id, recs[i].id, 32);
      e.seg = (uint32_t)(db->nsegs - 1); e.len = (uint32_t)(flen[i] - NGS_FRAME_OVERHEAD); e.off = at + foff[i];
      e.head = hidx; e.t_record = recs[i].t_record;
      rc = ent_add(db, &e);
    }
    if (rc) { db->broken = 1; rc = fail(db, NGS_NOMEM, "out of memory after commit; reopen the database"); goto done; }
    db->ord++;
    db->last_t = recs[i].t_record;
    if (out_ids) memcpy(out_ids[i].b, recs[i].id, 32);
  }
  sg->size = at + frames.n;
  rc = NGS_OK;
done:
  if (tagbufs) for (i = 0; i < n; i++) ngs__buf_free(&tagbufs[i]);
  free(tagbufs); free(recs); free(bh); free(foff); free(flen);
  ngs__buf_free(&frames); ngs__buf_free(&pay);
  return rc;
}

/* Every other entry point of ngs.h is not in M1. */
int ngs__not_in_m1(ngs *db) {
  if (!db) return NGS_MISUSE;
  return fail(db, NGS_MISUSE, "not in M1");
}

static int writable(ngs *db) {
  if (!db) return NGS_MISUSE;
  if (db->failed) return NGS_MISUSE;
  if (db->ro) return fail(db, NGS_MISUSE, "database is open read-only");
  if (db->broken) return fail(db, NGS_IOERR, "handle is broken after an I/O failure; reopen the database");
  return NGS_OK;
}

int ngs_remember(ngs *db, const ngs_fact_in *in, int32_t flags, ngs_id *out_id) {
  int rc = writable(db);
  if (rc) return rc;
  if (!in) return fail(db, NGS_MISUSE, "in is NULL");
  ngs__mutex_lock(db->mu);
  rc = do_remember(db, in, 1, flags, out_id);
  ngs__mutex_unlock(db->mu);
  return rc;
}

int ngs_remember_many(ngs *db, const ngs_fact_in *in, size_t n, int32_t flags, ngs_id *out_ids) {
  int rc = writable(db);
  if (rc) return rc;
  if (!in || n == 0) return fail(db, NGS_MISUSE, "no facts");
  /* ngs_fact_in is an array of structs that each carry their own size; the caller's array stride is
  ** sizeof(ngs_fact_in), which is the only stride this header can express. */
  ngs__mutex_lock(db->mu);
  rc = do_remember(db, in, n, flags, out_ids);
  ngs__mutex_unlock(db->mu);
  return rc;
}

int ngs_flush(ngs *db) {
  int rc = NGS_OK;
  CHECK_HANDLE(db);
  if (db->ro) return NGS_OK;
  ngs__mutex_lock(db->mu);
  if (db->broken) rc = fail(db, NGS_IOERR, "handle is broken after an I/O failure; reopen the database");
  else if (db->nsegs) {
    seg_t *sg = &db->segs[db->nsegs - 1];
    if (sg->f->vfs->fsync(sg->f)) { db->broken = 1; rc = fail(db, NGS_IOERR, "fsync failed; reopen the database"); }
  }
  ngs__mutex_unlock(db->mu);
  return rc;
}

/* ----------------------------------------------------------------- scan */
int ngs_scan(ngs *db, const ngs_scan_opts *o, ngs_iter **it) {
  ngs_scan_opts so;
  ngs_iter *x;
  CHECK_HANDLE(db);
  if (!it) return fail(db, NGS_MISUSE, "it is NULL");
  *it = NULL;
  memset(&so, 0, sizeof so);
  if (o) {
    if (o->size < offsetof(ngs_scan_opts, since)) return fail(db, NGS_MISUSE, "ngs_scan_opts size is too small");
    memcpy(&so, o, o->size < sizeof so ? o->size : sizeof so);
    if (!str_ok(so.ns)) return fail(db, NGS_MISUSE, "namespace has a NULL pointer with a length");
    if (o->size <= offsetof(ngs_scan_opts, since)) { so.since = NGS_TIME_MIN; so.until = NGS_TIME_MAX; }
    else if (o->size <= offsetof(ngs_scan_opts, until)) { so.until = NGS_TIME_MAX; }
  } else {
    so.since = NGS_TIME_MIN; so.until = NGS_TIME_MAX;
  }
  x = (ngs_iter *)calloc(1, sizeof *x);
  if (!x) return fail(db, NGS_NOMEM, "out of memory");
  if (so.ns.n) { x->ns = dup_n(so.ns.p, so.ns.n); if (!x->ns) { free(x); return fail(db, NGS_NOMEM, "out of memory"); } x->nslen = so.ns.n; }
  if (so.writer) { x->have_writer = 1; memcpy(x->writer, so.writer->b, 32); }
  x->since = so.since; x->until = so.until; x->db = db;
  ngs__mutex_lock(db->mu);
  x->end = db->nents;
  db->iters++;
  ngs__mutex_unlock(db->mu);
  *it = x;
  return NGS_OK;
}

int ngs_iter_next(ngs_iter *it, ngs_fact **out) {
  ngs *db;
  int rc = NGS_NOTFOUND;
  if (!it || !out) return NGS_MISUSE;
  db = it->db;
  *out = NULL;
  ngs__mutex_lock(db->mu);
  while (it->pos < it->end) {
    const ent_t *e = &db->ents[it->pos++];
    ngs_buf pay = { NULL, 0, 0 };
    ngs_rec r;
    if (it->nslen && (db->chain.h[e->head].nslen != it->nslen || memcmp(db->chain.h[e->head].ns, it->ns, it->nslen) != 0)) continue;
    if (it->have_writer && memcmp(db->segs[e->seg].writer, it->writer, 32) != 0) continue;
    if (e->t_record < it->since || e->t_record > it->until) continue;
    rc = ent_payload(db, e, &pay, &r);
    if (rc == NGS_OK) rc = make_view(&r, out);
    free(pay.p);
    if (rc == NGS_CORRUPT) (void)fail(db, rc, "stored record failed its checks");
    else if (rc) (void)fail(db, rc, "cannot read the record");
    ngs__mutex_unlock(db->mu);
    return rc;
  }
  ngs__mutex_unlock(db->mu);
  return rc;
}

void ngs_iter_close(ngs_iter *it) {
  if (!it) return;
  ngs__mutex_lock(it->db->mu);
  it->db->iters--;
  ngs__mutex_unlock(it->db->mu);
  free(it->ns);
  free(it);
}

/* --------------------------------------------------------------- verify */
static int vfail(ngs *db, const char *msg) { return fail(db, NGS_CORRUPT, msg); }

int ngs_verify(ngs *db, const uint8_t *ckpt, size_t len) {
  ngs_buf pay = { NULL, 0, 0 };
  chain_t vc = { NULL, 0, 0 };
  uint64_t ord = 0;
  int64_t last_t = 0;
  size_t i;
  int rc = NGS_OK, any = 0;
  static const uint8_t zero32[32] = { 0 };
  CHECK_HANDLE(db);
  if (ckpt || len) return fail(db, NGS_MISUSE, "not in M1: checkpoint verification");
  ngs__mutex_lock(db->mu);
  for (i = 0; i < db->nsegs && rc == NGS_OK; i++) {
    seg_t *s = &db->segs[i];
    uint8_t hdr[NGS_SEG_HDR], w[32];
    uint64_t fo, off = NGS_SEG_HDR;
    size_t got = 0;
    int pending = 0;
    if (s->f->vfs->pread(s->f, hdr, NGS_SEG_HDR, 0, &got) || got != NGS_SEG_HDR || ngs__seg_hdr_decode(hdr, &fo, w) != NGS_OK) { rc = vfail(db, "segment header is damaged"); break; }
    if (fo != ord || fo != s->first_ord) { rc = vfail(db, "segment ordinal does not continue the log"); break; }
    if (memcmp(w, s->writer, 32) != 0) { rc = vfail(db, "segment writer changed on disk"); break; }
    while (off < s->size) {
      uint8_t type;
      uint64_t flen = 0;
      ngs_rec r;
      int ci, fr = read_frame_at(s->f, off, s->size, &type, &pay, &flen);
      if (fr == FR_BAD) { rc = vfail(db, "frame is short or fails its CRC"); break; }
      if (fr > 0) { rc = fail(db, NGS_IOERR, "I/O error while verifying"); break; }
      pending = (type & NGS_REC_PENDING) != 0;
      type = (uint8_t)(type & 0x7Fu);
      if (type == NGS_REC_PAD) { off += flen; continue; }
      if (type != NGS_REC_FACT) { rc = vfail(db, "unknown record type"); break; }
      if (ngs__rec_decode(pay.p, pay.n, &r) != NGS_OK) { rc = vfail(db, "record does not decode in canonical form"); break; }
      if (memcmp(r.writer, s->writer, 32) != 0) { rc = vfail(db, "record writer differs from its segment"); break; }
      if (ngs__rec_check_id(&r) != NGS_OK) { rc = vfail(db, "record id or body hash does not match its content"); break; }
      if (ngs__rec_check_sig(&r) != NGS_OK) { rc = vfail(db, "signature does not verify"); break; }
      ci = chain_find(&vc, r.ns, r.ns_len);
      if (r.seq != (ci >= 0 ? vc.h[ci].seq + 1 : 1) || memcmp(r.prev, ci >= 0 ? vc.h[ci].last : zero32, 32) != 0) { rc = vfail(db, "sequence or previous-hash chain is broken"); break; }
      if (any && r.t_record <= last_t) { rc = vfail(db, "record time goes backwards"); break; }
      if (chain_set(&vc, r.ns, r.ns_len, r.seq, r.id, NULL)) { rc = fail(db, NGS_NOMEM, "out of memory"); break; }
      any = 1; last_t = r.t_record; ord++;
      off += flen;
    }
    if (rc) break;
    if (pending) { rc = vfail(db, "segment ends inside an unfinished batch"); break; }
    if (off != s->size) { rc = vfail(db, "segment length does not match its records"); break; }
  }
  if (rc == NGS_OK && ord != db->ord) rc = vfail(db, "record count differs from the open handle's view");
  ngs__mutex_unlock(db->mu);
  chain_free(&vc);
  free(pay.p);
  return rc;
}
