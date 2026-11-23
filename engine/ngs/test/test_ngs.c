/*
** test_ngs.c -- NGS M1 tests: API round trips, misuse, bit-flip detection,
** live corruption, threads, and the crash / power-loss suite over memvfs.
** Build: cc -std=c11 -Iinclude test/test_ngs.c src/<each>.c -lpthread
*/
#include "memvfs.h"
#include <pthread.h>
#include <math.h>

static int checks, failures;
#define CHECK(c) do { checks++; if (!(c)) { failures++; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define S(lit) ((ngs_str){ lit, sizeof(lit) - 1 })

static ngs *open_db(const char *dir, int32_t flags) {
  ngs_open_opts o = NGS_OPEN_OPTS_INIT;
  ngs *db = NULL;
  int rc;
  o.flags = flags;
  o.segment_bytes = 8192;              /* small, so tests cross segment boundaries */
  rc = ngs_open(dir, &o, &db);
  if (rc) { fprintf(stderr, "  open %s: rc %d: %s\n", dir, rc, ngs_errmsg(db)); ngs_close(db); return NULL; }
  return db;
}

static ngs_fact_in fact(const char *ns, const char *title, const char *body) {
  ngs_fact_in f = NGS_FACT_IN_INIT;
  f.ns.p = ns; f.ns.n = strlen(ns);
  f.kind = NGS_SEMANTIC;
  f.title.p = title; f.title.n = strlen(title);
  f.body.p = body; f.body.n = strlen(body);
  return f;
}

/* ----------------------------------------------------------------- */
static void test_roundtrip(void) {
  ngs *db;
  ngs_id id, id2;
  ngs_fact *f = NULL;
  ngs_pubkey pk1, pk2;
  ngs_fact_in in = fact("kestrel", "deploy region", "us-east-2, confirmed by the operator");
  ngs_str tags[2];
  uint8_t attrs[] = { 0xa1, 0x01, 0x18, 0x2a };      /* {1: 42} canonical */
  float v[3] = { 0.6f, 0.8f, 0.0f };
  ngs_vec vec;
  mv_reset();
  db = open_db("/db", NGS_OPEN_READWRITE | NGS_OPEN_CREATE);
  CHECK(db != NULL);
  if (!db) return;
  tags[0] = S("infra"); tags[1] = S("ünïcode");
  in.tags = tags; in.n_tags = 2;
  in.attrs_cbor = attrs; in.attrs_len = sizeof attrs; in.schema = 3;
  in.t_event = 1700000000000000;
  vec.model_id = S("nomic-embed-text"); vec.dim = 3; vec.version = 1; vec.v = v;
  in.vecs = &vec; in.n_vecs = 1;
  CHECK(ngs_remember(db, &in, 0, &id) == NGS_OK);
  CHECK(ngs_get(db, &id, &f) == NGS_OK);
  if (f) {
    CHECK(f->size == sizeof *f);
    CHECK(memcmp(f->id.b, id.b, 32) == 0);
    CHECK(f->ns.n == 7 && memcmp(f->ns.p, "kestrel", 7) == 0);
    CHECK(f->kind == NGS_SEMANTIC && f->seq == 1);
    CHECK(f->t_event == 1700000000000000 && f->valid_from == f->t_event && f->valid_to == NGS_TIME_MAX);
    CHECK(f->t_record > 0);
    CHECK(f->body.n == strlen("us-east-2, confirmed by the operator") && memcmp(f->body.p, "us-east-2", 9) == 0);
    CHECK(f->n_tags == 2 && f->tags[1].n == strlen("ünïcode"));
    CHECK(f->attrs_len == 4 && memcmp(f->attrs_cbor, attrs, 4) == 0 && f->schema == 3);
    CHECK(((uintptr_t)f % 16) == 0);
    ngs_free(f);
  }
  CHECK(ngs_node_pubkey(db, &pk1) == NGS_OK);
  {   /* a second fact chains to the first */
    ngs_fact_in b = fact("kestrel", "second", "x");
    CHECK(ngs_remember(db, &b, 0, &id2) == NGS_OK);
    CHECK(ngs_get(db, &id2, &f) == NGS_OK);
    if (f) { CHECK(f->seq == 2); ngs_free(f); }
  }
  CHECK(ngs_verify(db, NULL, 0) == NGS_OK);
  CHECK(ngs_close(db) == NGS_OK);
  /* reopen: same key, same facts, the fact outlives a closed handle */
  db = open_db("/db", NGS_OPEN_READWRITE);
  CHECK(db != NULL);
  if (!db) return;
  CHECK(ngs_node_pubkey(db, &pk2) == NGS_OK && memcmp(pk1.b, pk2.b, 32) == 0);
  CHECK(ngs_get(db, &id, &f) == NGS_OK);
  CHECK(ngs_close(db) == NGS_OK);
  if (f) { CHECK(f->title.n == 13 && memcmp(f->title.p, "deploy region", 13) == 0); ngs_free(f); }
  /* read-only open works, writes are refused */
  db = open_db("/db", NGS_OPEN_READONLY);
  CHECK(db != NULL);
  if (db) {
    ngs_fact_in c = fact("kestrel", "ro", "ro");
    CHECK(ngs_get(db, &id2, &f) == NGS_OK); ngs_free(f);
    CHECK(ngs_remember(db, &c, 0, NULL) == NGS_MISUSE);
    ngs_close(db);
  }
}

static void test_batch_scan_and_segments(void) {
  ngs *db;
  ngs_fact_in in[5];
  ngs_id ids[5];
  ngs_iter *it;
  ngs_fact *f;
  int n, i;
  char body[2000];
  ngs_stats_t st = NGS_STATS_INIT;
  mv_reset();
  db = open_db("/db", NGS_OPEN_READWRITE | NGS_OPEN_CREATE);
  if (!db) { CHECK(0); return; }
  memset(body, 'b', sizeof body - 1); body[sizeof body - 1] = 0;
  for (i = 0; i < 5; i++) in[i] = fact(i % 2 ? "osprey" : "heron", "batch", body);
  CHECK(ngs_remember_many(db, in, 5, 0, ids) == NGS_OK);
  for (i = 0; i < 20; i++) { ngs_fact_in x = fact("heron", "more", body); CHECK(ngs_remember(db, &x, 0, NULL) == NGS_OK); }
  CHECK(ngs_stats(db, &st) == NGS_OK && st.facts == 25 && st.log_bytes > 8192);
  /* scan by namespace, in log order, with gapless seqs */
  {
    ngs_scan_opts so = NGS_SCAN_OPTS_INIT;
    uint64_t want = 1;
    so.ns = S("heron");
    CHECK(ngs_scan(db, &so, &it) == NGS_OK);
    n = 0;
    while (ngs_iter_next(it, &f) == NGS_OK) { CHECK(f->seq == want); want++; n++; ngs_free(f); }
    ngs_iter_close(it);
    CHECK(n == 23);
  }
  CHECK(ngs_verify(db, NULL, 0) == NGS_OK);
  ngs_close(db);
  db = open_db("/db", NGS_OPEN_READWRITE);     /* replay across several segments */
  CHECK(db != NULL);
  if (db) { CHECK(ngs_verify(db, NULL, 0) == NGS_OK); CHECK(ngs_stats(db, &st) == NGS_OK && st.facts == 25); ngs_close(db); }
}

static void test_misuse(void) {
  ngs *db, *db2 = NULL;
  ngs_fact_in in;
  ngs_id id, other;
  float bad[2] = { 1.0f, 0.0f };
  ngs_vec v;
  ngs_results *res = (ngs_results *)1;
  ngs_open_opts o = NGS_OPEN_OPTS_INIT;
  mv_reset();
  db = open_db("/db", NGS_OPEN_READWRITE | NGS_OPEN_CREATE);
  if (!db) { CHECK(0); return; }
  in = fact("ns", "t", "b"); in.kind = 0;           CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE);
  in = fact("", "t", "b");                           CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE);
  in = fact("ns", "t", "b"); in.body.p = NULL; in.body.n = 3; CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE);
  in = fact("ns", "t", "\xc0\xaf");                  CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE);   /* overlong UTF-8 */
  in = fact("ns", "t", "b"); in.salience0 = NAN;      CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE);
  in = fact("ns", "t", "b"); in.salience0 = 1.5f;     CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE);
  in = fact("ns", "t", "b"); in.size = 4;             CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE);
  in = fact("ns", "t", "b"); in.t_event = NGS_TIME_MAX; CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE);
  in = fact("ns", "t", "b"); in.supersedes = &other;  CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE);
  bad[1] = INFINITY;
  v.model_id = S("m"); v.dim = 2; v.version = 1; v.v = bad;
  in = fact("ns", "t", "b"); in.vecs = &v; in.n_vecs = 1; CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE);
  {
    static char big[NGS_MAX_TITLE_LEN + 2];
    memset(big, 'x', sizeof big - 1);
    in = fact("ns", big, "b");                       CHECK(ngs_remember(db, &in, 0, &id) == NGS_TOOBIG);
  }
  {
    uint8_t notmap[] = { 0x01 };
    in = fact("ns", "t", "b"); in.attrs_cbor = notmap; in.attrs_len = 1; CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE);
  }
  CHECK(strlen(ngs_errmsg(db)) > 0);
  in = fact("ns", "t", "b");
  CHECK(ngs_remember(db, &in, 0x80, &id) == NGS_MISUSE);
  /* a batch with one bad fact writes nothing */
  {
    ngs_fact_in two[2];
    ngs_stats_t st = NGS_STATS_INIT;
    two[0] = fact("ns", "ok", "ok"); two[1] = fact("ns", "bad", "bad"); two[1].kind = 9;
    CHECK(ngs_remember_many(db, two, 2, 0, NULL) == NGS_MISUSE);
    CHECK(ngs_stats(db, &st) == NGS_OK && st.facts == 0);
  }
  memset(&other, 7, sizeof other);
  { ngs_fact *f = NULL; CHECK(ngs_get(db, &other, &f) == NGS_NOTFOUND && f == NULL); }
  /* everything outside M1 is NGS_MISUSE */
  CHECK(ngs_recall(db, NULL, &res) == NGS_MISUSE && res == NULL);
  CHECK(ngs_invalidate(db, &other, S("r")) == NGS_MISUSE);
  CHECK(ngs_link(db, &other, &other, S("r"), 1.0f, NULL) == NGS_MISUSE);
  CHECK(ngs_redact(db, &other, S("r")) == NGS_MISUSE);
  CHECK(ngs_grant(db, S("ns"), NULL, NULL) == NGS_MISUSE);
  CHECK(ngs_mark(db, &other, NGS_MARK_USED) == NGS_MISUSE);
  CHECK(ngs_checkpoint(db, NULL, NULL) == NGS_MISUSE);
  CHECK(ngs_rebuild(db) == NGS_MISUSE);
  CHECK(ngs_heads(db, NULL, NULL) == NGS_MISUSE);
  CHECK(ngs_sync_export(db, NULL, 0, NULL, NULL) == NGS_MISUSE);
  CHECK(ngs_sync_import(db, NULL, 0, NULL) == NGS_MISUSE);
  CHECK(ngs_as_of(db, 0, 0, NULL, &res) == NGS_MISUSE);
  CHECK(ngs_verify(db, (const uint8_t *)"x", 1) == NGS_MISUSE);
  /* the writer lock is exclusive */
  o.flags = NGS_OPEN_READWRITE;
  CHECK(ngs_open("/db", &o, &db2) == NGS_BUSY);
  ngs_close(db2);
  CHECK(ngs_open("/nope", &o, &db2) == NGS_NOTFOUND);
  ngs_close(db2);
  o.flags = NGS_OPEN_READONLY | NGS_OPEN_CREATE;
  CHECK(ngs_open("/db", &o, &db2) == NGS_MISUSE);
  ngs_close(db2);
  CHECK(ngs_errstr(NGS_CORRUPT)[0] != 0 && ngs_libversion_number() == NGS_VERSION_NUMBER);
  ngs_close(db);
}

/* Write a log, then flip every bit-position class: header, length, type,
** payload, CRC. Every flip must be refused at open or by ngs_verify, or (only
** inside the final write) be truncated as a torn tail. Wrong data is never
** returned. */
static void test_bitflips(int *refused, int *truncated, int *trials) {
  ngs_id ids[12];
  int t;
  for (t = 0; t < 400; t++) {
    ngs *db;
    mv_node *seg;
    size_t pos;
    int i, rc, all_ok = 1, got_wrong = 0;
    ngs_open_opts o = NGS_OPEN_OPTS_INIT;
    mv_reset();
    mv_rng = 0x9e3779b97f4a7c15ull ^ (uint64_t)t;
    db = open_db("/db", NGS_OPEN_READWRITE | NGS_OPEN_CREATE);
    if (!db) { CHECK(0); return; }
    for (i = 0; i < 12; i++) {
      char body[64];
      ngs_fact_in in;
      snprintf(body, sizeof body, "fact number %d", i);
      in = fact("kestrel", "flip", body);
      ngs_remember(db, &in, 0, &ids[i]);
    }
    ngs_close(db);
    seg = mv_find("/db/log/000001.seg");
    if (!seg || seg->dur_n <= 64) { CHECK(0); return; }
    pos = (size_t)(mv_rand() % seg->dur_n);
    seg->dur[pos] ^= (uint8_t)(1u << (mv_rand() % 8));
    memcpy(seg->cur, seg->dur, seg->dur_n);
    (*trials)++;
    o.flags = NGS_OPEN_READWRITE;
    db = NULL;
    rc = ngs_open("/db", &o, &db);
    if (rc == NGS_CORRUPT) { (*refused)++; ngs_close(db); continue; }
    CHECK(rc == NGS_OK);
    if (rc) { ngs_close(db); continue; }
    if (ngs_verify(db, NULL, 0) == NGS_CORRUPT) { (*refused)++; ngs_close(db); continue; }
    /* opened and verified: every surviving fact must be exactly right */
    for (i = 0; i < 12; i++) {
      ngs_fact *f = NULL;
      char body[64];
      snprintf(body, sizeof body, "fact number %d", i);
      if (ngs_get(db, &ids[i], &f) != NGS_OK) { all_ok = 0; continue; }
      if (f->body.n != strlen(body) || memcmp(f->body.p, body, f->body.n) != 0) got_wrong = 1;
      ngs_free(f);
    }
    CHECK(!got_wrong);
    if (!all_ok) (*truncated)++;
    else {
      /* the flip landed in bytes that carry no meaning (none should exist) */
      fprintf(stderr, "  note: flip at %zu of %zu went unnoticed\n", pos, seg->dur_n);
      CHECK(0);
    }
    ngs_close(db);
  }
}

/* A byte changed under a live handle is caught by get and by verify. */
static void test_live_corruption(void) {
  ngs *db;
  ngs_id id[3];
  ngs_fact *f = NULL;
  mv_node *seg;
  int i;
  mv_reset();
  db = open_db("/db", NGS_OPEN_READWRITE | NGS_OPEN_CREATE);
  if (!db) { CHECK(0); return; }
  for (i = 0; i < 3; i++) { ngs_fact_in in = fact("ns", "live", "some body text"); ngs_remember(db, &in, 0, &id[i]); }
  seg = mv_find("/db/log/000001.seg");
  {   /* flip one bit in the middle of the second record */
    uint64_t off = 64, len0 = 0;
    memcpy(&len0, seg->cur + off, 4);        /* little-endian host assumed by this test only */
    off += len0 + 9;
    seg->cur[off + 20] ^= 0x10;
  }
  CHECK(ngs_get(db, &id[1], &f) == NGS_CORRUPT && f == NULL);
  CHECK(ngs_get(db, &id[0], &f) == NGS_OK); ngs_free(f);
  CHECK(ngs_verify(db, NULL, 0) == NGS_CORRUPT);
  ngs_close(db);
  /* and on reopen the damage is below a later durable record: refused */
  {
    ngs_open_opts o = NGS_OPEN_OPTS_INIT;
    ngs *db2 = NULL;
    memcpy(seg->dur, seg->cur, seg->cur_n);
    o.flags = NGS_OPEN_READWRITE;
    CHECK(ngs_open("/db", &o, &db2) == NGS_CORRUPT);
    ngs_close(db2);
  }
}

/* ------------------------------ threads ------------------------------ */
typedef struct { ngs *db; int t; ngs_id ids[50]; int ok; } thr_arg;
static void *writer_thread(void *p) {
  thr_arg *a = (thr_arg *)p;
  int i;
  char ns[16];
  snprintf(ns, sizeof ns, "w%d", a->t % 2);
  for (i = 0; i < 50; i++) {
    ngs_fact_in in = fact(ns, "thread", "concurrent write");
    if (ngs_remember(a->db, &in, i % 3 ? NGS_WRITE_NO_SYNC : 0, &a->ids[i]) == NGS_OK) a->ok++;
    if (i % 7 == 0) {
      ngs_fact *f = NULL;
      if (i && ngs_get(a->db, &a->ids[i - 1], &f) == NGS_OK) ngs_free(f);
    }
  }
  return NULL;
}
static void test_threads(void) {
  ngs *db;
  pthread_t th[6];
  thr_arg args[6];
  int i, j;
  mv_reset();
  db = open_db("/db", NGS_OPEN_READWRITE | NGS_OPEN_CREATE);
  if (!db) { CHECK(0); return; }
  for (i = 0; i < 6; i++) { memset(&args[i], 0, sizeof args[i]); args[i].db = db; args[i].t = i; pthread_create(&th[i], NULL, writer_thread, &args[i]); }
  for (i = 0; i < 6; i++) pthread_join(th[i], NULL);
  CHECK(ngs_flush(db) == NGS_OK);
  for (i = 0; i < 6; i++) {
    CHECK(args[i].ok == 50);
    for (j = 0; j < 50; j++) { ngs_fact *f = NULL; CHECK(ngs_get(db, &args[i].ids[j], &f) == NGS_OK); ngs_free(f); }
  }
  CHECK(ngs_verify(db, NULL, 0) == NGS_OK);
  ngs_close(db);
}

/* --------------------------- crash suite ---------------------------
** One fixed workload. Run it once to count its mutating I/O calls; then for
** every call k, rerun it with the process killed at call k, cut the power
** (random persistence of unsynced writes, tearing, reordering), reopen and
** check: open succeeds, ngs_verify passes, every acknowledged-durable fact is
** there and exact, every batch is all-or-nothing, and the log takes new
** writes. Each kill point runs with several power-loss seeds. */
#define WL_STEPS 14
typedef struct { ngs_id id; char body[48]; } ack_t;

static int run_workload(ack_t *acked, int *n_acked) {
  ngs *db;
  int step, i;
  ack_t pending[8];
  int n_pending = 0;
  db = open_db("/db", NGS_OPEN_READWRITE | NGS_OPEN_CREATE);
  if (!db) return -1;
  for (step = 0; step < WL_STEPS; step++) {
    if (step % 4 == 3) {                       /* atomic batch of 3, fsync */
      ngs_fact_in in[3];
      ngs_id ids[3];
      ack_t a[3];
      for (i = 0; i < 3; i++) { snprintf(a[i].body, sizeof a[i].body, "batch %d item %d of 3", step, i); in[i] = fact("crash", "batch", a[i].body); }
      if (ngs_remember_many(db, in, 3, 0, ids) == NGS_OK) {
        for (i = 0; i < 3; i++) { a[i].id = ids[i]; acked[(*n_acked)++] = a[i]; }
      }
    } else if (step % 4 == 1) {                /* NO_SYNC: durable only after flush */
      ngs_fact_in in;
      ack_t a;
      snprintf(a.body, sizeof a.body, "nosync %d", step);
      in = fact("crash", "nosync", a.body);
      if (ngs_remember(db, &in, NGS_WRITE_NO_SYNC, &a.id) == NGS_OK) pending[n_pending++] = a;
    } else {
      ngs_fact_in in;
      ack_t a;
      snprintf(a.body, sizeof a.body, "single %d with padding to cross sectors", step);
      in = fact(step % 2 ? "crash" : "other", "single", a.body);
      if (ngs_remember(db, &in, 0, &a.id) == NGS_OK) {
        acked[(*n_acked)++] = a;
        /* a synced write also made every earlier NO_SYNC write durable */
        for (i = 0; i < n_pending; i++) acked[(*n_acked)++] = pending[i];
        n_pending = 0;
      }
    }
    if (step == 9 && ngs_flush(db) == NGS_OK) {
      for (i = 0; i < n_pending; i++) acked[(*n_acked)++] = pending[i];
      n_pending = 0;
    }
  }
  ngs_close(db);
  return 0;
}

static void test_crash_suite(long *points, long *runs) {
  ack_t acked[64];
  int n_acked = 0;
  long total, k;
  int seed;
  mv_reset();
  run_workload(acked, &n_acked);
  total = mv_ops;
  *points = total;
  for (k = 1; k <= total; k++) {
    for (seed = 0; seed < 6; seed++) {
      ngs *db;
      int i, rc;
      ngs_open_opts o = NGS_OPEN_OPTS_INIT;
      n_acked = 0;
      mv_reset();
      mv_rng = 0x2545F4914F6CDD1Dull * (uint64_t)(k * 7 + seed + 1);
      mv_fail_at = k;
      run_workload(acked, &n_acked);
      mv_crash();
      (*runs)++;
      o.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
      o.segment_bytes = 8192;
      db = NULL;
      rc = ngs_open("/db", &o, &db);
      if (rc) {
        fprintf(stderr, "  crash point %ld seed %d: reopen rc %d (%s)\n", k, seed, rc, ngs_errmsg(db));
        CHECK(rc == NGS_OK);
        ngs_close(db);
        continue;
      }
      CHECK(ngs_verify(db, NULL, 0) == NGS_OK);
      for (i = 0; i < n_acked; i++) {
        ngs_fact *f = NULL;
        rc = ngs_get(db, &acked[i].id, &f);
        if (rc != NGS_OK) fprintf(stderr, "  crash point %ld seed %d: acknowledged fact '%s' lost (rc %d)\n", k, seed, acked[i].body, rc);
        CHECK(rc == NGS_OK);
        if (f) { CHECK(f->body.n == strlen(acked[i].body) && memcmp(f->body.p, acked[i].body, f->body.n) == 0); ngs_free(f); }
      }
      {   /* batches all-or-nothing */
        ngs_iter *it;
        ngs_fact *f;
        int per_batch[WL_STEPS];
        memset(per_batch, 0, sizeof per_batch);
        if (ngs_scan(db, NULL, &it) == NGS_OK) {
          while (ngs_iter_next(it, &f) == NGS_OK) {
            int st, item;
            if (sscanf(f->body.p, "batch %d item %d", &st, &item) == 2 && st >= 0 && st < WL_STEPS) per_batch[st]++;
            ngs_free(f);
          }
          ngs_iter_close(it);
        }
        for (i = 0; i < WL_STEPS; i++) {
          if (per_batch[i] != 0 && per_batch[i] != 3) fprintf(stderr, "  crash point %ld seed %d: batch %d half-visible (%d of 3)\n", k, seed, i, per_batch[i]);
          CHECK(per_batch[i] == 0 || per_batch[i] == 3);
        }
      }
      {   /* the recovered log accepts new writes and still verifies */
        ngs_fact_in in = fact("crash", "after", "written after recovery");
        ngs_id id;
        CHECK(ngs_remember(db, &in, 0, &id) == NGS_OK);
        CHECK(ngs_verify(db, NULL, 0) == NGS_OK);
      }
      ngs_close(db);
    }
  }
}

int main(void) {
  int refused = 0, truncated = 0, trials = 0;
  long points = 0, runs = 0;
  ngs__vfs_set(&mv_vfs);
  test_roundtrip();
  test_batch_scan_and_segments();
  test_misuse();
  test_live_corruption();
  test_threads();
  test_bitflips(&refused, &truncated, &trials);
  test_crash_suite(&points, &runs);
  printf("bit flips: %d trials, %d refused (open or verify), %d truncated as a torn tail (final write only)\n", trials, refused, truncated);
  printf("crash suite: %ld injection points x 6 power-loss seeds = %ld runs\n", points, runs);
  printf("ngs M1 tests: %d checks, %d failures\n", checks, failures);
  mv_reset();
  return failures ? 1 : 0;
}
