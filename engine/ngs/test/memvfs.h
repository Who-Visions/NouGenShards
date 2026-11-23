/*
** memvfs.h -- an in-memory platform layer for crash, power-loss and bit-flip
** testing. Header-only so a test is one translation unit.
**
** Model:
**   - every file has `cur` (what reads see) and `dur` (what survives power loss)
**   - pwrite/truncate change `cur` and queue an op; sync(file) makes dur = cur
**   - a file's existence is durable only after sync_dir of its directory
**   - mv_crash(): every queued op persists or not (independently, so later ops
**     can survive while earlier ones are lost: reordering), and a persisted
**     write may be torn at a 512-byte sector boundary; undurable files vanish
**   - mv_fail_at = k makes the k-th mutating call fail and every later call
**     fail too ("the process died here"); mv_ops counts mutating calls
*/
#ifndef MEMVFS_H
#define MEMVFS_H
#include "../src/ngs_internal.h"
#include <stdio.h>

#define MV_MAX_FILES 256
#define MV_MAX_OPS 4096

typedef struct { int is_trunc; uint64_t off; uint8_t *data; size_t n; } mv_op;
typedef struct {
  char path[256];
  int used, durable_exists, is_dir;
  uint8_t *cur, *dur; size_t cur_n, dur_n, cur_cap;
  mv_op ops[MV_MAX_OPS]; size_t n_ops;
  int locked;
} mv_node;
struct ngs__file { mv_node *n; };

static mv_node mv_nodes[MV_MAX_FILES];
static long mv_fail_at = -1, mv_ops;
static int mv_dead;
static uint64_t mv_rng = 88172645463325252ull;

static uint64_t mv_rand(void) { mv_rng ^= mv_rng << 13; mv_rng ^= mv_rng >> 7; mv_rng ^= mv_rng << 17; return mv_rng; }

static int mv_tick(void) {          /* call at the start of every mutating op */
  if (mv_dead) return NGS_IOERR;
  mv_ops++;
  if (mv_fail_at >= 0 && mv_ops >= mv_fail_at) { mv_dead = 1; return NGS_IOERR; }
  return NGS_OK;
}

static mv_node *mv_find(const char *p) {
  int i;
  for (i = 0; i < MV_MAX_FILES; i++) if (mv_nodes[i].used && strcmp(mv_nodes[i].path, p) == 0) return &mv_nodes[i];
  return NULL;
}
static mv_node *mv_new(const char *p, int is_dir) {
  int i;
  for (i = 0; i < MV_MAX_FILES; i++) if (!mv_nodes[i].used) {
    mv_node *n = &mv_nodes[i];
    memset(n, 0, sizeof *n);
    n->used = 1; n->is_dir = is_dir;
    snprintf(n->path, sizeof n->path, "%s", p);
    return n;
  }
  return NULL;
}

static void mv_reserve(mv_node *n, size_t need) {
  if (need > n->cur_cap) {
    size_t c = n->cur_cap ? n->cur_cap : 4096;
    while (c < need) c *= 2;
    n->cur = (uint8_t *)realloc(n->cur, c);
    n->cur_cap = c;
  }
}

static int mv_open_u(const char *path, int create, ngs__file **out) {
  mv_node *n = mv_find(path);
  *out = NULL;
  if (!n) {
    int rc;
    if (!create) return NGS_NOTFOUND;
    if ((rc = mv_tick())) return rc;
    n = mv_new(path, 0);
    if (!n) return NGS_IOERR;
  }
  *out = (ngs__file *)malloc(sizeof **out);
  (*out)->n = n;
  return NGS_OK;
}
static int mv_close_u(ngs__file *f) { if (f) { if (f->n) f->n->locked = 0; free(f); } return NGS_OK; }
static int mv_pread_u(ngs__file *f, void *buf, size_t n, uint64_t off, size_t *got) {
  mv_node *x = f->n;
  if (mv_dead) return NGS_IOERR;
  *got = 0;
  if (off >= x->cur_n) return NGS_OK;
  if (n > x->cur_n - off) n = (size_t)(x->cur_n - off);
  memcpy(buf, x->cur + off, n);
  *got = n;
  return NGS_OK;
}
static int mv_pwrite_u(ngs__file *f, const void *buf, size_t n, uint64_t off) {
  mv_node *x = f->n;
  mv_op *op;
  int rc;
  if ((rc = mv_tick())) {
    /* a dying write may still land partly (a torn write the process never
    ** saw complete) */
    if (n && mv_fail_at >= 0 && mv_ops == mv_fail_at && (mv_rand() & 1)) {
      size_t part = (size_t)(mv_rand() % n);
      mv_reserve(x, (size_t)off + part);
      if (off > x->cur_n) memset(x->cur + x->cur_n, 0, (size_t)off - x->cur_n);
      memcpy(x->cur + off, buf, part);
      if (off + part > x->cur_n) x->cur_n = (size_t)(off + part);
      if (x->n_ops < MV_MAX_OPS) {
        op = &x->ops[x->n_ops++];
        op->is_trunc = 0; op->off = off; op->n = part;
        op->data = (uint8_t *)malloc(part ? part : 1); memcpy(op->data, buf, part);
      }
    }
    return rc;
  }
  mv_reserve(x, (size_t)off + n);
  if (off > x->cur_n) memset(x->cur + x->cur_n, 0, (size_t)off - x->cur_n);
  memcpy(x->cur + off, buf, n);
  if (off + n > x->cur_n) x->cur_n = (size_t)(off + n);
  if (x->n_ops >= MV_MAX_OPS) return NGS_IOERR;
  op = &x->ops[x->n_ops++];
  op->is_trunc = 0; op->off = off; op->n = n;
  op->data = (uint8_t *)malloc(n ? n : 1); memcpy(op->data, buf, n);
  return NGS_OK;
}
static void mv_clear_ops(mv_node *x) {
  size_t i;
  for (i = 0; i < x->n_ops; i++) free(x->ops[i].data);
  x->n_ops = 0;
}
static int mv_sync_u(ngs__file *f) {
  mv_node *x = f->n;
  int rc;
  if ((rc = mv_tick())) return rc;
  free(x->dur);
  x->dur = (uint8_t *)malloc(x->cur_n ? x->cur_n : 1);
  memcpy(x->dur, x->cur, x->cur_n);
  x->dur_n = x->cur_n;
  mv_clear_ops(x);
  return NGS_OK;
}
static int mv_truncate_u(ngs__file *f, uint64_t size) {
  mv_node *x = f->n;
  int rc;
  mv_op *op;
  if ((rc = mv_tick())) return rc;
  mv_reserve(x, (size_t)size);
  if (size > x->cur_n) memset(x->cur + x->cur_n, 0, (size_t)size - x->cur_n);
  x->cur_n = (size_t)size;
  if (x->n_ops >= MV_MAX_OPS) return NGS_IOERR;
  op = &x->ops[x->n_ops++];
  op->is_trunc = 1; op->off = size; op->data = NULL; op->n = 0;
  return NGS_OK;
}
static int mv_size_u(ngs__file *f, uint64_t *out) { if (mv_dead) return NGS_IOERR; *out = f->n->cur_n; return NGS_OK; }
static int mv_mkdir_u(const char *p) {
  int rc;
  if (mv_find(p)) return NGS_OK;
  if ((rc = mv_tick())) return rc;
  return mv_new(p, 1) ? NGS_OK : NGS_IOERR;
}
static int mv_sync_dir_u(const char *p) {
  int i, rc;
  size_t L = strlen(p);
  if ((rc = mv_tick())) return rc;
  for (i = 0; i < MV_MAX_FILES; i++) {
    mv_node *n = &mv_nodes[i];
    if (n->used && strncmp(n->path, p, L) == 0 && n->path[L] == '/' && !strchr(n->path + L + 1, '/')) n->durable_exists = 1;
  }
  { mv_node *d = mv_find(p); if (d) d->durable_exists = 1; }
  return NGS_OK;
}
static int mv_exists_u(const char *p, int *out) { *out = mv_find(p) != NULL; return NGS_OK; }
static int mv_lock_u(ngs__file *f) {
  if (mv_dead) return NGS_IOERR;
  if (f->n->locked) return NGS_BUSY;
  f->n->locked = 1;
  return NGS_OK;
}
static int mv_random_u(void *buf, size_t n) {
  size_t i;
  for (i = 0; i < n; i++) ((uint8_t *)buf)[i] = (uint8_t)mv_rand();
  return NGS_OK;
}

/* every call holds one lock: the engine now fsyncs while other threads write */
#include <pthread.h>
static pthread_mutex_t mv_mu = PTHREAD_MUTEX_INITIALIZER;
static int mv_open(const char *path, int create, ngs__file **out) { int r; pthread_mutex_lock(&mv_mu); r = mv_open_u(path, create, out); pthread_mutex_unlock(&mv_mu); return r; }
static int mv_close(ngs__file *f) { int r; pthread_mutex_lock(&mv_mu); r = mv_close_u(f); pthread_mutex_unlock(&mv_mu); return r; }
static int mv_pread(ngs__file *f, void *buf, size_t n, uint64_t off, size_t *got) { int r; pthread_mutex_lock(&mv_mu); r = mv_pread_u(f, buf, n, off, got); pthread_mutex_unlock(&mv_mu); return r; }
static int mv_pwrite(ngs__file *f, const void *buf, size_t n, uint64_t off) { int r; pthread_mutex_lock(&mv_mu); r = mv_pwrite_u(f, buf, n, off); pthread_mutex_unlock(&mv_mu); return r; }
static int mv_sync(ngs__file *f) { int r; pthread_mutex_lock(&mv_mu); r = mv_sync_u(f); pthread_mutex_unlock(&mv_mu); return r; }
static int mv_truncate(ngs__file *f, uint64_t size) { int r; pthread_mutex_lock(&mv_mu); r = mv_truncate_u(f, size); pthread_mutex_unlock(&mv_mu); return r; }
static int mv_size(ngs__file *f, uint64_t *out) { int r; pthread_mutex_lock(&mv_mu); r = mv_size_u(f, out); pthread_mutex_unlock(&mv_mu); return r; }
static int mv_mkdir(const char *p) { int r; pthread_mutex_lock(&mv_mu); r = mv_mkdir_u(p); pthread_mutex_unlock(&mv_mu); return r; }
static int mv_sync_dir(const char *p) { int r; pthread_mutex_lock(&mv_mu); r = mv_sync_dir_u(p); pthread_mutex_unlock(&mv_mu); return r; }
static int mv_exists(const char *p, int *out) { int r; pthread_mutex_lock(&mv_mu); r = mv_exists_u(p, out); pthread_mutex_unlock(&mv_mu); return r; }
static int mv_lock(ngs__file *f) { int r; pthread_mutex_lock(&mv_mu); r = mv_lock_u(f); pthread_mutex_unlock(&mv_mu); return r; }
static int mv_random(void *buf, size_t n) { int r; pthread_mutex_lock(&mv_mu); r = mv_random_u(buf, n); pthread_mutex_unlock(&mv_mu); return r; }

static const ngs__vfs mv_vfs = { mv_open, mv_close, mv_pread, mv_pwrite, mv_sync, mv_truncate, mv_size,
                                 mv_mkdir, mv_sync_dir, mv_exists, mv_lock, mv_random };

/* Power loss: rebuild every file from its durable image plus a random subset
** of its queued ops (possibly torn at a 512-byte boundary). */
static void mv_crash(void) {
  int i;
  for (i = 0; i < MV_MAX_FILES; i++) {
    mv_node *x = &mv_nodes[i];
    size_t k;
    if (!x->used) continue;
    if (!x->durable_exists && (mv_rand() & 1)) { mv_clear_ops(x); free(x->cur); free(x->dur); x->used = 0; continue; }
    x->cur_n = 0;
    mv_reserve(x, x->dur_n + 1);
    if (x->dur_n) memcpy(x->cur, x->dur, x->dur_n);
    x->cur_n = x->dur_n;
    for (k = 0; k < x->n_ops; k++) {
      mv_op *op = &x->ops[k];
      if (mv_rand() % 3 == 0) continue;                      /* this op was lost */
      if (op->is_trunc) {
        mv_reserve(x, (size_t)op->off);
        if (op->off > x->cur_n) memset(x->cur + x->cur_n, 0, (size_t)op->off - x->cur_n);
        x->cur_n = (size_t)op->off;
      } else {
        size_t n = op->n;
        if (n > 512 && mv_rand() % 4 == 0) n = (size_t)(mv_rand() % (n / 512 + 1)) * 512;   /* torn */
        mv_reserve(x, (size_t)op->off + n);
        if (op->off > x->cur_n) memset(x->cur + x->cur_n, 0, (size_t)op->off - x->cur_n);
        memcpy(x->cur + op->off, op->data, n);
        if (op->off + n > x->cur_n) x->cur_n = (size_t)(op->off + n);
      }
    }
    mv_clear_ops(x);
    free(x->dur);
    x->dur = (uint8_t *)malloc(x->cur_n ? x->cur_n : 1);
    memcpy(x->dur, x->cur, x->cur_n);
    x->dur_n = x->cur_n;
    x->durable_exists = 1;
    x->locked = 0;
  }
  mv_dead = 0; mv_fail_at = -1;
}

static void mv_reset(void) {
  int i;
  for (i = 0; i < MV_MAX_FILES; i++) if (mv_nodes[i].used) { mv_clear_ops(&mv_nodes[i]); free(mv_nodes[i].cur); free(mv_nodes[i].dur); }
  memset(mv_nodes, 0, sizeof mv_nodes);
  mv_dead = 0; mv_fail_at = -1; mv_ops = 0;
}
#endif
