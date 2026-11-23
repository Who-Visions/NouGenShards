/* SPDX-License-Identifier: Apache-2.0 */
/*
** test_main.c -- NGS M1 test suite. Tests internals and crash safety only; black-box contract tests
** belong to the conformance harness and are deliberately not duplicated here.
**
**   known answers   CRC32C, BLAKE3, Ed25519 (RFC 8032), canonical CBOR, UTF-8
**   codec           record and segment-header round trips; every flipped bit is detected
**   api             remember / remember_many / get / scan / flush / verify, limits, M1 stubs
**   crash           a fault at EVERY state-changing call: crash before, crash after, partial write,
**                   power loss with random un-synced sector survival, and one-shot I/O failures
**   torture         every byte of every segment flipped; detection by CRC, chain or signature
**   real fs         the same API on the real filesystem; single-writer lock; threads
**   abi             sizeof and offsetof of every public struct
*/
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <process.h>
#else
#include <pthread.h>
#endif

#include "ngs_int.h"
#include "simfs.h"
#include "../third_party/blake3/blake3.h"
#include "../third_party/ed25519/ed25519.h"

/* ------------------------------------------------------------ framework */
static unsigned long g_checks, g_fail;
static const char *g_name = "";

#define CHECK(c) do { g_checks++; if (!(c)) { g_fail++; printf("FAIL %s:%d [%s] %s\n", __FILE__, __LINE__, g_name, #c); } } while (0)
#define CHECKF(c, ...) do { g_checks++; if (!(c)) { g_fail++; printf("FAIL %s:%d [%s] %s -- ", __FILE__, __LINE__, g_name, #c); printf(__VA_ARGS__); printf("\n"); } } while (0)

static void hexs(const uint8_t *p, size_t n, char *out) {
  static const char d[] = "0123456789abcdef";
  size_t i;
  for (i = 0; i < n; i++) { out[2 * i] = d[p[i] >> 4]; out[2 * i + 1] = d[p[i] & 15]; }
  out[2 * n] = 0;
}

static int unhex(const char *h, uint8_t *out, size_t cap) {
  size_t n = strlen(h) / 2, i;
  if (n > cap) return -1;
  for (i = 0; i < n; i++) {
    unsigned v;
    if (sscanf(h + 2 * i, "%2x", &v) != 1) return -1;
    out[i] = (uint8_t)v;
  }
  return (int)n;
}

static ngs_str S(const char *s) { ngs_str x; x.p = s; x.n = strlen(s); return x; }

static uint8_t G_SK[64], G_PK[32], G_SK2[64], G_PK2[32];

static void key_from_tag(uint8_t sk[64], uint8_t pk[32], uint8_t tag) {
  uint8_t seed[32];
  memset(seed, tag, 32);
  ngs__keypair(pk, sk, seed);
}

/* ============================================================ known answers */
static void test_crc_blake_ed(void) {
  static const uint8_t m[] = "123456789";
  char hx[130];
  uint8_t out[32];
  blake3_hasher h;
  size_t k;
  g_name = "known-answers";
  CHECK(ngs__crc32c(0, m, 9) == 0xE3069283u);
  CHECK(ngs__crc32c(ngs__crc32c(0, m, 4), m + 4, 5) == 0xE3069283u);       /* chaining */
  CHECK(ngs__crc32c(0, "", 0) == 0u);

  /* BLAKE3 official vectors: input byte i is (i % 251) */
  {
    static const char *want[] = {
      "af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9adc112b7cc9a93cae41f3262",
      "2d3adedff11b61f14c886e35afa036736dcd87a74d27b5c1510225d0f592e213",
      "7b7015bb92cf0b318037702a6cdd81dee41224f734684c2c122cd6359cb1ee63",
      "e1be4d7a8ab5560aa4199eea339849ba8e293d55ca0a81006726d184519e647f" };
    uint8_t in[8];
    for (k = 0; k < 8; k++) in[k] = (uint8_t)(k % 251);
    for (k = 0; k < 4; k++) { ngs__blake3(in, k, out); hexs(out, 32, hx); CHECKF(strcmp(hx, want[k]) == 0, "len %u got %s", (unsigned)k, hx); }
  }
  /* one-shot equals chunked across the 1024-byte chunk boundary */
  {
    static uint8_t big[5000];
    uint8_t a[32], b[32];
    size_t lens[] = { 63, 64, 65, 1023, 1024, 1025, 2048, 5000 }, li;
    for (k = 0; k < sizeof big; k++) big[k] = (uint8_t)(k * 7 + 3);
    for (li = 0; li < sizeof lens / sizeof lens[0]; li++) {
      size_t n = lens[li], pos = 0;
      ngs__blake3(big, n, a);
      blake3_hasher_init(&h);
      while (pos < n) { size_t step = 37 < n - pos ? 37 : n - pos; blake3_hasher_update(&h, big + pos, step); pos += step; }
      blake3_hasher_finalize(&h, b, 32);
      CHECKF(memcmp(a, b, 32) == 0, "chunked hash differs at len %u", (unsigned)n);
    }
  }
  /* Ed25519, RFC 8032 section 7.1 tests 1 and 2 */
  {
    struct { const char *seed, *pk, *msg, *sig; } v[2] = {
      { "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b" },
      { "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00" } };
    for (k = 0; k < 2; k++) {
      uint8_t seed[32], pk[32], sk[64], sig[64], msg[4], want_sig[64], want_pk[32], pk2[32];
      int ml = unhex(v[k].msg, msg, sizeof msg);
      unhex(v[k].seed, seed, 32); unhex(v[k].pk, want_pk, 32); unhex(v[k].sig, want_sig, 64);
      ngs__keypair(pk, sk, seed);
      CHECK(memcmp(pk, want_pk, 32) == 0);
      ngs__pub_from_sk(pk2, sk);
      CHECK(memcmp(pk2, want_pk, 32) == 0);
      ed25519_sign(sig, msg, (size_t)ml, pk, sk);
      CHECKF(memcmp(sig, want_sig, 64) == 0, "RFC 8032 test %u signature", (unsigned)(k + 1));
      CHECK(ed25519_verify(want_sig, msg, (size_t)ml, want_pk) == 1);
      want_sig[10] ^= 0x01;
      CHECK(ed25519_verify(want_sig, msg, (size_t)ml, want_pk) == 0);
    }
  }
  /* the 32-byte-message wrappers used by the log */
  {
    uint8_t id[32], sig[64];
    memset(id, 0x5A, 32);
    ngs__sign(sig, id, G_PK, G_SK);
    CHECK(ngs__verify_sig(sig, id, G_PK) == 1);
    id[0] ^= 1;
    CHECK(ngs__verify_sig(sig, id, G_PK) == 0);
    CHECK(ngs__verify_sig(sig, id, G_PK2) == 0);
  }
}

static void test_utf8(void) {
  static const struct { const char *s; size_t n; int ok; } c[] = {
    { "abc", 3, 1 }, { "", 0, 1 }, { "\xC3\xA9", 2, 1 }, { "\xE2\x82\xAC", 3, 1 }, { "\xF0\x9F\x98\x80", 4, 1 },
    { "\xC0\xAF", 2, 0 }, { "\xE0\x80\xAF", 3, 0 }, { "\xED\xA0\x80", 3, 0 }, { "\xF4\x90\x80\x80", 4, 0 },
    { "\xF8\x88\x80\x80\x80", 5, 0 }, { "\xC3", 1, 0 }, { "\x80", 1, 0 }, { "\xE2\x82", 2, 0 }, { "\xF0\x9F\x98", 3, 0 } };
  size_t i;
  g_name = "utf8";
  for (i = 0; i < sizeof c / sizeof c[0]; i++) CHECKF(ngs__utf8_ok((const uint8_t *)c[i].s, c[i].n) == c[i].ok, "case %u", (unsigned)i);
}

/* ============================================================ canonical CBOR */
static void test_cbor(void) {
  static const struct { int64_t v; const char *hex; } ints[] = {
    { 0, "00" }, { 23, "17" }, { 24, "1818" }, { 255, "18ff" }, { 256, "190100" }, { 65535, "19ffff" },
    { 65536, "1a00010000" }, { 4294967295ll, "1affffffff" }, { 4294967296ll, "1b0000000100000000" },
    { INT64_MAX, "1b7fffffffffffffff" }, { -1, "20" }, { -24, "37" }, { -25, "3818" }, { -256, "38ff" },
    { -257, "390100" }, { INT64_MIN, "3b7fffffffffffffff" } };
  size_t i;
  ngs_buf b = { NULL, 0, 0 };
  char hx[64];
  g_name = "cbor";
  for (i = 0; i < sizeof ints / sizeof ints[0]; i++) {
    ngs_cur c;
    int64_t back = 0;
    b.n = 0;
    CHECK(ngs__cbor_int(&b, ints[i].v) == 0);
    hexs(b.p, b.n, hx);
    CHECKF(strcmp(hx, ints[i].hex) == 0, "encode %lld -> %s want %s", (long long)ints[i].v, hx, ints[i].hex);
    c.p = b.p; c.n = b.n; c.i = 0; c.bad = 0;
    CHECK(ngs__cur_int(&c, &back) == 0 && back == ints[i].v && c.i == c.n);
  }
  b.n = 0; ngs__cbor_bytes(&b, "", 0); hexs(b.p, b.n, hx); CHECK(strcmp(hx, "40") == 0);
  b.n = 0; ngs__cbor_text(&b, "a", 1); hexs(b.p, b.n, hx); CHECK(strcmp(hx, "6161") == 0);
  ngs__buf_free(&b);
  /* the decoder accepts only shortest form, definite lengths, the right major type */
  {
    static const char *bad[] = { "1800", "1817", "190000", "1900ff", "1a0000ffff", "1b00000000ffffffff", "5f", "1c", "1f", "19ff", "" };
    uint8_t raw[16];
    for (i = 0; i < sizeof bad / sizeof bad[0]; i++) {
      ngs_cur c;
      uint64_t v;
      int n = unhex(bad[i], raw, sizeof raw);
      c.p = raw; c.n = (size_t)n; c.i = 0; c.bad = 0;
      CHECKF(ngs__cur_uint(&c, &v) != 0, "decoder accepted %s", bad[i]);
    }
    {
      ngs_cur c; uint64_t v; uint8_t raw2[2] = { 0x20, 0 };
      c.p = raw2; c.n = 1; c.i = 0; c.bad = 0;
      CHECK(ngs__cur_uint(&c, &v) != 0);                                   /* negative where unsigned is required */
    }
  }
  /* attrs validation: one well-formed item, definite lengths, bounded depth */
  {
    static const struct { const char *hex; int ok; } w[] = {
      { "a0", 1 }, { "a1616b01", 1 }, { "a1616b", 0 }, { "a1616b0100", 0 }, { "bf616b01ff", 0 },
      { "a26161a0616281", 0 }, { "a1616c8301020304", 0 }, { "c100", 1 }, { "f4", 1 }, { "", 0 }, { "ff", 0 }, { "1f", 0 } };
    uint8_t raw[32];
    char deep[200];
    size_t k;
    for (i = 0; i < sizeof w / sizeof w[0]; i++) {
      int n = unhex(w[i].hex, raw, sizeof raw);
      CHECKF((ngs__cbor_wellformed(raw, (size_t)n) == 0) == w[i].ok, "wellformed %s", w[i].hex);
    }
    for (k = 0; k < 100; k++) deep[k] = (char)0x81;                         /* 100 nested arrays of one item */
    deep[100] = 0x00;
    CHECK(ngs__cbor_wellformed((const uint8_t *)deep, 101) != 0);           /* deeper than 32 is refused */
  }
}

/* ============================================================ record codec */
static void fill_rec(ngs_rec *r, ngs_buf *tags, const uint8_t *attrs, size_t alen) {
  static const ngs_str tg[2] = { { "alpha", 5 }, { "b\xC3\xA9ta", 5 } };
  memset(r, 0, sizeof *r);
  memcpy(r->writer, G_PK, 32);
  r->ns = (const uint8_t *)"ns/one"; r->ns_len = 6;
  r->kind = NGS_SEMANTIC; r->seq = 3;
  memset(r->prev, 0x11, 32);
  r->t_event = -1234; r->t_record = 1700000000123456ll; r->valid_from = 99;
  r->title = (const uint8_t *)"a title"; r->title_len = 7;
  r->body = (const uint8_t *)"body text \xE2\x82\xAC end"; r->body_len = 16;
  r->attrs = attrs; r->attrs_len = alen; r->schema = 7;
  ngs__encode_tags(tags, tg, 2);
  r->tags = tags->p; r->tags_len = tags->n; r->n_tags = 2;
}

static void test_record_and_header(void) {
  static const uint8_t attrs[] = { 0xa1, 0x61, 0x6b, 0x01 };
  ngs_buf tags = { NULL, 0, 0 }, pay = { NULL, 0, 0 };
  ngs_rec r, d;
  size_t i, detected = 0, flips = 0;
  int m;
  uint8_t *copy;
  g_name = "record-codec";
  fill_rec(&r, &tags, attrs, sizeof attrs);
  CHECK(ngs__rec_seal(&r, G_SK) == 0);
  CHECK(ngs__rec_encode(&pay, &r) == 0);
  CHECK(ngs__rec_decode(pay.p, pay.n, &d) == 0);
  CHECK(memcmp(d.id, r.id, 32) == 0 && memcmp(d.sig, r.sig, 64) == 0 && d.seq == 3 && d.kind == NGS_SEMANTIC);
  CHECK(d.t_event == -1234 && d.t_record == 1700000000123456ll && d.valid_from == 99 && d.schema == 7 && d.n_tags == 2);
  CHECK(d.ns_len == 6 && memcmp(d.ns, "ns/one", 6) == 0 && d.body_len == 16 && d.attrs_len == 4);
  CHECK(ngs__rec_check_id(&d) == 0 && ngs__rec_check_sig(&d) == 0);
  /* the id is reproducible: same fields, same id; any field change, different id */
  {
    ngs_rec r2 = r;
    ngs__rec_seal(&r2, G_SK);
    CHECK(memcmp(r2.id, r.id, 32) == 0 && memcmp(r2.sig, r.sig, 64) == 0);
    r2.seq = 4; ngs__rec_seal(&r2, G_SK);
    CHECK(memcmp(r2.id, r.id, 32) != 0);
  }
  /* flip every bit of the encoded record: it must fail to decode, or fail the id check, or fail the signature */
  copy = (uint8_t *)malloc(pay.n);
  for (i = 0; i < pay.n; i++) {
    for (m = 0; m < 8; m++) {
      ngs_rec x;
      memcpy(copy, pay.p, pay.n);
      copy[i] ^= (uint8_t)(1u << m);
      flips++;
      if (ngs__rec_decode(copy, pay.n, &x) != 0 || ngs__rec_check_id(&x) != 0 || ngs__rec_check_sig(&x) != 0) detected++;
    }
  }
  CHECKF(detected == flips, "%lu of %lu single-bit flips went undetected", (unsigned long)(flips - detected), (unsigned long)flips);
  printf("  record codec: %lu single-bit flips of a %lu-byte record, %lu detected\n", (unsigned long)flips, (unsigned long)pay.n, (unsigned long)detected);
  /* truncation and trailing bytes */
  for (i = 0; i < pay.n; i++) { ngs_rec x; CHECK(ngs__rec_decode(pay.p, i, &x) != 0); }
  { ngs_rec x; uint8_t *t2 = (uint8_t *)malloc(pay.n + 1); memcpy(t2, pay.p, pay.n); t2[pay.n] = 0; CHECK(ngs__rec_decode(t2, pay.n + 1, &x) != 0); free(t2); }
  free(copy);
  ngs__buf_free(&tags); ngs__buf_free(&pay);

  /* segment header */
  {
    uint8_t h[NGS_SEG_HDR], w[32], h2[NGS_SEG_HDR];
    uint64_t fo = 0;
    size_t k;
    int mm;
    ngs__seg_hdr_encode(h, 0x0102030405060708ull, G_PK);
    CHECK(ngs__seg_hdr_decode(h, &fo, w) == 0 && fo == 0x0102030405060708ull && memcmp(w, G_PK, 32) == 0);
    for (k = 0; k < NGS_SEG_HDR; k++) {
      for (mm = 0; mm < 8; mm++) {
        memcpy(h2, h, sizeof h);
        h2[k] ^= (uint8_t)(1u << mm);
        CHECKF(ngs__seg_hdr_decode(h2, &fo, w) != 0, "header bit %u.%d accepted", (unsigned)k, mm);
      }
    }
  }
  /* frame */
  {
    uint8_t fr[NGS_FRAME_OVERHEAD + 5];
    ngs__frame_encode(fr, NGS_REC_FACT | NGS_REC_PENDING, (const uint8_t *)"hello", 5);
    CHECK(fr[0] == 5 && fr[1] == 0 && fr[4] == 0x81);
    CHECK(ngs__crc32c(ngs__crc32c(0, &fr[4], 1), fr + 5, 5) == (uint32_t)(fr[10] | (fr[11] << 8) | (fr[12] << 16) | ((uint32_t)fr[13] << 24)));
  }
}

/* ============================================================ API on the simulated disk */
static int open_sim(sim *s, int create, const uint8_t *sk, uint64_t segbytes, int ro, ngs **db) {
  ngs_open_opts o = NGS_OPEN_OPTS_INIT;
  o.flags = ro ? NGS_OPEN_READONLY : (NGS_OPEN_READWRITE | (create ? NGS_OPEN_CREATE : 0));
  o.node_seckey = sk;
  o.segment_bytes = segbytes;
  return ngs__open_vfs("db", &o, sim_vfs(s), db);
}

static ngs_fact_in mkfact(const char *ns, const char *title, const char *body, int kind) {
  ngs_fact_in f = NGS_FACT_IN_INIT;
  f.ns = S(ns); f.kind = kind; f.title = S(title); f.body = S(body);
  return f;
}

static int same(const ngs_id *a, const ngs_id *b) { return memcmp(a->b, b->b, 32) == 0; }

static void test_api(void) {
  sim *s = sim_new(1);
  ngs *db = NULL, *db2 = NULL;
  ngs_id i1, i2, i3, many[3], zero;
  ngs_fact *f = NULL;
  ngs_fact_in a, b, c, arr[3];
  ngs_str tg[2];
  static const uint8_t attrs[] = { 0xa1, 0x61, 0x6b, 0x01 };
  ngs_pubkey pk;
  ngs_iter *it = NULL;
  ngs_scan_opts so = NGS_SCAN_OPTS_INIT;
  size_t count;
  int rc;
  g_name = "api";
  memset(&zero, 0, sizeof zero);
  CHECK(open_sim(s, 1, G_SK, 0, 0, &db) == 0);
  CHECK(ngs_node_pubkey(db, &pk) == 0 && memcmp(pk.b, G_PK, 32) == 0);
  CHECK(ngs_libversion_number() == NGS_VERSION_NUMBER && strcmp(ngs_libversion(), NGS_VERSION) == 0);
  CHECK(strcmp(ngs_errstr(NGS_OK), "ok") == 0 && ngs_errstr(NGS_CORRUPT)[0] && ngs_errstr(999)[0]);

  tg[0] = S("x"); tg[1] = S("y");
  a = mkfact("alpha", "t1", "hello", NGS_EPISODIC); a.tags = tg; a.n_tags = 2; a.attrs_cbor = attrs; a.attrs_len = sizeof attrs; a.schema = 3;
  CHECK(ngs_remember(db, &a, 0, &i1) == 0);
  b = mkfact("alpha", "t2", "second", NGS_SEMANTIC);
  CHECK(ngs_remember(db, &b, 0, &i2) == 0);
  c = mkfact("beta", "t3", "other ns", NGS_PROCEDURAL);
  CHECK(ngs_remember(db, &c, 0, &i3) == 0);
  CHECK(!same(&i1, &i2) && !same(&i2, &i3));

  CHECK(ngs_get(db, &i1, &f) == 0 && f);
  if (f) {
    CHECK(f->size == sizeof(ngs_fact) && ((uintptr_t)f % NGS_ALIGN_MAX) == 0);
    CHECK(same(&f->id, &i1) && f->kind == NGS_EPISODIC && f->seq == 1 && memcmp(f->writer.b, G_PK, 32) == 0);
    CHECK(f->ns.n == 5 && memcmp(f->ns.p, "alpha", 5) == 0 && f->title.n == 2 && f->body.n == 5 && memcmp(f->body.p, "hello", 5) == 0);
    CHECK(f->t_event == f->t_record && f->valid_from == f->t_event && f->valid_to == NGS_TIME_MAX);
    CHECK(memcmp(&f->superseded_by, &zero, 32) == 0 && f->redacted == 0 && f->schema == 3);
    CHECK(f->n_tags == 2 && f->tags[0].n == 1 && f->tags[0].p[0] == 'x' && f->tags[1].p[0] == 'y');
    CHECK(f->attrs_len == 4 && memcmp(f->attrs_cbor, attrs, 4) == 0);
    ngs_free(f); f = NULL;
  }
  CHECK(ngs_get(db, &i2, &f) == 0 && f && f->seq == 2 && f->n_tags == 0 && f->attrs_len == 0);
  { ngs_time t2 = f ? f->t_record : 0; ngs_free(f); f = NULL; CHECK(ngs_get(db, &i3, &f) == 0 && f && f->seq == 1 && f->t_record > t2); ngs_free(f); f = NULL; }
  { ngs_id nope; memset(&nope, 0xEE, sizeof nope); CHECK(ngs_get(db, &nope, &f) == NGS_NOTFOUND && f == NULL); }

  /* atomic batch */
  arr[0] = mkfact("alpha", "b1", "x", NGS_EPISODIC); arr[1] = mkfact("beta", "b2", "y", NGS_EPISODIC); arr[2] = mkfact("alpha", "b3", "z", NGS_EPISODIC);
  CHECK(ngs_remember_many(db, arr, 3, 0, many) == 0);
  CHECK(ngs_get(db, &many[2], &f) == 0 && f && f->seq == 4);                 /* alpha: t1, t2, b1, b3 -> seq 4 */
  ngs_free(f); f = NULL;
  /* a batch with one invalid fact writes nothing at all */
  arr[1] = mkfact("", "bad", "y", NGS_EPISODIC);
  rc = ngs_remember_many(db, arr, 3, 0, many);
  CHECK(rc == NGS_MISUSE);
  count = 0; CHECK(ngs_scan(db, NULL, &it) == 0); while (ngs_iter_next(it, &f) == 0) { count++; ngs_free(f); } ngs_iter_close(it);
  CHECK(count == 6);

  /* scan filters */
  so.ns = S("alpha"); CHECK(ngs_scan(db, &so, &it) == 0); count = 0;
  while (ngs_iter_next(it, &f) == 0) { count++; CHECK(f->ns.n == 5); ngs_free(f); } ngs_iter_close(it); CHECK(count == 4);
  so.ns = S("none"); CHECK(ngs_scan(db, &so, &it) == 0); CHECK(ngs_iter_next(it, &f) == NGS_NOTFOUND); ngs_iter_close(it);
  so = (ngs_scan_opts)NGS_SCAN_OPTS_INIT; so.writer = &(ngs_pubkey){ { 0 } };
  CHECK(ngs_scan(db, &so, &it) == 0); CHECK(ngs_iter_next(it, &f) == NGS_NOTFOUND); ngs_iter_close(it);
  memcpy(&pk, G_PK, 32); so.writer = &pk; CHECK(ngs_scan(db, &so, &it) == 0); count = 0;
  while (ngs_iter_next(it, &f) == 0) { count++; ngs_free(f); } ngs_iter_close(it); CHECK(count == 6);
  {
    ngs_time mid;
    CHECK(ngs_get(db, &i2, &f) == 0); mid = f->t_record; ngs_free(f); f = NULL;
    so = (ngs_scan_opts)NGS_SCAN_OPTS_INIT; so.since = mid; so.until = mid;
    CHECK(ngs_scan(db, &so, &it) == 0); count = 0; while (ngs_iter_next(it, &f) == 0) { count++; CHECK(f->t_record == mid); ngs_free(f); } ngs_iter_close(it);
    CHECK(count == 1);
  }

  /* NO_SYNC then flush; verify */
  { ngs_fact_in n1 = mkfact("alpha", "ns1", "nosync", NGS_EPISODIC); ngs_id id; CHECK(ngs_remember(db, &n1, NGS_WRITE_NO_SYNC, &id) == 0); CHECK(ngs_flush(db) == 0); }
  CHECK(ngs_verify(db, NULL, 0) == 0);

  /* every entry point M1 does not implement */
  {
    ngs_str nostr = { NULL, 0 };
    ngs_results *res = (ngs_results *)1; uint8_t *buf = (uint8_t *)1; size_t blen = 9; ngs_head *hd = (ngs_head *)1; ngs_sync_report *rep = (ngs_sync_report *)1;
    ngs_stats_t st = NGS_STATS_INIT; ngs_query q = NGS_QUERY_INIT; ngs_id idx;
#define NOT_M1(call) do { rc = (call); CHECK(rc == NGS_MISUSE); CHECK(strcmp(ngs_errmsg(db), "not in M1") == 0); } while (0)
    NOT_M1(ngs_invalidate(db, &i1, nostr));
    NOT_M1(ngs_link(db, &i1, &i2, nostr, 0.5f, &idx));
    NOT_M1(ngs_redact(db, &i1, nostr));
    NOT_M1(ngs_grant(db, S("alpha"), &pk, &idx));
    NOT_M1(ngs_recall(db, &q, &res)); CHECK(res == NULL);
    res = (ngs_results *)1;
    NOT_M1(ngs_as_of(db, NGS_TIME_NOW, NGS_TIME_NOW, &q, &res)); CHECK(res == NULL);
    NOT_M1(ngs_mark(db, &i1, NGS_MARK_USED));
    NOT_M1(ngs_checkpoint(db, &buf, &blen)); CHECK(buf == NULL && blen == 0);
    NOT_M1(ngs_rebuild(db));
    NOT_M1(ngs_heads(db, &hd, &blen)); CHECK(hd == NULL);
    NOT_M1(ngs_sync_export(db, NULL, 0, &buf, &blen));
    NOT_M1(ngs_sync_import(db, NULL, 0, &rep)); CHECK(rep == NULL);
    NOT_M1(ngs_stats(db, &st));
    CHECK(ngs_verify(db, (const uint8_t *)"x", 1) == NGS_MISUSE && strncmp(ngs_errmsg(db), "not in M1", 9) == 0);
  }

  /* input validation: every case is refused and writes nothing */
  {
    ngs_fact_in x;
    static char big[NGS_MAX_BODY + 1], ns256[257];
    ngs_str badtag[1] = { { NULL, 3 } };
    static const uint8_t badattrs[] = { 0xa1, 0x61 }, nonmap[] = { 0x01 };
    ngs_vec vec = { { "m", 1 }, 1, 1, NULL };
    ngs_id sup = { { 1 } };
    float nan = 0.0f;
    nan = nan / nan;
    memset(big, 'a', sizeof big); memset(ns256, 'n', sizeof ns256);
#define REFUSE(expect, setup) do { x = mkfact("alpha", "v", "b", NGS_EPISODIC); setup; rc = ngs_remember(db, &x, 0, NULL); CHECKF(rc == (expect), "%s -> rc %d", #setup, rc); } while (0)
    REFUSE(NGS_MISUSE, x.ns = S(""));
    REFUSE(NGS_MISUSE, x.ns.n = 256; x.ns.p = ns256);
    REFUSE(NGS_MISUSE, x.ns = S("a\xC0\xAF"));
    REFUSE(NGS_MISUSE, x.ns.n = 3; x.ns.p = "a\0b");
    REFUSE(NGS_MISUSE, x.kind = 0);
    REFUSE(NGS_MISUSE, x.kind = 4);
    REFUSE(NGS_TOOBIG, x.body.p = big; x.body.n = NGS_MAX_BODY + 1);
    REFUSE(NGS_MISUSE, x.body = S("bad \xFF byte"));
    REFUSE(NGS_TOOBIG, x.title.p = big; x.title.n = NGS_MAX_TITLE_LEN + 1);
    REFUSE(NGS_MISUSE, x.tags = badtag; x.n_tags = 1);
    REFUSE(NGS_MISUSE, x.tags = NULL; x.n_tags = 2);
    REFUSE(NGS_MISUSE, x.attrs_cbor = badattrs; x.attrs_len = sizeof badattrs);
    REFUSE(NGS_MISUSE, x.attrs_cbor = nonmap; x.attrs_len = sizeof nonmap);
    REFUSE(NGS_MISUSE, x.attrs_cbor = NULL; x.attrs_len = 4);
    REFUSE(NGS_TOOBIG, x.attrs_cbor = (const uint8_t *)big; x.attrs_len = NGS_MAX_ATTRS_LEN + 1);
    REFUSE(NGS_MISUSE, x.vecs = &vec; x.n_vecs = 1);
    REFUSE(NGS_MISUSE, x.supersedes = &sup);
    REFUSE(NGS_MISUSE, x.t_event = NGS_TIME_MAX);
    REFUSE(NGS_MISUSE, x.valid_from = NGS_TIME_MIN);
    REFUSE(NGS_MISUSE, x.salience0 = nan);
    REFUSE(NGS_MISUSE, x.size = 4);
    CHECK(ngs_remember(db, NULL, 0, NULL) == NGS_MISUSE);
    /* a body of exactly the limit is fine; a struct larger than this build knows is read up to sizeof */
    x = mkfact("alpha", "max", "m", NGS_EPISODIC); x.body.p = big; x.body.n = NGS_MAX_BODY;
    CHECK(ngs_remember(db, &x, 0, NULL) == 0);
    {
      union { ngs_fact_in f; uint8_t raw[sizeof(ngs_fact_in) + 64]; } u;
      memset(&u, 0xCC, sizeof u);
      u.f = mkfact("alpha", "bigstruct", "s", NGS_EPISODIC);
      u.f.size = (uint32_t)sizeof u;
      CHECK(ngs_remember(db, &u.f, 0, NULL) == 0);
    }
    count = 0; CHECK(ngs_scan(db, NULL, &it) == 0); while (ngs_iter_next(it, &f) == 0) { count++; ngs_free(f); } ngs_iter_close(it);
    CHECK(count == 9);                                                     /* 7 earlier + max + bigstruct; none of the refused ones */
  }
  CHECK(ngs_close(db) == 0);

  /* reopen: state, chain heads and time survive; read-only handles cannot write */
  CHECK(open_sim(s, 0, G_SK, 0, 0, &db) == 0);
  CHECK(ngs_get(db, &i1, &f) == 0 && f && f->seq == 1); ngs_free(f); f = NULL;
  { ngs_fact_in n1 = mkfact("alpha", "after reopen", "r", NGS_EPISODIC); ngs_id id; CHECK(ngs_remember(db, &n1, 0, &id) == 0); CHECK(ngs_get(db, &id, &f) == 0 && f && f->seq == 8); ngs_free(f); f = NULL; }
  CHECK(ngs_verify(db, NULL, 0) == 0);
  /* a second writer handle on the same directory is refused */
  rc = open_sim(s, 0, G_SK, 0, 0, &db2); CHECK(rc == NGS_BUSY && db2 && strlen(ngs_errmsg(db2)) > 0); CHECK(ngs_get(db2, &i1, &f) == NGS_MISUSE); ngs_close(db2); db2 = NULL;
  /* ... a read-only handle is fine alongside it */
  CHECK(open_sim(s, 0, NULL, 0, 1, &db2) == 0);
  CHECK(ngs_get(db2, &i1, &f) == 0); ngs_free(f); f = NULL;
  { ngs_fact_in n1 = mkfact("alpha", "ro", "r", NGS_EPISODIC); CHECK(ngs_remember(db2, &n1, 0, NULL) == NGS_MISUSE && strstr(ngs_errmsg(db2), "read-only") != NULL); }
  CHECK(ngs_node_pubkey(db2, &pk) == NGS_NOTFOUND);
  CHECK(ngs_close(db2) == 0);
  CHECK(ngs_close(db) == 0);
  /* wrong node key on an existing database */
  rc = open_sim(s, 0, G_SK2, 0, 0, &db2); CHECK(rc == NGS_NOGRANT); ngs_close(db2);

  /* open errors */
  {
    ngs_open_opts o = NGS_OPEN_OPTS_INIT;
    sim *e = sim_new(2);
    ngs *x = NULL;
    CHECK(open_sim(e, 0, G_SK, 0, 0, &x) == NGS_NOTFOUND); ngs_close(x);
    CHECK(open_sim(e, 0, NULL, 0, 1, &x) == NGS_NOTFOUND); ngs_close(x);
    o.flags = NGS_OPEN_READONLY | NGS_OPEN_READWRITE; CHECK(ngs__open_vfs("db", &o, sim_vfs(e), &x) == NGS_MISUSE); ngs_close(x);
    o.flags = NGS_OPEN_READONLY | NGS_OPEN_CREATE; CHECK(ngs__open_vfs("db", &o, sim_vfs(e), &x) == NGS_MISUSE); ngs_close(x);
    o.flags = NGS_OPEN_READWRITE; o.size = 2; CHECK(ngs__open_vfs("db", &o, sim_vfs(e), &x) == NGS_MISUSE); ngs_close(x);
    CHECK(ngs__open_vfs("", NULL, sim_vfs(e), &x) == NGS_MISUSE); ngs_close(x);
    CHECK(ngs_close(NULL) == 0);
    sim_free(e);
  }
  sim_free(s);
}

static void test_segments_and_keys(void) {
  sim *s = sim_new(3);
  ngs *db = NULL;
  ngs_id ids[40];
  ngs_fact *f = NULL;
  char title[16];
  int i;
  ngs_pubkey pk1, pk2;
  g_name = "segments-and-keys";
  /* rolling: a tiny segment size gives many segments; everything reads back and verifies */
  CHECK(open_sim(s, 1, G_SK, 1500, 0, &db) == 0);
  for (i = 0; i < 40; i++) {
    ngs_fact_in x;
    snprintf(title, sizeof title, "f%d", i);
    x = mkfact(i % 2 ? "odd" : "even", title, "some body text to make the record a few hundred bytes long, repeated: some body text", NGS_EPISODIC);
    CHECK(ngs_remember(db, &x, 0, &ids[i]) == 0);
  }
  CHECK(sim_count_names(s, "db/log") >= 10);
  for (i = 0; i < 40; i++) { CHECK(ngs_get(db, &ids[i], &f) == 0 && f && f->seq == (uint64_t)(i / 2 + 1)); ngs_free(f); f = NULL; }
  CHECK(ngs_verify(db, NULL, 0) == 0);
  ngs_close(db);
  sim_clean_shutdown(s);
  CHECK(open_sim(s, 0, G_SK, 1500, 0, &db) == 0);
  for (i = 0; i < 40; i++) { CHECK(ngs_get(db, &ids[i], &f) == 0); ngs_free(f); f = NULL; }
  CHECK(ngs_verify(db, NULL, 0) == 0);
  ngs_close(db);
  /* a batch never spans two segments: its frames stay together */
  {
    ngs_fact_in arr[5];
    ngs_id bid[5];
    CHECK(open_sim(s, 0, G_SK, 1500, 0, &db) == 0);
    for (i = 0; i < 5; i++) arr[i] = mkfact("batch", "bt", "body body body body body body body body body body body body body body body body body body", NGS_EPISODIC);
    CHECK(ngs_remember_many(db, arr, 5, 0, bid) == 0);
    CHECK(ngs_verify(db, NULL, 0) == 0);
    ngs_close(db);
    sim_clean_shutdown(s);
    CHECK(open_sim(s, 0, G_SK, 1500, 0, &db) == 0);
    for (i = 0; i < 5; i++) { CHECK(ngs_get(db, &bid[i], &f) == 0); ngs_free(f); f = NULL; }
    ngs_close(db);
  }
  sim_free(s);

  /* node key: NGS_OPEN_CREATE generates one, persists it, and reopening finds the same key */
  s = sim_new(4);
  {
    ngs_open_opts o = NGS_OPEN_OPTS_INIT;
    o.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
    CHECK(ngs__open_vfs("db", &o, sim_vfs(s), &db) == 0);
    CHECK(ngs_node_pubkey(db, &pk1) == 0);
    { ngs_fact_in x = mkfact("k", "t", "b", NGS_EPISODIC); ngs_id id; CHECK(ngs_remember(db, &x, 0, &id) == 0); }
    ngs_close(db);
    sim_clean_shutdown(s);
    o.flags = NGS_OPEN_READWRITE;
    CHECK(ngs__open_vfs("db", &o, sim_vfs(s), &db) == 0);
    CHECK(ngs_node_pubkey(db, &pk2) == 0 && memcmp(pk1.b, pk2.b, 32) == 0);
    CHECK(ngs_verify(db, NULL, 0) == 0);
    ngs_close(db);
  }
  sim_free(s);
}

/* ============================================================ crash and torture */
#define MAXF 64
typedef struct { int start, n, nosync, acked, flushed; } call_t;
static call_t g_calls[40];
static int g_ncalls, g_nf;
static ngs_id g_id[MAXF];
static int g_have_id[MAXF];
static char g_ns[MAXF][8], g_title[MAXF][16], g_body[MAXF][480];
static ngs_str g_tags[MAXF][2];
static uint8_t g_attrs[8] = { 0xa1, 0x61, 0x61, 0x18, 0x2a };       /* {"a": 42} */

static void fill_fact(int i, ngs_fact_in *f) {
  size_t blen = (size_t)((i * 53) % 400) + 1;
  static const char *nss[3] = { "a", "b", "c" };
  snprintf(g_ns[i], sizeof g_ns[i], "%s", i >= 60 ? "post" : nss[i % 3]);
  snprintf(g_title[i], sizeof g_title[i], "f%d", i);
  memset(g_body[i], 'a' + (i % 26), blen); g_body[i][blen] = 0;
  g_tags[i][0] = S("tagA"); g_tags[i][1] = S("t\xC3\xA9");
  *f = mkfact(g_ns[i], g_title[i], g_body[i], 1 + (i % 3));
  if (i % 2) { f->tags = g_tags[i]; f->n_tags = (i % 4 == 1) ? 1 : 2; }
  if (i % 5 == 0) { f->attrs_cbor = g_attrs; f->attrs_len = 5; }
  f->schema = (uint16_t)(i % 4);
}

static int g_continue;               /* 1: keep issuing calls after a failure (one-shot failure mode) */

static int do_call(ngs *db, int n, int nosync) {
  ngs_fact_in arr[8];
  ngs_id ids[8];
  call_t *c = &g_calls[g_ncalls++];
  int i, rc;
  c->start = g_nf; c->n = n; c->nosync = nosync; c->acked = 0; c->flushed = 0;
  for (i = 0; i < n; i++) fill_fact(g_nf + i, &arr[i]);
  g_nf += n;
  rc = (n == 1) ? ngs_remember(db, &arr[0], nosync ? NGS_WRITE_NO_SYNC : 0, &ids[0]) : ngs_remember_many(db, arr, (size_t)n, 0, ids);
  if (rc == NGS_OK) {
    for (i = 0; i < n; i++) { g_id[c->start + i] = ids[i]; g_have_id[c->start + i] = 1; }
    if (!nosync) c->acked = 1;
  }
  return rc;
}

static void do_flush(ngs *db) {
  if (ngs_flush(db) == NGS_OK) { int i; for (i = 0; i < g_ncalls; i++) if (g_calls[i].nosync && g_have_id[g_calls[i].start]) g_calls[i].acked = 1; }
}

/* the scripted workload: singles, a batch, un-synced singles then a flush, another batch, more singles */
static void run_workload(sim *s) {
  ngs *db = NULL;
  int i, rc;
  g_ncalls = 0; g_nf = 0; memset(g_have_id, 0, sizeof g_have_id);
  rc = open_sim(s, 1, G_SK, 2048, 0, &db);
  if (rc != 0) { ngs_close(db); return; }
#define STEP(x) do { rc = (x); if (rc != 0 && !g_continue) goto out; } while (0)
  for (i = 0; i < 8; i++) STEP(do_call(db, 1, 0));
  STEP(do_call(db, 4, 0));
  for (i = 0; i < 3; i++) STEP(do_call(db, 1, 1));
  do_flush(db);
  STEP(do_call(db, 3, 0));
  for (i = 0; i < 12; i++) STEP(do_call(db, 1, 0));
out:
  ngs_close(db);
}

/* After a crash or failure: reboot, reopen, and check every promise. Returns 1 if all hold. */
static int verify_after(sim *s, const char *what) {
  ngs *db = NULL;
  ngs_iter *it = NULL;
  ngs_fact *f = NULL;
  int present[MAXF], ok = 1, i, last = -1, rc;
  unsigned long before = g_fail;
  memset(present, 0, sizeof present);
  if (getenv("NGS_TRACE")) printf(" verify_after open\n");
  rc = open_sim(s, 1, G_SK, 2048, 0, &db);
  if (getenv("NGS_TRACE")) printf(" opened rc=%d\n", rc);
  CHECKF(rc == 0, "%s: reopen failed rc %d (%s)", what, rc, ngs_errmsg(db));
  if (rc != 0) { ngs_close(db); return 0; }
  rc = ngs_verify(db, NULL, 0);
  CHECKF(rc == 0, "%s: verify rc %d (%s)", what, rc, ngs_errmsg(db));
  CHECK(ngs_scan(db, NULL, &it) == 0);
  while (ngs_iter_next(it, &f) == 0) {
    int idx = -1;
    ngs_fact_in want;
    if (sscanf(f->title.p, "f%d", &idx) != 1 || idx < 0 || idx >= g_nf) { CHECKF(0, "%s: unknown fact in the log", what); ngs_free(f); continue; }
    fill_fact(idx, &want);
    CHECKF(f->ns.n == strlen(g_ns[idx]) && memcmp(f->ns.p, g_ns[idx], f->ns.n) == 0 && f->body.n == strlen(g_body[idx]) &&
           memcmp(f->body.p, g_body[idx], f->body.n) == 0 && f->kind == want.kind && f->n_tags == want.n_tags && f->attrs_len == want.attrs_len && f->schema == want.schema,
           "%s: fact %d came back different", what, idx);
    CHECKF(idx > last, "%s: log order broken at fact %d", what, idx);
    last = idx; present[idx] = 1;
    ngs_free(f);
  }
  ngs_iter_close(it);
  for (i = 0; i < g_ncalls; i++) {
    int k, cnt = 0;
    for (k = 0; k < g_calls[i].n; k++) cnt += present[g_calls[i].start + k];
    CHECKF(cnt == 0 || cnt == g_calls[i].n, "%s: call %d is half visible (%d of %d facts)", what, i, cnt, g_calls[i].n);
    if (g_calls[i].acked) {
      CHECKF(cnt == g_calls[i].n, "%s: acknowledged call %d lost (%d of %d)", what, i, cnt, g_calls[i].n);
      for (k = 0; k < g_calls[i].n; k++) {
        if (g_have_id[g_calls[i].start + k]) { ngs_fact *gf = NULL; CHECKF(ngs_get(db, &g_id[g_calls[i].start + k], &gf) == 0, "%s: acknowledged id unreadable", what); ngs_free(gf); }
      }
    }
  }
  /* the recovered database takes new writes and stays consistent */
  {
    ngs_fact_in x;
    ngs_id id;
    int post = MAXF - 1;
    fill_fact(post, &x);
    g_nf = post + 1;
    rc = ngs_remember(db, &x, 0, &id);
    CHECKF(rc == 0, "%s: write after recovery rc %d (%s)", what, rc, ngs_errmsg(db));
    CHECKF(ngs_verify(db, NULL, 0) == 0, "%s: verify after recovery write", what);
    CHECK(ngs_get(db, &id, &f) == 0); ngs_free(f);
  }
  ngs_close(db);
  ok = (g_fail == before);
  return ok;
}

static unsigned long g_crash_points, g_crash_runs, g_fail_runs;

static void test_crash(void) {
  sim *dry = sim_new(7);
  uint64_t N, op;
  int variant;
  static const int keeps[3] = { 0, 50, 100 };
  int ki, seed;
  unsigned long kinds[9] = { 0 };
  clock_t t0 = clock();
  g_name = "crash";
  g_continue = 0;
  run_workload(dry);
  N = sim_ops(dry);
  CHECK(g_ncalls == 8 + 1 + 3 + 1 + 12);
  for (op = 1; op <= N; op++) kinds[sim_op_kind(dry, op)]++;
  printf("  workload: %d calls, %d facts, %lu state-changing calls (open-create %lu, write %lu, fsync %lu, truncate %lu, rename %lu, unlink %lu, mkdir %lu, dir-fsync %lu)\n",
         g_ncalls, g_nf, (unsigned long)N, kinds[1], kinds[2], kinds[3], kinds[4], kinds[5], kinds[6], kinds[7], kinds[8]);
  sim_free(dry);
  CHECK(N > 50);
  for (op = 1; op <= N; op++) {
    int kind;
    {
      sim *probe = sim_new(7);
      run_workload(probe);
      kind = sim_op_kind(probe, op);
      sim_free(probe);
    }
    for (variant = SIM_BEFORE; variant <= SIM_AFTER; variant++) {
      if (variant == SIM_PARTIAL && kind != SIMK_PWRITE) continue;
      g_crash_points++;
      for (ki = 0; ki < 3; ki++) {
        for (seed = 1; seed <= 3; seed++) {
          sim *s = sim_new(7);
          char what[96];
          if (getenv("NGS_TRACE")) printf("op %lu var %d keep %d seed %d\n", (unsigned long)op, variant, keeps[ki], seed);
          sim_arm_crash(s, op, variant);
          run_workload(s);
          if (getenv("NGS_TRACE")) printf(" workload done\n");
          CHECKF(sim_crashed(s), "crash at op %lu variant %d never fired", (unsigned long)op, variant);
          sim_reboot(s, (uint64_t)seed * 7919u + op, keeps[ki], keeps[ki] == 100 ? 100 : 50);
          snprintf(what, sizeof what, "crash op %lu (kind %d) variant %d keep %d seed %d", (unsigned long)op, kind, variant, keeps[ki], seed);
          verify_after(s, what);
          g_crash_runs++;
          sim_free(s);
        }
      }
    }
  }
  printf("  crash injection: %lu injection points x 9 power-loss outcomes = %lu runs, %.1f s\n", g_crash_points, g_crash_runs, (double)(clock() - t0) / CLOCKS_PER_SEC);

  /* one-shot I/O failures: the process survives the failed call; then clean shutdown and power loss */
  g_continue = 1;
  {
    sim *dry2 = sim_new(7);
    g_continue = 0; run_workload(dry2); g_continue = 1;
    N = sim_ops(dry2);
    sim_free(dry2);
  }
  for (op = 1; op <= N; op++) {
    int mode;
    for (mode = 0; mode < 3; mode++) {
      sim *s = sim_new(7);
      char what[96];
      sim_arm_fail(s, op);
      run_workload(s);
      if (mode == 0) sim_clean_shutdown(s); else sim_reboot(s, op * 31u + (uint64_t)mode, mode == 1 ? 50 : 0, 50);
      snprintf(what, sizeof what, "one-shot failure at op %lu mode %d", (unsigned long)op, mode);
      verify_after(s, what);
      g_fail_runs++;
      sim_free(s);
    }
  }
  g_continue = 0;
  printf("  one-shot I/O failures: %lu runs (failure at every call; clean stop, 50%% and 0%% sector survival)\n", g_fail_runs);
}

/* every byte of every segment flipped, one bit each: detected, never a wrong read */
static void build_dataset(sim *s, ngs_id *ids, int n) {
  ngs *db = NULL;
  int i;
  char t[16];
  open_sim(s, 1, G_SK, 2048, 0, &db);
  for (i = 0; i < n; i++) {
    ngs_fact_in x;
    snprintf(t, sizeof t, "f%d", i);
    x = mkfact(i % 3 ? "p" : "q", t, "payload for the torture run, long enough to span a few sectors, payload for the torture run", NGS_SEMANTIC);
    if (i % 7 == 3) { ngs_fact_in arr[3]; ngs_id bid[3]; int k; for (k = 0; k < 3; k++) arr[k] = x; ngs_remember_many(db, arr, 3, 0, bid); ids[i] = bid[0]; i += 0; }
    else ngs_remember(db, &x, 0, &ids[i]);
  }
  ngs_close(db);
  sim_clean_shutdown(s);
}

static void test_torture(void) {
  sim *s = sim_new(11);
  ngs *db = NULL;
  ngs_id ids[30];
  int nseg, sg, total_facts = 0;
  unsigned long runs = 0, refused = 0, cut = 0, flipped_last = 0;
  char path[64];
  ngs_iter *it = NULL;
  ngs_fact *f = NULL;
  g_name = "torture";
  build_dataset(s, ids, 30);
  /* count the facts the dataset really holds */
  CHECK(open_sim(s, 0, NULL, 0, 1, &db) == 0);
  CHECK(ngs_scan(db, NULL, &it) == 0); while (ngs_iter_next(it, &f) == 0) { total_facts++; ngs_free(f); } ngs_iter_close(it);
  CHECK(ngs_verify(db, NULL, 0) == 0);
  ngs_close(db);
  nseg = (int)sim_count_names(s, "db/log");
  CHECK(nseg >= 5 && total_facts >= 30);
  for (sg = 1; sg <= nseg; sg++) {
    long len;
    long off;
    snprintf(path, sizeof path, "db/log/%06d.seg", sg);
    len = sim_file_len(s, path);
    CHECK(len > 64);
    for (off = 0; off < len; off++) {
      ngs *x = NULL;
      int rc;
      uint8_t mask = (uint8_t)(1u << (off % 8));
      sim_flip(s, path, (size_t)off, mask);
      rc = open_sim(s, 0, NULL, 0, 1, &x);
      runs++;
      if (rc != 0) {
        CHECKF(rc == NGS_CORRUPT, "segment %d byte %ld: open failed with %d, not CORRUPT", sg, off, rc);
        refused++;
      } else {
        int got = 0, vrc;
        ngs_iter *it2 = NULL;
        CHECKF(sg == nseg, "segment %d byte %ld: damage in a completed segment was accepted", sg, off);
        vrc = ngs_verify(x, NULL, 0);
        CHECKF(vrc == 0, "segment %d byte %ld: opened but verify says %d", sg, off, vrc);
        ngs_scan(x, NULL, &it2);
        while (ngs_iter_next(it2, &f) == 0) {
          int idx = -1;
          if (sscanf(f->title.p, "f%d", &idx) != 1) CHECKF(0, "wrong data");
          CHECK(f->body.n == 91 && memcmp(f->body.p, "payload for the torture run", 27) == 0);
          got++; ngs_free(f);
        }
        ngs_iter_close(it2);
        CHECKF(got < total_facts, "segment %d byte %ld: flip silently accepted, all %d facts present", sg, off, got);
        cut++;
        flipped_last++;
      }
      ngs_close(x);
      sim_flip(s, path, (size_t)off, mask);                               /* restore */
    }
  }
  printf("  bit flips: %lu runs over %d segments; %lu refused as NGS_CORRUPT, %lu cut as a torn tail of the last segment, 0 silently accepted\n",
         runs, nseg, refused, cut);
  CHECK(flipped_last > 0 && refused > 0);
  sim_free(s);

  /* torn tail on a read-write open: cut, evidence kept, durable, and the log carries on */
  {
    int k, last_seg;
    unsigned long checked = 0;
    for (k = 0; k < 6; k++) {
      sim *t = sim_new(20 + (uint64_t)k);
      ngs_id ids2[30];
      long len;
      ngs *r = NULL;
      int rc2, before = 0, after = 0;
      build_dataset(t, ids2, 30);
      last_seg = (int)sim_count_names(t, "db/log");
      snprintf(path, sizeof path, "db/log/%06d.seg", last_seg);
      len = sim_file_len(t, path);
      sim_flip(t, path, (size_t)(64 + (long)k * 37 % (len - 64 - 4)), 0x10);
      rc2 = open_sim(t, 0, G_SK, 2048, 0, &r);
      CHECKF(rc2 == 0, "read-write open of a torn tail failed: %d", rc2);
      if (rc2 == 0) {
        ngs_fact_in x = mkfact("p", "after-cut", "x", NGS_EPISODIC);
        ngs_id nid;
        CHECK(strstr(ngs_errmsg(r), "recovered") != NULL);
        CHECK(ngs_verify(r, NULL, 0) == 0);
        ngs_scan(r, NULL, &it); while (ngs_iter_next(it, &f) == 0) { before++; ngs_free(f); } ngs_iter_close(it);
        CHECK(before < 30 + 8);
        CHECK(ngs_remember(r, &x, 0, &nid) == 0);
        ngs_close(r);
        sim_clean_shutdown(t);
        CHECK(open_sim(t, 0, G_SK, 2048, 0, &r) == 0);
        CHECK(ngs_errmsg(r)[0] == 0);                                      /* nothing left to recover the second time */
        CHECK(ngs_verify(r, NULL, 0) == 0);
        ngs_scan(r, NULL, &it); while (ngs_iter_next(it, &f) == 0) { after++; ngs_free(f); } ngs_iter_close(it);
        CHECK(after == before + 1);
        CHECK(ngs_get(r, &nid, &f) == 0); ngs_free(f);
        ngs_close(r);
        { char tp[80]; snprintf(tp, sizeof tp, "%s.torn", path); CHECK(sim_file_len(t, tp) > 0); }
        checked++;
      }
      sim_free(t);
    }
    printf("  torn-tail recovery (read-write): %lu runs, tail cut, evidence kept in .torn, second open clean, log accepts new writes\n", checked);
  }
}

/* ============================================================ real filesystem + threads */
#ifdef _WIN32
typedef HANDLE thr_t;
static int thr_start(thr_t *t, unsigned (__stdcall *fn)(void *), void *arg) { *t = (HANDLE)_beginthreadex(NULL, 0, fn, arg, 0, NULL); return *t ? 0 : -1; }
static void thr_join(thr_t t) { WaitForSingleObject(t, INFINITE); CloseHandle(t); }
#define THR_FN(name) static unsigned __stdcall name(void *arg)
#define THR_RET return 0
#else
typedef pthread_t thr_t;
static int thr_start(thr_t *t, void *(*fn)(void *), void *arg) { return pthread_create(t, NULL, fn, arg); }
static void thr_join(thr_t t) { pthread_join(t, NULL); }
#define THR_FN(name) static void *name(void *arg)
#define THR_RET return NULL
#endif

typedef struct { ngs *db; int id; int n; int failures; } wctx;

THR_FN(writer_main) {
  wctx *w = (wctx *)arg;
  int i;
  char ns[8], title[24];
  snprintf(ns, sizeof ns, "w%d", w->id);
  for (i = 0; i < w->n; i++) {
    ngs_fact_in x;
    snprintf(title, sizeof title, "t%d-%d", w->id, i);
    x = mkfact(ns, title, "threaded body", NGS_EPISODIC);
    if (ngs_remember(w->db, &x, NGS_WRITE_NO_SYNC, NULL) != 0) w->failures++;
  }
  THR_RET;
}

THR_FN(reader_main) {
  wctx *w = (wctx *)arg;
  int round;
  for (round = 0; round < 40; round++) {
    ngs_iter *it = NULL;
    ngs_fact *f = NULL;
    if (ngs_scan(w->db, NULL, &it) != 0) { w->failures++; continue; }
    while (ngs_iter_next(it, &f) == 0) {
      ngs_fact *g = NULL;
      if (ngs_get(w->db, &f->id, &g) != 0) w->failures++;
      ngs_free(g); ngs_free(f);
    }
    ngs_iter_close(it);
  }
  THR_RET;
}

static void test_real_fs(void) {
  char dir[160];
  ngs *db = NULL, *db2 = NULL;
  ngs_id ids[12], bid[3];
  ngs_fact *f = NULL;
  ngs_pubkey pk1, pk2;
  ngs_open_opts o = NGS_OPEN_OPTS_INIT;
  int i, rc;
  g_name = "real-fs";
  /* a UTF-8 directory name, unique per run */
  snprintf(dir, sizeof dir, "build/fsdb_\xC3\xA9_%lu", (unsigned long)time(NULL) * 1000u + (unsigned long)(clock() % 1000));
  o.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  rc = ngs_open(dir, &o, &db);
  CHECKF(rc == 0, "ngs_open on the real filesystem: %d (%s)", rc, ngs_errmsg(db));
  if (rc != 0) { ngs_close(db); return; }
  CHECK(ngs_node_pubkey(db, &pk1) == 0);
  for (i = 0; i < 12; i++) {
    char t[16];
    ngs_fact_in x;
    snprintf(t, sizeof t, "r%d", i);
    x = mkfact("real", t, "real filesystem body", NGS_SEMANTIC);
    CHECK(ngs_remember(db, &x, 0, &ids[i]) == 0);
  }
  { ngs_fact_in arr[3]; for (i = 0; i < 3; i++) arr[i] = mkfact("real", "batch", "b", NGS_EPISODIC); CHECK(ngs_remember_many(db, arr, 3, 0, bid) == 0); }
  CHECK(ngs_verify(db, NULL, 0) == 0);
  CHECK(ngs_open(dir, &o, &db2) == NGS_BUSY);                                /* single writer */
  ngs_close(db2); db2 = NULL;
  { ngs_open_opts ro = NGS_OPEN_OPTS_INIT; ro.flags = NGS_OPEN_READONLY; CHECK(ngs_open(dir, &ro, &db2) == 0); CHECK(ngs_get(db2, &ids[3], &f) == 0); ngs_free(f); f = NULL; ngs_close(db2); db2 = NULL; }
  ngs_close(db);
  o.flags = NGS_OPEN_READWRITE;
  CHECK(ngs_open(dir, &o, &db) == 0);                                        /* the generated key is found again */
  CHECK(ngs_node_pubkey(db, &pk2) == 0 && memcmp(pk1.b, pk2.b, 32) == 0);
  for (i = 0; i < 12; i++) { CHECK(ngs_get(db, &ids[i], &f) == 0 && f && f->seq == (uint64_t)(i + 1)); ngs_free(f); f = NULL; }
  CHECK(ngs_verify(db, NULL, 0) == 0);
  ngs_close(db);

  /* threads: 4 writers and 2 readers share one handle */
  {
    thr_t th[6];
    wctx w[6];
    int t, ok = 1;
    size_t total = 0;
    ngs_iter *it = NULL;
    uint64_t lastseq[4] = { 0 };
    snprintf(dir, sizeof dir, "build/fsdb_thr_%lu", (unsigned long)time(NULL) * 1000u + (unsigned long)(clock() % 1000));
    o.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
    CHECK(ngs_open(dir, &o, &db) == 0);
    for (t = 0; t < 6; t++) { w[t].db = db; w[t].id = t; w[t].n = 250; w[t].failures = 0; }
    for (t = 0; t < 6; t++) if (thr_start(&th[t], t < 4 ? writer_main : reader_main, &w[t]) != 0) ok = 0;
    CHECK(ok);
    for (t = 0; t < 6; t++) thr_join(th[t]);
    for (t = 0; t < 6; t++) CHECKF(w[t].failures == 0, "thread %d had %d failed calls", t, w[t].failures);
    CHECK(ngs_flush(db) == 0);
    CHECK(ngs_verify(db, NULL, 0) == 0);
    CHECK(ngs_scan(db, NULL, &it) == 0);
    while (ngs_iter_next(it, &f) == 0) {
      int wid = f->ns.p[1] - '0';
      total++;
      if (wid >= 0 && wid < 4) { CHECKF(f->seq == lastseq[wid] + 1, "per-namespace sequence broke"); lastseq[wid] = f->seq; }
      ngs_free(f);
    }
    ngs_iter_close(it);
    CHECK(total == 1000);
    ngs_close(db);
    CHECK(ngs_open(dir, &o, &db) == 0 && ngs_verify(db, NULL, 0) == 0);     /* and it survives a reopen */
    ngs_close(db);
    printf("  threads: 4 writers x 250 facts + 2 readers on one handle: 1000 facts, sequences gapless per namespace, verify ok\n");
  }
}

/* ============================================================ ABI */
#include "abi_asserts.h"

static void test_abi(void) {
  g_name = "abi";
  /* every input/output struct starts with a uint32_t size at offset 0 */
  CHECK(offsetof(ngs_open_opts, size) == 0 && offsetof(ngs_fact_in, size) == 0 && offsetof(ngs_fact, size) == 0);
  CHECK(offsetof(ngs_query, size) == 0 && offsetof(ngs_hit, size) == 0 && offsetof(ngs_results, size) == 0);
  CHECK(offsetof(ngs_scan_opts, size) == 0 && offsetof(ngs_sync_report, size) == 0 && offsetof(ngs_stats_t, size) == 0);
  CHECK(sizeof(ngs_id) == 32 && sizeof(ngs_pubkey) == 32 && sizeof(ngs_time) == 8);
  CHECK(sizeof(ngs_fact_in) <= 0xFFFFFFFFu);
  CHECK(NGS_N_ARMS == 5 && NGS_ALIGN_MAX == 16);
  printf("  abi: %d compile-time layout assertions (sizeof and offsetof of every public struct, 64-bit targets)\n", NGS_ABI_ASSERT_COUNT);
}

int main(int argc, char **argv) {
  int only_fast = (argc > 1 && strcmp(argv[1], "--fast") == 0);
  setvbuf(stdout, NULL, _IONBF, 0);
  clock_t t0 = clock();
  key_from_tag(G_SK, G_PK, 1);
  key_from_tag(G_SK2, G_PK2, 2);
  printf("NGS M1 test suite (version %s, format %d)\n", ngs_libversion(), NGS_FORMAT);
  test_crc_blake_ed();
  test_utf8();
  test_cbor();
  test_record_and_header();
  test_api();
  test_segments_and_keys();
  test_abi();
  test_real_fs();
  test_torture();
  if (!only_fast) test_crash();
  printf("\n%lu checks, %lu failed, %.1f s\n", g_checks, g_fail, (double)(clock() - t0) / CLOCKS_PER_SEC);
  return g_fail ? 1 : 0;
}
