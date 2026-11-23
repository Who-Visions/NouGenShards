/* SPDX-License-Identifier: Apache-2.0 */
/* simfs.c -- see simfs.h. Test code: it may use the whole libc. */
#include "simfs.h"

#include <stdlib.h>
#include <string.h>

#define SECT 512u

typedef struct {
  uint8_t *vol; size_t vlen, vcap;
  uint8_t *dur; size_t dlen;
  uint8_t *dirty; size_t nds;          /* one byte per sector */
  int len_dirty;
} sinode;

typedef struct { char *path; sinode *ino; } sname;
typedef struct { int kind; char *a, *b; sinode *ino; } nsop;   /* kind: 1 create(a) 2 rename(a->b) 3 unlink(a) */

typedef struct { sname *v; size_t n, cap; } nsmap;

struct sim {
  ngs_vfs vfs;
  sinode **inodes; size_t ninodes, capinodes;
  nsmap vol, dur;
  nsop *ops; size_t nops, capops;
  char **dirs; size_t ndirs;
  uint64_t op, crash_at, fail_at;
  uint8_t *kinds; size_t kcap;
  int variant, crashed;
  uint64_t rng;
  int64_t clock;
};

typedef struct { ngs_file base; sim *s; sinode *ino; } sfile;

static uint64_t rnd(sim *s) {                      /* xorshift64* */
  uint64_t x = s->rng;
  x ^= x >> 12; x ^= x << 25; x ^= x >> 27;
  s->rng = x;
  return x * 0x2545F4914F6CDD1Dull;
}

static char *dupstr(const char *p) { size_t n = strlen(p); char *q = (char *)malloc(n + 1); memcpy(q, p, n + 1); return q; }

static void parent_of(const char *path, char *out, size_t cap) {
  const char *sl = strrchr(path, '/');
  size_t n = sl ? (size_t)(sl - path) : 0;
  if (n >= cap) n = cap - 1;
  memcpy(out, path, n); out[n] = 0;
}

/* ------------------------------------------------------------- inodes */
static sinode *ino_new(sim *s) {
  sinode *i = (sinode *)calloc(1, sizeof *i);
  if (s->ninodes == s->capinodes) {
    s->capinodes = s->capinodes ? s->capinodes * 2 : 16;
    s->inodes = (sinode **)realloc(s->inodes, s->capinodes * sizeof *s->inodes);
  }
  s->inodes[s->ninodes++] = i;
  return i;
}

static void ino_free(sinode *i) { free(i->vol); free(i->dur); free(i->dirty); free(i); }

static void ino_grow(sinode *i, size_t len) {
  if (len > i->vcap) {
    size_t nc = i->vcap ? i->vcap : 1024;
    while (nc < len) nc *= 2;
    i->vol = (uint8_t *)realloc(i->vol, nc);
    memset(i->vol + i->vcap, 0, nc - i->vcap);
    i->vcap = nc;
  }
  {
    size_t need = (len + SECT - 1) / SECT;
    if (need > i->nds) {
      i->dirty = (uint8_t *)realloc(i->dirty, need);
      memset(i->dirty + i->nds, 0, need - i->nds);
      i->nds = need;
    }
  }
}

static void ino_write(sinode *i, size_t off, const uint8_t *buf, size_t n) {
  size_t end = off + n, k;
  if (!n) return;
  ino_grow(i, end);
  if (off > i->vlen) memset(i->vol + i->vlen, 0, off - i->vlen);
  memcpy(i->vol + off, buf, n);
  if (end > i->vlen) { i->vlen = end; i->len_dirty = 1; }
  for (k = off / SECT; k <= (end - 1) / SECT; k++) i->dirty[k] = 1;
}

static void ino_truncate(sinode *i, size_t len) {
  if (len > i->vlen) { ino_grow(i, len); memset(i->vol + i->vlen, 0, len - i->vlen); }
  else if (len < i->vlen) { memset(i->vol + len, 0, i->vlen - len); }
  if (len != i->vlen) {
    size_t k, from = len / SECT;
    i->len_dirty = 1;
    for (k = from; k < i->nds; k++) i->dirty[k] = (k * SECT < i->vlen || k * SECT < len) ? 1 : 0;
  }
  i->vlen = len;
}

static void ino_sync(sinode *i) {
  free(i->dur);
  i->dur = (uint8_t *)malloc(i->vlen ? i->vlen : 1);
  if (i->vlen) memcpy(i->dur, i->vol, i->vlen);
  i->dlen = i->vlen;
  if (i->dirty) memset(i->dirty, 0, i->nds);
  i->len_dirty = 0;
}

/* power loss for one inode: durable content plus a random subset of the dirty sectors */
static void ino_crash(sim *s, sinode *i, int keep_pct) {
  size_t newlen = (i->len_dirty && (int)(rnd(s) % 100) < keep_pct) ? i->vlen : i->dlen, k;
  uint8_t *res = (uint8_t *)calloc(newlen ? newlen : 1, 1);
  if (i->dur) memcpy(res, i->dur, i->dlen < newlen ? i->dlen : newlen);
  for (k = 0; k < i->nds; k++) {
    size_t a = k * SECT, b = a + SECT;
    if (!i->dirty[k] || (int)(rnd(s) % 100) >= keep_pct) continue;
    if (a >= newlen) continue;
    if (b > newlen) b = newlen;
    if (a < i->vlen) { size_t e = b < i->vlen ? b : i->vlen; memcpy(res + a, i->vol + a, e - a); }
  }
  free(i->vol); free(i->dur); free(i->dirty);
  i->vol = res; i->vlen = newlen; i->vcap = newlen ? newlen : 1;
  i->dur = (uint8_t *)malloc(newlen ? newlen : 1);
  if (newlen) memcpy(i->dur, res, newlen);
  i->dlen = newlen;
  i->nds = (newlen + SECT - 1) / SECT;
  i->dirty = (uint8_t *)calloc(i->nds ? i->nds : 1, 1);
  i->len_dirty = 0;
}

/* ------------------------------------------------------------- names */
static sinode *map_get(const nsmap *m, const char *path) {
  size_t k;
  for (k = 0; k < m->n; k++) if (strcmp(m->v[k].path, path) == 0) return m->v[k].ino;
  return NULL;
}

static void map_set(nsmap *m, const char *path, sinode *ino) {
  size_t k;
  for (k = 0; k < m->n; k++) if (strcmp(m->v[k].path, path) == 0) { m->v[k].ino = ino; return; }
  if (m->n == m->cap) { m->cap = m->cap ? m->cap * 2 : 16; m->v = (sname *)realloc(m->v, m->cap * sizeof *m->v); }
  m->v[m->n].path = dupstr(path); m->v[m->n].ino = ino; m->n++;
}

static void map_del(nsmap *m, const char *path) {
  size_t k;
  for (k = 0; k < m->n; k++) {
    if (strcmp(m->v[k].path, path) == 0) { free(m->v[k].path); m->v[k] = m->v[--m->n]; return; }
  }
}

static void map_clear(nsmap *m) {
  size_t k;
  for (k = 0; k < m->n; k++) free(m->v[k].path);
  m->n = 0;
}

static void op_push(sim *s, int kind, const char *a, const char *b, sinode *ino) {
  if (s->nops == s->capops) { s->capops = s->capops ? s->capops * 2 : 16; s->ops = (nsop *)realloc(s->ops, s->capops * sizeof *s->ops); }
  s->ops[s->nops].kind = kind; s->ops[s->nops].a = dupstr(a); s->ops[s->nops].b = b ? dupstr(b) : NULL; s->ops[s->nops].ino = ino;
  s->nops++;
}

static void op_apply(nsmap *m, const nsop *o) {
  if (o->kind == 1) map_set(m, o->a, o->ino);
  else if (o->kind == 2) { map_set(m, o->b, o->ino); map_del(m, o->a); }
  else if (o->kind == 3) map_del(m, o->a);
}

static void ops_clear(sim *s) {
  size_t k;
  for (k = 0; k < s->nops; k++) { free(s->ops[k].a); free(s->ops[k].b); }
  s->nops = 0;
}

/* ---------------------------------------------------------- fault gate */
enum { G_RUN = 0, G_FAIL, G_BEFORE, G_AFTER, G_PARTIAL, G_DEAD };

static int gate(sim *s, int kind) {
  if (s->crashed) return G_DEAD;
  s->op++;
  if (s->op >= s->kcap) { size_t nc = s->kcap ? s->kcap * 2 : 256; while (nc <= s->op) nc *= 2; s->kinds = (uint8_t *)realloc(s->kinds, nc); memset(s->kinds + s->kcap, 0, nc - s->kcap); s->kcap = nc; }
  s->kinds[s->op] = (uint8_t)kind;
  if (s->fail_at && s->op == s->fail_at) return G_FAIL;
  if (s->crash_at && s->op == s->crash_at) {
    s->crashed = 1;
    return s->variant == SIM_AFTER ? G_AFTER : (s->variant == SIM_PARTIAL ? G_PARTIAL : G_BEFORE);
  }
  return G_RUN;
}

/* ------------------------------------------------------------------ vfs */
static int s_open(ngs_vfs *v, const char *path, int flags, ngs_file **out) {
  sim *s = (sim *)v->ctx;
  sinode *ino = map_get(&s->vol, path);
  sfile *f;
  if (s->crashed) return NGS_IOERR;
  if (!ino) {
    int g;
    char par[512];
    if (!(flags & NGS_VF_CREATE)) return NGS_NOTFOUND;
    g = gate(s, SIMK_OPEN);
    if (g == G_FAIL || g == G_BEFORE || g == G_PARTIAL || g == G_DEAD) return NGS_IOERR;
    ino = ino_new(s);
    map_set(&s->vol, path, ino);
    parent_of(path, par, sizeof par);
    op_push(s, 1, path, NULL, ino);
    if (g == G_AFTER) return NGS_IOERR;
  }
  f = (sfile *)calloc(1, sizeof *f);
  f->base.vfs = v; f->s = s; f->ino = ino;
  *out = &f->base;
  return NGS_OK;
}

static int s_pread(ngs_file *fp, void *buf, size_t n, uint64_t off, size_t *got) {
  sfile *f = (sfile *)fp;
  size_t avail;
  if (f->s->crashed) return NGS_IOERR;
  if (off >= f->ino->vlen) { *got = 0; return NGS_OK; }
  avail = f->ino->vlen - (size_t)off;
  *got = n < avail ? n : avail;
  memcpy(buf, f->ino->vol + off, *got);
  return NGS_OK;
}

static int s_pwrite(ngs_file *fp, const void *buf, size_t n, uint64_t off) {
  sfile *f = (sfile *)fp;
  int g = gate(f->s, SIMK_PWRITE);
  if (g == G_FAIL || g == G_BEFORE || g == G_DEAD) return NGS_IOERR;
  if (g == G_PARTIAL) { ino_write(f->ino, (size_t)off, (const uint8_t *)buf, n ? (size_t)(rnd(f->s) % (n + 1)) : 0); return NGS_IOERR; }
  ino_write(f->ino, (size_t)off, (const uint8_t *)buf, n);
  return g == G_AFTER ? NGS_IOERR : NGS_OK;
}

static int s_fsync(ngs_file *fp) {
  sfile *f = (sfile *)fp;
  int g = gate(f->s, SIMK_FSYNC);
  if (g == G_FAIL || g == G_BEFORE || g == G_PARTIAL || g == G_DEAD) return NGS_IOERR;
  ino_sync(f->ino);
  return g == G_AFTER ? NGS_IOERR : NGS_OK;
}

static int s_truncate(ngs_file *fp, uint64_t len) {
  sfile *f = (sfile *)fp;
  int g = gate(f->s, SIMK_TRUNCATE);
  if (g == G_FAIL || g == G_BEFORE || g == G_PARTIAL || g == G_DEAD) return NGS_IOERR;
  ino_truncate(f->ino, (size_t)len);
  return g == G_AFTER ? NGS_IOERR : NGS_OK;
}

static int s_size(ngs_file *fp, uint64_t *out) {
  sfile *f = (sfile *)fp;
  if (f->s->crashed) return NGS_IOERR;
  *out = f->ino->vlen;
  return NGS_OK;
}

static int s_close(ngs_file *fp) { free(fp); return NGS_OK; }

static int s_rename(ngs_vfs *v, const char *from, const char *to) {
  sim *s = (sim *)v->ctx;
  sinode *ino = map_get(&s->vol, from);
  int g = gate(s, SIMK_RENAME);
  if (g == G_FAIL || g == G_BEFORE || g == G_PARTIAL || g == G_DEAD) return NGS_IOERR;
  if (!ino) return NGS_NOTFOUND;
  map_set(&s->vol, to, ino);
  map_del(&s->vol, from);
  op_push(s, 2, from, to, ino);
  return g == G_AFTER ? NGS_IOERR : NGS_OK;
}

static int s_unlink(ngs_vfs *v, const char *path) {
  sim *s = (sim *)v->ctx;
  int g = gate(s, SIMK_UNLINK);
  if (g == G_FAIL || g == G_BEFORE || g == G_PARTIAL || g == G_DEAD) return NGS_IOERR;
  if (!map_get(&s->vol, path)) return NGS_NOTFOUND;
  map_del(&s->vol, path);
  op_push(s, 3, path, NULL, NULL);
  return g == G_AFTER ? NGS_IOERR : NGS_OK;
}

static int s_mkdir(ngs_vfs *v, const char *path) {
  sim *s = (sim *)v->ctx;
  size_t k;
  int g = gate(s, SIMK_MKDIR);
  if (g == G_FAIL || g == G_BEFORE || g == G_PARTIAL || g == G_DEAD) return NGS_IOERR;
  for (k = 0; k < s->ndirs; k++) if (strcmp(s->dirs[k], path) == 0) return g == G_AFTER ? NGS_IOERR : NGS_OK;
  s->dirs = (char **)realloc(s->dirs, (s->ndirs + 1) * sizeof *s->dirs);
  s->dirs[s->ndirs++] = dupstr(path);
  return g == G_AFTER ? NGS_IOERR : NGS_OK;
}

static int s_fsync_dir(ngs_vfs *v, const char *path) {
  sim *s = (sim *)v->ctx;
  size_t k, w = 0;
  int g = gate(s, SIMK_FSYNCDIR);
  if (g == G_FAIL || g == G_BEFORE || g == G_PARTIAL || g == G_DEAD) return NGS_IOERR;
  for (k = 0; k < s->nops; k++) {
    char par[512];
    parent_of(s->ops[k].kind == 2 ? s->ops[k].b : s->ops[k].a, par, sizeof par);
    if (strcmp(par, path) == 0) { op_apply(&s->dur, &s->ops[k]); free(s->ops[k].a); free(s->ops[k].b); }
    else s->ops[w++] = s->ops[k];
  }
  s->nops = w;
  return g == G_AFTER ? NGS_IOERR : NGS_OK;
}

static int s_list(ngs_vfs *v, const char *dir, int (*cb)(void *arg, const char *name), void *arg) {
  sim *s = (sim *)v->ctx;
  size_t k, dl = strlen(dir);
  int rc;
  if (s->crashed) return NGS_IOERR;
  for (k = 0; k < s->ndirs; k++) if (strcmp(s->dirs[k], dir) == 0) break;
  if (k == s->ndirs) return NGS_NOTFOUND;
  for (k = 0; k < s->vol.n; k++) {
    const char *p = s->vol.v[k].path;
    if (strncmp(p, dir, dl) == 0 && p[dl] == '/' && strchr(p + dl + 1, '/') == NULL) {
      rc = cb(arg, p + dl + 1);
      if (rc) return rc;
    }
  }
  return NGS_OK;
}

static int s_lock(ngs_vfs *v, const char *path, ngs_file **out) {
  sfile *f;
  (void)path;
  if (((sim *)v->ctx)->crashed) return NGS_IOERR;
  f = (sfile *)calloc(1, sizeof *f);
  f->base.vfs = v; f->s = (sim *)v->ctx; f->ino = NULL;
  *out = &f->base;
  return NGS_OK;
}

static int64_t s_now(ngs_vfs *v) { sim *s = (sim *)v->ctx; s->clock += 1000; return s->clock; }

static int s_random(ngs_vfs *v, void *buf, size_t n) {
  sim *s = (sim *)v->ctx;
  size_t i;
  for (i = 0; i < n; i++) ((uint8_t *)buf)[i] = (uint8_t)(rnd(s) >> 24);
  return NGS_OK;
}

/* ------------------------------------------------------------------ api */
sim *sim_new(uint64_t seed) {
  sim *s = (sim *)calloc(1, sizeof *s);
  s->rng = seed ? seed : 88172645463325252ull;
  s->clock = 1700000000000000ll;
  s->vfs.ctx = s;
  s->vfs.open = s_open; s->vfs.pread = s_pread; s->vfs.pwrite = s_pwrite; s->vfs.fsync = s_fsync;
  s->vfs.truncate = s_truncate; s->vfs.size = s_size; s->vfs.close = s_close; s->vfs.rename = s_rename;
  s->vfs.unlink = s_unlink; s->vfs.mkdir = s_mkdir; s->vfs.fsync_dir = s_fsync_dir; s->vfs.list = s_list;
  s->vfs.lock = s_lock; s->vfs.now_us = s_now; s->vfs.random = s_random;
  return s;
}

void sim_free(sim *s) {
  size_t k;
  if (!s) return;
  for (k = 0; k < s->ninodes; k++) ino_free(s->inodes[k]);
  free(s->inodes); free(s->kinds);
  map_clear(&s->vol); map_clear(&s->dur); free(s->vol.v); free(s->dur.v);
  ops_clear(s); free(s->ops);
  for (k = 0; k < s->ndirs; k++) free(s->dirs[k]);
  free(s->dirs);
  free(s);
}

ngs_vfs *sim_vfs(sim *s) { return &s->vfs; }
int sim_op_kind(sim *s, uint64_t op) { return op < s->kcap ? s->kinds[op] : 0; }
void sim_reset_ops(sim *s) { s->op = 0; s->crash_at = 0; s->fail_at = 0; }
uint64_t sim_ops(sim *s) { return s->op; }
void sim_arm_crash(sim *s, uint64_t op, int variant) { s->crash_at = op; s->variant = variant; }
void sim_arm_fail(sim *s, uint64_t op) { s->fail_at = op; }
int sim_crashed(sim *s) { return s->crashed; }

void sim_clean_shutdown(sim *s) {
  size_t k;
  for (k = 0; k < s->nops; k++) op_apply(&s->dur, &s->ops[k]);
  ops_clear(s);
  for (k = 0; k < s->ninodes; k++) ino_sync(s->inodes[k]);
  s->crashed = 0; s->crash_at = 0; s->fail_at = 0; s->op = 0;
}

void sim_reboot(sim *s, uint64_t seed, int keep_pct, int ns_keep_pct) {
  size_t k, cut;
  nsmap res = { NULL, 0, 0 };
  s->rng = seed ? seed : 1;
  for (k = 0; k < s->dur.n; k++) map_set(&res, s->dur.v[k].path, s->dur.v[k].ino);
  cut = ((int)(rnd(s) % 100) < ns_keep_pct) ? s->nops : (s->nops ? (size_t)(rnd(s) % (s->nops + 1)) : 0);
  for (k = 0; k < cut; k++) op_apply(&res, &s->ops[k]);
  ops_clear(s);
  map_clear(&s->dur); free(s->dur.v);
  s->dur = res;
  /* only inodes still named survive; resolve their content */
  for (k = 0; k < s->ninodes; k++) {
    size_t j; int named = 0;
    for (j = 0; j < s->dur.n; j++) if (s->dur.v[j].ino == s->inodes[k]) { named = 1; break; }
    if (named) ino_crash(s, s->inodes[k], keep_pct);
  }
  map_clear(&s->vol);
  for (k = 0; k < s->dur.n; k++) map_set(&s->vol, s->dur.v[k].path, s->dur.v[k].ino);
  s->crashed = 0; s->crash_at = 0; s->fail_at = 0; s->op = 0;
}

int sim_flip(sim *s, const char *path, size_t offset, uint8_t xor_mask) {
  sinode *i = map_get(&s->vol, path);
  if (!i || offset >= i->vlen) return -1;
  i->vol[offset] ^= xor_mask;
  if (i->dur && offset < i->dlen) i->dur[offset] ^= xor_mask;
  return 0;
}

long sim_file_len(sim *s, const char *path) {
  sinode *i = map_get(&s->vol, path);
  return i ? (long)i->vlen : -1;
}

int sim_truncate_durable(sim *s, const char *path, size_t len) {
  sinode *i = map_get(&s->vol, path);
  if (!i || len > i->vlen) return -1;
  i->vlen = len; i->dlen = len;
  return 0;
}

size_t sim_count_names(sim *s, const char *dir) {
  size_t k, n = 0, dl = strlen(dir);
  for (k = 0; k < s->vol.n; k++) {
    const char *p = s->vol.v[k].path;
    if (strncmp(p, dir, dl) == 0 && p[dl] == '/' && strchr(p + dl + 1, '/') == NULL) n++;
  }
  return n;
}
