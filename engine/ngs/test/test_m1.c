/* test_m1.c -- M1 unit + behaviour tests for the meta-app NGS entry.
**
** Covers: known-answer vectors for every primitive written from spec
** (BLAKE3, SHA-512, CRC32C, Ed25519), remember/get round-trips, per-
** namespace sequences, scan ordering and filters, checkpoint/verify,
** the NGS_MISUSE surface, writer-lock exclusion, read-only opens, and
** persistence across reopen. Tamper and crash behaviour live in
** crash_harness.c.
**
** Exit status 0 = all checks passed.
*/
#include "ngs.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <pthread.h>

static int g_pass = 0, g_fail = 0;
#define CHECK(cond, name) do { \
    if (cond) { g_pass++; } \
    else { g_fail++; printf("FAIL: %s (%s:%d)\n", name, __FILE__, __LINE__); } \
  } while (0)

/* The amalgamation's internals are not exported; the KATs reach the
** primitives through kat_shim.c, which #includes the amalgamation and
** exposes these wrappers. The test binary links the shim object INSTEAD
** of the plain engine object (the shim already contains the engine). */
void ngs_test_blake3(const uint8_t *in, size_t n, uint8_t out[32]);
void ngs_test_sha512(const uint8_t *in, size_t n, uint8_t out[64]);
uint32_t ngs_test_crc32c(const uint8_t *in, size_t n);
void ngs_test_ed_keypair(const uint8_t seed[32], uint8_t pub[32]);
void ngs_test_ed_sign(const uint8_t seed[32], const uint8_t *msg, size_t n, uint8_t sig[64]);
int ngs_test_ed_verify(const uint8_t pub[32], const uint8_t *msg, size_t n, const uint8_t sig[64]);
void ngs_test_blake3_chunks(const uint8_t *in, size_t n, const size_t *chunks, size_t nchunks, uint8_t out[32]);

static ngs_str S(const char *z) { ngs_str s; s.p = z; s.n = strlen(z); return s; }

static int hexval(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}
static void unhex(const char *hex, uint8_t *out, size_t n) {
  size_t i;
  for (i = 0; i < n; i++) out[i] = (uint8_t)(hexval(hex[2 * i]) * 16 + hexval(hex[2 * i + 1]));
}
static int hexeq(const uint8_t *got, const char *hex, size_t n) {
  uint8_t want[64];
  unhex(hex, want, n);
  return memcmp(got, want, n) == 0;
}

static char g_dir[256];
static void fresh_dir(void) {
  snprintf(g_dir, sizeof g_dir, "/tmp/ngs-test-XXXXXX");
  if (!mkdtemp(g_dir)) { perror("mkdtemp"); exit(2); }
}
static void wipe_dir(void) {
  char cmd[600];
  snprintf(cmd, sizeof cmd, "rm -rf '%s'", g_dir);
  if (system(cmd) != 0) { /* best effort */ }
}

static ngs_fact_in mk_input(const char *ns, const char *title, const char *body) {
  ngs_fact_in in = NGS_FACT_IN_INIT;
  in.ns = S(ns);
  in.kind = NGS_SEMANTIC;
  in.title = S(title);
  in.body = S(body);
  return in;
}

static void test_kats(void) {
  uint8_t out[64];
  ngs_test_blake3((const uint8_t *)"", 0, out);
  CHECK(hexeq(out, "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262", 32),
        "KAT BLAKE3 empty");
  ngs_test_blake3((const uint8_t *)"abc", 3, out);
  CHECK(hexeq(out, "6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85", 32),
        "KAT BLAKE3 abc");

  /* multi-chunk agreement: a >1024-byte input fed in awkward chunk sizes
  ** must equal the one-shot hash (exercises the chunk/CV stack). */
  {
    static uint8_t big[100000];
    uint8_t one[32], two[32];
    size_t i;
    size_t chunks[] = {1, 1023, 1024, 1025, 4096, 65536, 7, 8192};
    for (i = 0; i < sizeof big; i++) big[i] = (uint8_t)(i * 31 + 7);
    ngs_test_blake3(big, sizeof big, one);
    ngs_test_blake3_chunks(big, sizeof big, chunks, sizeof chunks / sizeof chunks[0], two);
    CHECK(memcmp(one, two, 32) == 0, "BLAKE3 chunked == one-shot (100000 bytes)");
  }

  ngs_test_sha512((const uint8_t *)"", 0, out);
  CHECK(hexeq(out, "cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce"
                   "47d0d13c5d85f2b0ff8318d2877eec2f63b931bd47417a81a538327af927da3e", 64),
        "KAT SHA-512 empty");
  ngs_test_sha512((const uint8_t *)"abc", 3, out);
  CHECK(hexeq(out, "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
                   "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f", 64),
        "KAT SHA-512 abc");

  CHECK(ngs_test_crc32c((const uint8_t *)"123456789", 9) == 0xE3069283u, "KAT CRC32C 123456789");
  CHECK(ngs_test_crc32c((const uint8_t *)"", 0) == 0, "KAT CRC32C empty");

  /* RFC 8032 TEST 1 */
  {
    uint8_t seed[32], pub[32], sig[64];
    unhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60", seed, 32);
    ngs_test_ed_keypair(seed, pub);
    CHECK(hexeq(pub, "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", 32),
          "KAT Ed25519 RFC8032 pub");
    ngs_test_ed_sign(seed, (const uint8_t *)"", 0, sig);
    CHECK(hexeq(sig, "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
                     "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b", 64),
          "KAT Ed25519 RFC8032 sig");
    CHECK(ngs_test_ed_verify(pub, (const uint8_t *)"", 0, sig) == 1, "Ed25519 verify good sig");
    sig[0] ^= 1;
    CHECK(ngs_test_ed_verify(pub, (const uint8_t *)"", 0, sig) == 0, "Ed25519 verify rejects flipped sig");
  }
  {
    uint8_t seed[32], pub[32], sig[64];
    const char *msg = "NouGenShards M1 round-trip message, long enough to hash twice over.";
    memset(seed, 0x42, sizeof seed);
    ngs_test_ed_keypair(seed, pub);
    ngs_test_ed_sign(seed, (const uint8_t *)msg, strlen(msg), sig);
    CHECK(ngs_test_ed_verify(pub, (const uint8_t *)msg, strlen(msg), sig) == 1, "Ed25519 round-trip");
    CHECK(ngs_test_ed_verify(pub, (const uint8_t *)"different", 9, sig) == 0, "Ed25519 wrong message rejected");
  }
}

static void test_basic_roundtrip(void) {
  ngs *db = NULL;
  ngs_open_opts oo = NGS_OPEN_OPTS_INIT;
  ngs_id id1, id2, id3;
  ngs_fact_in in;
  ngs_fact *f = NULL;
  uint8_t *ckpt = NULL;
  size_t cklen = 0;
  ngs_pubkey pub, pub2;

  fresh_dir();
  oo.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  CHECK(ngs_open(g_dir, &oo, &db) == NGS_OK && db != NULL, "open create");
  CHECK(ngs_libversion_number() == NGS_VERSION_NUMBER, "libversion number");
  CHECK(ngs_libversion() != NULL, "libversion string");
  CHECK(ngs_node_pubkey(db, &pub) == NGS_OK, "node pubkey");

  in = mk_input("alpha", "first fact", "hello world");
  CHECK(ngs_remember(db, &in, 0, &id1) == NGS_OK, "remember 1");
  in = mk_input("alpha", "second fact", "chain me");
  CHECK(ngs_remember(db, &in, 0, &id2) == NGS_OK, "remember 2");
  in = mk_input("beta", "other ns", "separate sequence");
  CHECK(ngs_remember(db, &in, 0, &id3) == NGS_OK, "remember 3 (other ns)");
  CHECK(memcmp(id1.b, id2.b, 32) != 0 && memcmp(id1.b, id3.b, 32) != 0, "ids distinct");

  CHECK(ngs_get(db, &id1, &f) == NGS_OK && f != NULL, "get 1");
  if (f) {
    static const uint8_t zero32[32] = {0};
    CHECK(f->seq == 1, "seq starts at 1");
    CHECK(f->title.n == strlen("first fact") && memcmp(f->title.p, "first fact", f->title.n) == 0, "title round-trip");
    CHECK(f->body.n == strlen("hello world") && memcmp(f->body.p, "hello world", f->body.n) == 0, "body round-trip");
    CHECK(f->kind == NGS_SEMANTIC, "kind round-trip");
    CHECK(memcmp(f->writer.b, pub.b, 32) == 0, "writer is the node key");
    CHECK(f->valid_to == NGS_TIME_MAX, "valid_to open");
    CHECK(memcmp(f->superseded_by.b, zero32, 32) == 0, "not superseded");
    CHECK(f->t_event != NGS_TIME_NOW && f->t_record >= f->t_event, "engine clock resolved");
    ngs_free(f); f = NULL;
  }
  CHECK(ngs_get(db, &id2, &f) == NGS_OK && f != NULL, "get 2");
  if (f) {
    CHECK(f->seq == 2, "seq increments within the namespace");
    ngs_free(f); f = NULL;
  }
  CHECK(ngs_get(db, &id3, &f) == NGS_OK && f != NULL, "get 3");
  if (f) {
    CHECK(f->seq == 1, "per-namespace sequence");
    ngs_free(f); f = NULL;
  }
  {
    ngs_id bogus;
    memset(bogus.b, 0xEE, 32);
    CHECK(ngs_get(db, &bogus, &f) == NGS_NOTFOUND && f == NULL, "get missing -> NOTFOUND");
  }
  CHECK(ngs_verify(db, NULL, 0) == NGS_OK, "verify clean log (chain + signatures)");
  CHECK(ngs_checkpoint(db, &ckpt, &cklen) == NGS_OK && ckpt != NULL && cklen > 0, "checkpoint produced");
  CHECK(ngs_verify(db, ckpt, cklen) == NGS_OK, "verify with checkpoint");
  ngs_free(ckpt);
  CHECK(ngs_close(db) == NGS_OK, "close");

  /* persistence across reopen, same node key */
  db = NULL;
  CHECK(ngs_open(g_dir, NULL, &db) == NGS_OK && db != NULL, "reopen");
  CHECK(ngs_node_pubkey(db, &pub2) == NGS_OK && memcmp(pub.b, pub2.b, 32) == 0, "node key persists");
  CHECK(ngs_get(db, &id2, &f) == NGS_OK && f != NULL && f->seq == 2, "fact survives reopen");
  if (f) { ngs_free(f); f = NULL; }
  CHECK(ngs_verify(db, NULL, 0) == NGS_OK, "verify after reopen");
  CHECK(ngs_close(db) == NGS_OK, "close 2");
  wipe_dir();
}

static void test_scan(void) {
  ngs *db = NULL;
  ngs_open_opts oo = NGS_OPEN_OPTS_INIT;
  ngs_id ids[5];
  int i;
  ngs_scan_opts so = NGS_SCAN_OPTS_INIT;
  ngs_iter *it = NULL;
  ngs_fact *f = NULL;
  int count = 0;
  uint64_t last_seq = 0;
  int ordered = 1;
  ngs_pubkey pub;

  fresh_dir();
  oo.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  CHECK(ngs_open(g_dir, &oo, &db) == NGS_OK, "scan: open");
  CHECK(ngs_node_pubkey(db, &pub) == NGS_OK, "scan: pubkey");
  for (i = 0; i < 5; i++) {
    char body[32];
    ngs_fact_in in;
    ngs_str tag = S("marker");
    snprintf(body, sizeof body, "fact number %d", i);
    in = mk_input(i % 2 ? "odd" : "even", "t", body);
    if (i == 2) { in.tags = &tag; in.n_tags = 1; }
    CHECK(ngs_remember(db, &in, 0, &ids[i]) == NGS_OK, "scan: remember");
  }

  /* tags ride along on the fact */
  CHECK(ngs_get(db, &ids[2], &f) == NGS_OK && f != NULL, "scan: get tagged");
  if (f) {
    CHECK(f->n_tags == 1 && f->tags[0].n == 6 && memcmp(f->tags[0].p, "marker", 6) == 0, "tag round-trip");
    ngs_free(f); f = NULL;
  }

  /* full scan: all facts, then NOTFOUND at the end */
  CHECK(ngs_scan(db, NULL, &it) == NGS_OK && it != NULL, "scan open");
  while (ngs_iter_next(it, &f) == NGS_OK) { count++; ngs_free(f); f = NULL; }
  CHECK(count == 5, "scan returns all 5");
  CHECK(ngs_iter_next(it, &f) == NGS_NOTFOUND && f == NULL, "scan ends with NOTFOUND");
  ngs_iter_close(it); it = NULL;

  /* namespace filter + ascending seq within the namespace */
  so.ns = S("even");
  count = 0; last_seq = 0; ordered = 1;
  CHECK(ngs_scan(db, &so, &it) == NGS_OK, "scan ns open");
  while (ngs_iter_next(it, &f) == NGS_OK) {
    count++;
    if (f->seq <= last_seq) ordered = 0;
    last_seq = f->seq;
    ngs_free(f); f = NULL;
  }
  ngs_iter_close(it); it = NULL;
  CHECK(count == 3 && ordered, "scan ns filter, seq ascending");

  /* writer filter: the node itself matches, a stranger does not */
  {
    ngs_scan_opts wo = NGS_SCAN_OPTS_INIT;
    ngs_pubkey stranger;
    wo.writer = &pub;
    count = 0;
    CHECK(ngs_scan(db, &wo, &it) == NGS_OK, "scan writer open");
    while (ngs_iter_next(it, &f) == NGS_OK) { count++; ngs_free(f); f = NULL; }
    ngs_iter_close(it); it = NULL;
    CHECK(count == 5, "scan writer = node finds all");
    memset(stranger.b, 0x77, 32);
    wo.writer = &stranger;
    count = 0;
    CHECK(ngs_scan(db, &wo, &it) == NGS_OK, "scan stranger open");
    while (ngs_iter_next(it, &f) == NGS_OK) { count++; ngs_free(f); f = NULL; }
    ngs_iter_close(it); it = NULL;
    CHECK(count == 0, "scan writer = stranger finds none");
  }

  /* since filter (t_record window): a far-future bound returns nothing */
  {
    ngs_scan_opts fo = NGS_SCAN_OPTS_INIT;
    fo.since = (ngs_time)4000000000000000LL; /* year 2096 in micros */
    count = 0;
    CHECK(ngs_scan(db, &fo, &it) == NGS_OK, "scan since open");
    while (ngs_iter_next(it, &f) == NGS_OK) { count++; ngs_free(f); f = NULL; }
    ngs_iter_close(it); it = NULL;
    CHECK(count == 0, "scan since future -> empty");
  }
  CHECK(ngs_close(db) == NGS_OK, "scan: close");
  wipe_dir();
}

static void test_misuse_and_validation(void) {
  ngs *db = NULL;
  ngs_open_opts oo = NGS_OPEN_OPTS_INIT;
  ngs_id id;
  ngs_fact_in in;

  fresh_dir();
  oo.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  CHECK(ngs_open(g_dir, &oo, &db) == NGS_OK, "misuse: open");

  /* the whole post-M1 surface returns NGS_MISUSE */
  {
    ngs_query q = NGS_QUERY_INIT;
    ngs_results *res = (ngs_results *)(void *)0x1;
    ngs_stats_t st = NGS_STATS_INIT;
    uint8_t *seg = NULL; size_t seglen = 0;
    ngs_head *heads = NULL; size_t nh = 0;
    ngs_sync_report *rep = (ngs_sync_report *)(void *)0x1;
    ngs_id other;
    memset(other.b, 1, 32);
    CHECK(ngs_recall(db, &q, &res) == NGS_MISUSE && res == NULL, "recall -> MISUSE");
    CHECK(ngs_as_of(db, 0, 0, &q, &res) == NGS_MISUSE && res == NULL, "as_of -> MISUSE");
    CHECK(ngs_invalidate(db, &other, S("x")) == NGS_MISUSE, "invalidate -> MISUSE");
    CHECK(ngs_link(db, &other, &other, S("r"), 1.0f, &id) == NGS_MISUSE, "link -> MISUSE");
    CHECK(ngs_redact(db, &other, S("x")) == NGS_MISUSE, "redact -> MISUSE");
    CHECK(ngs_grant(db, S("n"), NULL, &id) == NGS_MISUSE, "grant -> MISUSE");
    CHECK(ngs_mark(db, &other, 1) == NGS_MISUSE, "mark -> MISUSE");
    CHECK(ngs_rebuild(db) == NGS_MISUSE, "rebuild -> MISUSE");
    CHECK(ngs_heads(db, &heads, &nh) == NGS_MISUSE, "heads -> MISUSE");
    CHECK(ngs_sync_export(db, NULL, 0, &seg, &seglen) == NGS_MISUSE, "sync_export -> MISUSE");
    CHECK(ngs_sync_import(db, (const uint8_t *)"x", 1, &rep) == NGS_MISUSE && rep == NULL, "sync_import -> MISUSE");
    CHECK(ngs_stats(db, &st) == NGS_OK && st.size == sizeof st, "stats -> OK (M1 counters)");
    CHECK(ngs_stats(db, NULL) == NGS_MISUSE, "stats NULL -> MISUSE");
    st.size = 1;
    CHECK(ngs_stats(db, &st) == NGS_MISUSE, "stats short size -> MISUSE");
  }

  /* validation */
  in = mk_input("", "t", "b");
  CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE, "empty ns -> MISUSE");
  in = mk_input("n", "t", "b");
  in.kind = 99;
  CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE, "bad kind -> MISUSE");
  in = mk_input("n", "t", "b");
  in.supersedes = &id;   /* invalidation is M3 */
  CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE, "supersedes -> MISUSE in M1");
  in = mk_input("n", "t", "b");
  {
    float vals[2] = {0.25f, 0.75f};
    volatile float z = 0.0f;
    ngs_vec v;
    v.model_id = S("test-model");
    v.dim = 2;
    v.version = 1;
    v.v = vals;
    in.vecs = &v; in.n_vecs = 1;
    CHECK(ngs_remember(db, &in, 0, &id) == NGS_OK, "finite vector accepted (validated, not indexed in M1)");
    vals[1] = 1.0f / z; /* +Inf at runtime */
    CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE, "non-finite vector -> MISUSE");
  }
  in = mk_input("n", "t", "b");
  {
    static const uint8_t empty_map[1] = {0xA0};
    static const uint8_t bad_cbor[1] = {0xFF};
    ngs_fact *f = NULL;
    in.attrs_cbor = empty_map; in.attrs_len = 1;
    CHECK(ngs_remember(db, &in, 0, &id) == NGS_OK, "attrs empty map accepted");
    CHECK(ngs_get(db, &id, &f) == NGS_OK && f && f->attrs_len == 1 && f->attrs_cbor[0] == 0xA0,
          "attrs round-trip");
    if (f) { ngs_free(f); f = NULL; }
    in.attrs_cbor = bad_cbor; in.attrs_len = 1;
    CHECK(ngs_remember(db, &in, 0, &id) == NGS_MISUSE, "non-canonical attrs -> MISUSE");
  }
  CHECK(ngs_remember(NULL, &in, 0, &id) == NGS_MISUSE, "NULL db -> MISUSE");
  CHECK(ngs_remember(db, NULL, 0, &id) == NGS_MISUSE, "NULL input -> MISUSE");

  /* remember_many: one bad apple fails the batch atomically */
  {
    ngs_fact_in arr[2];
    ngs_id out[2];
    ngs_fact *f = NULL;
    arr[0] = mk_input("batch", "a", "one");
    arr[1] = mk_input("batch", "b", "two");
    arr[1].kind = 42;
    CHECK(ngs_remember_many(db, arr, 2, 0, out) == NGS_MISUSE, "batch with bad kind fails");
    arr[1].kind = NGS_EPISODIC;
    CHECK(ngs_remember_many(db, arr, 2, 0, out) == NGS_OK, "clean batch ok");
    CHECK(ngs_get(db, &out[1], &f) == NGS_OK && f && f->seq == 2, "batch seqs assigned in order");
    if (f) { ngs_free(f); f = NULL; }
    /* the failed batch left nothing behind: "batch" holds exactly 2 */
    {
      ngs_scan_opts so = NGS_SCAN_OPTS_INIT;
      ngs_iter *it = NULL;
      int count = 0;
      so.ns = S("batch");
      CHECK(ngs_scan(db, &so, &it) == NGS_OK, "batch scan open");
      while (ngs_iter_next(it, &f) == NGS_OK) { count++; ngs_free(f); f = NULL; }
      ngs_iter_close(it);
      CHECK(count == 2, "failed batch was atomic");
    }
  }
  CHECK(ngs_close(db) == NGS_OK, "misuse: close");
  wipe_dir();
}

static void test_writer_lock_and_readonly(void) {
  ngs *a = NULL, *b = NULL;
  ngs_open_opts oo = NGS_OPEN_OPTS_INIT;
  ngs_id id;
  ngs_fact_in in = mk_input("n", "t", "body");
  int rc;

  fresh_dir();
  oo.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  CHECK(ngs_open(g_dir, &oo, &a) == NGS_OK, "lock: first writer opens");
  /* header contract: a failed open still returns a handle (error state) */
  rc = ngs_open(g_dir, &oo, &b);
  CHECK(rc == NGS_BUSY && b != NULL, "lock: second writer -> BUSY + error-state handle");
  if (b) {
    CHECK(ngs_remember(b, &in, 0, &id) == NGS_BUSY, "lock: error-state handle stays BUSY");
    CHECK(ngs_errmsg(b) != NULL, "lock: errmsg explains");
    CHECK(ngs_close(b) == NGS_OK, "lock: error-state handle closes");
    b = NULL;
  }
  CHECK(ngs_close(a) == NGS_OK, "lock: close first");
  CHECK(ngs_open(g_dir, &oo, &b) == NGS_OK && b != NULL, "lock: opens after release");
  CHECK(ngs_remember(b, &in, 0, &id) == NGS_OK, "lock: write");
  CHECK(ngs_close(b) == NGS_OK, "lock: close second");

  /* read-only open: reads fine, writes refused */
  {
    ngs_open_opts ro = NGS_OPEN_OPTS_INIT;
    ngs_fact *f = NULL;
    ro.flags = NGS_OPEN_READONLY;
    CHECK(ngs_open(g_dir, &ro, &b) == NGS_OK && b != NULL, "readonly: open");
    CHECK(ngs_get(b, &id, &f) == NGS_OK && f != NULL, "readonly: get works");
    if (f) { ngs_free(f); f = NULL; }
    CHECK(ngs_remember(b, &in, 0, &id) == NGS_ERROR, "readonly: remember -> ERROR");
    CHECK(ngs_verify(b, NULL, 0) == NGS_OK, "readonly: verify works");
    CHECK(ngs_close(b) == NGS_OK, "readonly: close");
    b = NULL;
  }
  /* nonexistent dir without CREATE: error-state handle per the contract */
  {
    char missing[300];
    snprintf(missing, sizeof missing, "%s/nope", g_dir);
    rc = ngs_open(missing, NULL, &b);
    CHECK(rc == NGS_ERROR && b != NULL, "open missing dir without CREATE -> ERROR + handle");
    if (b) { ngs_close(b); b = NULL; }
  }
  wipe_dir();
}

static void test_checkpoint_mismatch(void) {
  ngs *db = NULL;
  ngs_open_opts oo = NGS_OPEN_OPTS_INIT;
  ngs_id id;
  ngs_fact_in in = mk_input("n", "t", "one");
  uint8_t *ckpt = NULL;
  size_t len = 0;

  fresh_dir();
  oo.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  CHECK(ngs_open(g_dir, &oo, &db) == NGS_OK, "ckpt: open");
  CHECK(ngs_remember(db, &in, 0, &id) == NGS_OK, "ckpt: remember 1");
  CHECK(ngs_checkpoint(db, &ckpt, &len) == NGS_OK, "ckpt: take checkpoint");
  in = mk_input("n", "t", "two");
  CHECK(ngs_remember(db, &in, 0, &id) == NGS_OK, "ckpt: remember 2");
  CHECK(ngs_verify(db, ckpt, len) == NGS_CORRUPT, "stale checkpoint -> CORRUPT");
  ngs_free(ckpt); ckpt = NULL;
  CHECK(ngs_checkpoint(db, &ckpt, &len) == NGS_OK, "ckpt: fresh checkpoint");
  ckpt[len - 1] ^= 0x40;
  CHECK(ngs_verify(db, ckpt, len) == NGS_CORRUPT, "tampered checkpoint -> CORRUPT");
  ngs_free(ckpt);
  CHECK(ngs_close(db) == NGS_OK, "ckpt: close");
  wipe_dir();
}

/* Group commit: 8 threads of durable singles on 2 shared namespaces, then a
** batch that straddles a segment rollover. Everything must land gapless,
** chained and signed, and survive reopen. segment_bytes = 1 MiB forces
** several rollovers while writers are in flight. */
#define GC_THREADS 8
#define GC_PER 300
#define GC_BATCH 500
typedef struct { ngs *db; int tid; int fails; } gc_arg;
static char gc_body[1200];
static void *gc_writer(void *vp) {
  gc_arg *a = (gc_arg *)vp;
  int i;
  for (i = 0; i < GC_PER; i++) {
    char title[64];
    ngs_fact_in in;
    ngs_id id;
    snprintf(title, sizeof title, "t%d-%d", a->tid, i);
    in = mk_input((a->tid & 1) ? "gc-a" : "gc-b", title, gc_body);
    if (ngs_remember(a->db, &in, 0, &id) != NGS_OK) a->fails++;
  }
  return NULL;
}
static void test_group_commit(void) {
  ngs *db = NULL;
  ngs_open_opts oo = NGS_OPEN_OPTS_INIT;
  pthread_t th[GC_THREADS];
  gc_arg args[GC_THREADS];
  ngs_stats_t st = NGS_STATS_INIT;
  static ngs_fact_in batch[GC_BATCH];
  static ngs_id ids[GC_BATCH];
  static char bbody[2048];
  int k, fails = 0;
  uint8_t *ckpt = NULL;
  size_t cklen = 0;
  char seg3[400];
  struct stat sb;
  memset(gc_body, 'g', sizeof gc_body - 1);
  memset(bbody, 'b', sizeof bbody - 1);
  fresh_dir();
  oo.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  oo.segment_bytes = 1024 * 1024;
  CHECK(ngs_open(g_dir, &oo, &db) == NGS_OK, "gc: open (1 MiB segments)");
  for (k = 0; k < GC_THREADS; k++) {
    args[k].db = db; args[k].tid = k; args[k].fails = 0;
    pthread_create(&th[k], NULL, gc_writer, &args[k]);
  }
  for (k = 0; k < GC_THREADS; k++) { pthread_join(th[k], NULL); fails += args[k].fails; }
  CHECK(fails == 0, "gc: 8 concurrent durable writers, 0 failures");
  for (k = 0; k < GC_BATCH; k++) batch[k] = mk_input("gc-a", "batch", bbody);
  CHECK(ngs_remember_many(db, batch, GC_BATCH, 0, ids) == NGS_OK, "gc: 500-fact batch across a rollover");
  CHECK(ngs_stats(db, &st) == NGS_OK && st.facts == GC_THREADS * GC_PER + GC_BATCH, "gc: every fact indexed");
  CHECK(ngs_verify(db, NULL, 0) == NGS_OK, "gc: verify chain + signatures");
  CHECK(ngs_checkpoint(db, &ckpt, &cklen) == NGS_OK, "gc: checkpoint");
  CHECK(ngs_flush(db) == NGS_OK, "gc: flush");
  CHECK(ngs_close(db) == NGS_OK, "gc: close");
  snprintf(seg3, sizeof seg3, "%s/log/000003.seg", g_dir);
  CHECK(stat(seg3, &sb) == 0, "gc: rolled over at least twice");
  db = NULL;
  CHECK(ngs_open(g_dir, NULL, &db) == NGS_OK, "gc: reopen");
  st.facts = 0;
  CHECK(ngs_stats(db, &st) == NGS_OK && st.facts == GC_THREADS * GC_PER + GC_BATCH, "gc: every fact survives reopen");
  CHECK(ngs_verify(db, ckpt, cklen) == NGS_OK, "gc: verify against checkpoint after reopen");
  {
    ngs_fact *f = NULL;
    CHECK(ngs_get(db, &ids[GC_BATCH - 1], &f) == NGS_OK && f != NULL, "gc: last batch fact readable");
    ngs_free(f);
  }
  CHECK(ngs_close(db) == NGS_OK, "gc: close 2");
  ngs_free(ckpt);
  wipe_dir();
}

int main(void) {
  test_kats();
  test_basic_roundtrip();
  test_scan();
  test_misuse_and_validation();
  test_writer_lock_and_readonly();
  test_checkpoint_mismatch();
  test_group_commit();
  printf("TESTS: %d passed, %d failed\n", g_pass, g_fail);
  return g_fail == 0 ? 0 : 1;
}
