/*
** bench_50k.c -- the 50K scorecard: 50,000 facts through the amalgamation on a
** real filesystem. Usage: bench_50k <fresh empty parent directory> [N]
** Build: make bench (or cc -std=c11 -O2 -Iinclude bench/bench_50k.c src/nougenshards.c -lpthread)
**
** Phases (each on its own store under the parent directory):
**   A  bulk ingest: N singles with NGS_WRITE_NO_SYNC, ngs_flush every 1,000
**   B  batched ingest: N facts via ngs_remember_many, 100 per durable batch
**   C  durable singles: 2,000 ngs_remember calls, each fdatasync'd (latency)
**   D  8 threads x 250 durable singles (group commit)
**   E  N random ngs_get on store A (latency)
**   F  full ngs_scan of store A
**   G  ngs_verify of store A (every signature and the chain)
**   H  close + reopen of store A
** Every phase checks its own result; any failure exits non-zero.
*/
#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#  define _POSIX_C_SOURCE 200809L
#endif
#include "ngs.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/stat.h>
#include <dirent.h>

static double now_s(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (double)t.tv_sec + (double)t.tv_nsec / 1e9;
}
static int cmp_d(const void *a, const void *b) {
  double x = *(const double *)a, y = *(const double *)b;
  return x < y ? -1 : x > y;
}
static double pct(double *v, size_t n, double p) {
  size_t i = (size_t)(p * (double)(n - 1) + 0.5);
  return v[i < n ? i : n - 1];
}
#define DIE(...) do { fprintf(stderr, __VA_ARGS__); fputc('\n', stderr); exit(1); } while (0)

static void mkbody(char *b, size_t cap, unsigned i) {
  /* about 200 bytes, like a real shard summary */
  snprintf(b, cap, "fact %u: lane phoebus recorded that the deploy region for project kestrel-%u is "
                   "us-east-%u, confirmed by the operator, with rollback window %u minutes and owner "
                   "node %u of the fleet grid (bench body)", i, i % 97, i % 4 + 1, i % 60, i % 9);
}
static ngs_fact_in mkfact(const char *body) {
  ngs_fact_in in = NGS_FACT_IN_INIT;
  in.ns.p = "bench"; in.ns.n = 5; in.kind = NGS_EPISODIC;
  in.title.p = "bench"; in.title.n = 5;
  in.body.p = body; in.body.n = strlen(body);
  return in;
}
static ngs *open_store(const char *parent, const char *name) {
  char dir[1024];
  ngs_open_opts o = NGS_OPEN_OPTS_INIT;
  ngs *db = NULL;
  int rc;
  snprintf(dir, sizeof dir, "%s/%s", parent, name);
  o.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  rc = ngs_open(dir, &o, &db);
  if (rc != NGS_OK) DIE("open %s: %s", dir, ngs_errstr(rc));
  return db;
}
static unsigned long long dir_bytes(const char *path) {
  unsigned long long total = 0;
  DIR *d = opendir(path);
  struct dirent *e;
  if (!d) return 0;
  while ((e = readdir(d)) != NULL) {
    char p[2048];
    struct stat st;
    if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
    snprintf(p, sizeof p, "%s/%s", path, e->d_name);
    if (stat(p, &st) != 0) continue;
    if (S_ISDIR(st.st_mode)) total += dir_bytes(p); else total += (unsigned long long)st.st_size;
  }
  closedir(d);
  return total;
}

typedef struct { ngs *db; int tid; int n; int fails; } wr_arg;
static void *writer(void *p) {
  wr_arg *a = (wr_arg *)p;
  int i;
  for (i = 0; i < a->n; i++) {
    char body[256];
    ngs_fact_in in;
    ngs_id id;
    mkbody(body, sizeof body, (unsigned)(a->tid * 100000 + i));
    in = mkfact(body);
    if (ngs_remember(a->db, &in, 0, &id) != NGS_OK) a->fails++;
  }
  return NULL;
}

int main(int argc, char **argv) {
  const char *parent;
  unsigned n = 50000, i;
  ngs *db;
  ngs_id *ids;
  double t0, t, *lat;
  char body[256], path[1024];
  ngs_stats_t st = NGS_STATS_INIT;
  if (argc < 2) DIE("usage: bench_50k <parent dir> [N]");
  parent = argv[1];
  if (argc > 2) n = (unsigned)strtoul(argv[2], NULL, 10);
  ids = (ngs_id *)malloc(sizeof(ngs_id) * n);
  lat = (double *)malloc(sizeof(double) * (n > 2000 ? n : 2000));
  if (!ids || !lat) DIE("oom");
  printf("NGS 50K scorecard: %s, N=%u, body ~200 B\n", ngs_libversion(), n);

  /* A */
  db = open_store(parent, "a");
  t0 = now_s();
  for (i = 0; i < n; i++) {
    ngs_fact_in in;
    mkbody(body, sizeof body, i);
    in = mkfact(body);
    if (ngs_remember(db, &in, NGS_WRITE_NO_SYNC, &ids[i]) != NGS_OK) DIE("A remember %u: %s", i, ngs_errmsg(db));
    if ((i + 1) % 1000 == 0 && ngs_flush(db) != NGS_OK) DIE("A flush");
  }
  if (ngs_flush(db) != NGS_OK) DIE("A flush");
  t = now_s() - t0;
  printf("A bulk ingest (NO_SYNC, flush/1000): %u facts in %.2f s = %.0f facts/s\n", n, t, n / t);

  /* E */
  srand(1085);
  for (i = 0; i < n; i++) {
    ngs_fact *f = NULL;
    unsigned k = (unsigned)rand() % n;
    double s = now_s();
    if (ngs_get(db, &ids[k], &f) != NGS_OK || !f || f->seq != (uint64_t)k + 1) DIE("E get %u", k);
    lat[i] = now_s() - s;
    ngs_free(f);
  }
  qsort(lat, n, sizeof *lat, cmp_d);
  { double sum = 0; for (i = 0; i < n; i++) sum += lat[i];
    printf("E random get: %u gets in %.2f s = %.0f gets/s, p50 %.1f us, p99 %.1f us\n", n, sum, n / sum,
           pct(lat, n, 0.50) * 1e6, pct(lat, n, 0.99) * 1e6); }

  /* F */
  {
    ngs_scan_opts so = NGS_SCAN_OPTS_INIT;
    ngs_iter *it = NULL;
    ngs_fact *f = NULL;
    unsigned cnt = 0;
    int rc;
    t0 = now_s();
    if (ngs_scan(db, &so, &it) != NGS_OK) DIE("F scan");
    while ((rc = ngs_iter_next(it, &f)) == NGS_OK) { cnt++; ngs_free(f); }
    ngs_iter_close(it);
    t = now_s() - t0;
    if (rc != NGS_NOTFOUND || cnt != n) DIE("F scan saw %u of %u (rc %d)", cnt, n, rc);
    printf("F full scan: %u facts in %.2f s = %.0f facts/s\n", cnt, t, cnt / t);
  }

  /* G */
  t0 = now_s();
  if (ngs_verify(db, NULL, 0) != NGS_OK) DIE("G verify: %s", ngs_errmsg(db));
  t = now_s() - t0;
  printf("G verify (signatures + chain): %u facts in %.2f s = %.0f facts/s\n", n, t, n / t);

  /* H */
  ngs_close(db);
  t0 = now_s();
  db = open_store(parent, "a");
  t = now_s() - t0;
  if (ngs_stats(db, &st) != NGS_OK || st.facts != n) DIE("H stats facts %llu", (unsigned long long)st.facts);
  ngs_close(db);
  snprintf(path, sizeof path, "%s/a", parent);
  { unsigned long long b = dir_bytes(path);
    printf("H reopen: %.3f s; store %.1f MB, %.0f bytes/fact on disk\n", t, b / 1e6, (double)b / n); }

  /* B */
  db = open_store(parent, "b");
  {
    ngs_fact_in in[100];
    char bodies[100][256];
    ngs_id out[100];
    unsigned j, done = 0;
    t0 = now_s();
    while (done < n) {
      unsigned m = n - done < 100 ? n - done : 100;
      for (j = 0; j < m; j++) { mkbody(bodies[j], sizeof bodies[j], done + j); in[j] = mkfact(bodies[j]); }
      if (ngs_remember_many(db, in, m, 0, out) != NGS_OK) DIE("B remember_many: %s", ngs_errmsg(db));
      done += m;
    }
    t = now_s() - t0;
    if (ngs_stats(db, &st) != NGS_OK || st.facts != n) DIE("B stats");
    printf("B batched ingest (remember_many x100, durable): %u facts in %.2f s = %.0f facts/s\n", n, t, n / t);
  }
  ngs_close(db);

  /* C */
  db = open_store(parent, "c");
  for (i = 0; i < 2000; i++) {
    ngs_fact_in in;
    ngs_id id;
    double s;
    mkbody(body, sizeof body, i);
    in = mkfact(body);
    s = now_s();
    if (ngs_remember(db, &in, 0, &id) != NGS_OK) DIE("C remember");
    lat[i] = now_s() - s;
  }
  qsort(lat, 2000, sizeof *lat, cmp_d);
  { double sum = 0; for (i = 0; i < 2000; i++) sum += lat[i];
    printf("C durable singles (1 thread): 2000 facts, %.0f facts/s, p50 %.2f ms, p99 %.2f ms\n", 2000 / sum,
           pct(lat, 2000, 0.50) * 1e3, pct(lat, 2000, 0.99) * 1e3); }
  ngs_close(db);

  /* D */
  db = open_store(parent, "d");
  {
    pthread_t th[8];
    wr_arg a[8];
    int k, fails = 0;
    t0 = now_s();
    for (k = 0; k < 8; k++) { a[k].db = db; a[k].tid = k; a[k].n = 250; a[k].fails = 0; pthread_create(&th[k], NULL, writer, &a[k]); }
    for (k = 0; k < 8; k++) { pthread_join(th[k], NULL); fails += a[k].fails; }
    t = now_s() - t0;
    if (fails || ngs_stats(db, &st) != NGS_OK || st.facts != 2000) DIE("D fails %d", fails);
    if (ngs_verify(db, NULL, 0) != NGS_OK) DIE("D verify");
    printf("D durable singles (8 threads, group commit): 2000 facts in %.2f s = %.0f facts/s\n", t, 2000 / t);
  }
  ngs_close(db);
  printf("SCORECARD OK\n");
  free(ids); free(lat);
  return 0;
}
