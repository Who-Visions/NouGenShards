/*
** nougenshards.c -- NouGenShards (NGS) native memory engine, M1 entry.
**
** Bake-off entry: meta-app lane (Linux VM). Branch feat/ngs-m1-metaapp.
** Spec: docs/memory-engine/SPEC.md draft 0.3.1 (PR 1199, 685901aa).
** Public header: ngs.h, used verbatim (../include/ngs.h).
**
** M1 scope (SPEC 10): the signed hash-chained log + canonical CBOR +
** BLAKE3 + Ed25519 + CRC32C + crash recovery + verify/checkpoint.
** API slice implemented: ngs_open, ngs_close, ngs_errmsg, ngs_errstr,
** ngs_libversion(_number), ngs_free, ngs_node_pubkey, ngs_flush,
** ngs_remember, ngs_remember_many, ngs_get, ngs_scan, ngs_iter_next,
** ngs_iter_close, ngs_checkpoint, ngs_verify.
** Everything else (invalidate, link, redact, grant, recall, as_of, mark,
** rebuild, heads, sync_export, sync_import, stats) returns NGS_MISUSE.
**
** Layout of this file (the amalgamation):
**   1. core utilities + CRC32C            (ISO C11 headers only, SPEC 14)
**   2. BLAKE3                             (implemented from the BLAKE3 paper;
**                                        algorithm is public domain / CC0-style
**                                        reference design by the BLAKE3 team)
**   3. SHA-512 (FIPS 180-4) + Ed25519     (original implementation written for
**                                        NGS from RFC 8032; radix-2^26 field
**                                        arithmetic in the style of ref10,
**                                        which is public domain)
**   4. canonical CBOR                     (RFC 8949, deterministic encoding)
**   5. platform layer (POSIX)             (SPEC 15: the only OS-specific code;
**                                        the only place <unistd.h> etc. appear)
**   6. the engine                         (log, recovery, API)
**
** Licence: Apache-2.0 (NGS itself). No identities or hostnames in source.
*/
#if defined(__clang__)
#pragma STDC FP_CONTRACT OFF
#endif
/* Feature-test macros for the platform layer (section 5 below): they must
** be defined before the first libc header, so they live at the very top. */
#if !defined(_WIN32)
#  ifndef _GNU_SOURCE
#    define _GNU_SOURCE 1
#  endif
#  ifndef _FILE_OFFSET_BITS
#    define _FILE_OFFSET_BITS 64
#  endif
#endif

#include "ngs.h"

#include <stddef.h>
#include <stdint.h>
#include <limits.h>
#include <float.h>
#include <stdalign.h>
#include <assert.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include <time.h>
#include <stdio.h>
#include <inttypes.h>

/* ======================================================================
** 1. CRC32C (Castagnoli, reflected poly 0x82F63B78) -- SPEC 3.1.
** The table is generated once at first use (guarded by ngs_open's init).
** ==================================================================== */
static uint32_t ngs_crc_table[256];
static int ngs_crc_ready = 0;

static void ngs_crc_init(void) {
  uint32_t i, j, c;
  if (ngs_crc_ready) return;
  for (i = 0; i < 256; i++) {
    c = i;
    for (j = 0; j < 8; j++) c = (c & 1) ? (0x82F63B78u ^ (c >> 1)) : (c >> 1);
    ngs_crc_table[i] = c;
  }
  ngs_crc_ready = 1;
}

static uint32_t ngs_crc32c(const uint8_t *data, size_t len, uint32_t crc) {
  size_t i;
  crc = ~crc;
  for (i = 0; i < len; i++) crc = ngs_crc_table[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
  return ~crc;
}

/* ======================================================================
** 2. BLAKE3 (hash mode, 32-byte output). Implemented from the BLAKE3
** specification (G, message permutation, chunk/parent outputs, CV stack).
** ==================================================================== */
static const uint32_t NGS_B3_IV[8] = {
  0x6A09E667u, 0xBB67AE85u, 0x3C6EF372u, 0xA54FF53Au,
  0x510E527Fu, 0x9B05688Cu, 0x1F83D9ABu, 0x5BE0CD19u
};
static const uint8_t NGS_B3_PERM[16] = { 2, 6, 3, 10, 7, 0, 4, 13, 1, 11, 12, 5, 9, 14, 15, 8 };

#define NGS_B3_CHUNK_START (1u << 0)
#define NGS_B3_CHUNK_END   (1u << 1)
#define NGS_B3_PARENT      (1u << 2)
#define NGS_B3_ROOT        (1u << 3)
#define NGS_B3_CHUNK_LEN   1024u
#define NGS_B3_BLOCK_LEN   64u

static uint32_t ngs_rotr32(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }

static void ngs_b3_g(uint32_t st[16], int a, int b, int c, int d, uint32_t x, uint32_t y) {
  st[a] = st[a] + st[b] + x; st[d] = ngs_rotr32(st[d] ^ st[a], 16);
  st[c] = st[c] + st[d];     st[b] = ngs_rotr32(st[b] ^ st[c], 12);
  st[a] = st[a] + st[b] + y; st[d] = ngs_rotr32(st[d] ^ st[a], 8);
  st[c] = st[c] + st[d];     st[b] = ngs_rotr32(st[b] ^ st[c], 7);
}

static void ngs_b3_round(uint32_t st[16], const uint32_t m[16]) {
  ngs_b3_g(st, 0, 4,  8, 12, m[0],  m[1]);
  ngs_b3_g(st, 1, 5,  9, 13, m[2],  m[3]);
  ngs_b3_g(st, 2, 6, 10, 14, m[4],  m[5]);
  ngs_b3_g(st, 3, 7, 11, 15, m[6],  m[7]);
  ngs_b3_g(st, 0, 5, 10, 15, m[8],  m[9]);
  ngs_b3_g(st, 1, 6, 11, 12, m[10], m[11]);
  ngs_b3_g(st, 2, 7,  8, 13, m[12], m[13]);
  ngs_b3_g(st, 3, 4,  9, 14, m[14], m[15]);
}

static void ngs_b3_permute(uint32_t m[16]) {
  uint32_t t[16];
  int i;
  for (i = 0; i < 16; i++) t[i] = m[NGS_B3_PERM[i]];
  for (i = 0; i < 16; i++) m[i] = t[i];
}

/* One compression. out16 receives all 16 words (needed for root output). */
static void ngs_b3_compress(const uint32_t cv[8], const uint32_t block[16],
                            uint64_t counter, uint32_t block_len, uint32_t flags,
                            uint32_t out16[16]) {
  uint32_t st[16], m[16];
  int i, r;
  for (i = 0; i < 8; i++) { st[i] = cv[i]; m[i] = block[i]; }
  st[8]  = NGS_B3_IV[0]; st[9]  = NGS_B3_IV[1];
  st[10] = NGS_B3_IV[2]; st[11] = NGS_B3_IV[3];
  st[12] = (uint32_t)(counter & 0xFFFFFFFFu);
  st[13] = (uint32_t)(counter >> 32);
  st[14] = block_len;
  st[15] = flags;
  for (i = 8; i < 16; i++) m[i] = block[i];
  for (r = 0; r < 7; r++) {
    ngs_b3_round(st, m);
    if (r != 6) ngs_b3_permute(m);
  }
  for (i = 0; i < 8; i++) {
    out16[i]     = st[i] ^ st[i + 8];
    out16[i + 8] = st[i + 8] ^ cv[i];
  }
}

static void ngs_load32le(const uint8_t *p, uint32_t *out) {
  *out = (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void ngs_store32le(uint8_t *p, uint32_t v) {
  p[0] = (uint8_t)(v & 0xFFu); p[1] = (uint8_t)((v >> 8) & 0xFFu);
  p[2] = (uint8_t)((v >> 16) & 0xFFu); p[3] = (uint8_t)((v >> 24) & 0xFFu);
}
static void ngs_store64le(uint8_t *p, uint64_t v) {
  int i;
  for (i = 0; i < 8; i++) p[i] = (uint8_t)((v >> (8 * i)) & 0xFFu);
}
static uint64_t ngs_load64le(const uint8_t *p) {
  uint64_t v = 0;
  int i;
  for (i = 0; i < 8; i++) v |= ((uint64_t)p[i]) << (8 * i);
  return v;
}

/* An "output" object: can yield a chaining value, or the root hash. */
typedef struct {
  uint32_t cv[8];
  uint32_t block[16];
  uint64_t counter;
  uint32_t block_len;
  uint32_t flags;
} ngs_b3_output;

static void ngs_b3_output_cv(const ngs_b3_output *o, uint32_t cv_out[8]) {
  uint32_t out16[16];
  int i;
  ngs_b3_compress(o->cv, o->block, o->counter, o->block_len, o->flags, out16);
  /* ngs_b3_compress already applied the final XORs: words 0..7 ARE the
  ** chaining value, and all 16 words are the root output block. */
  for (i = 0; i < 8; i++) cv_out[i] = out16[i];
}

static void ngs_b3_output_root(const ngs_b3_output *o, uint8_t *out, size_t out_len) {
  uint64_t counter = 0;
  while (out_len > 0) {
    uint32_t out16[16];
    size_t take, i;
    ngs_b3_compress(o->cv, o->block, counter, o->block_len, o->flags | NGS_B3_ROOT, out16);
    take = out_len > 64 ? 64 : out_len;
    for (i = 0; i < take; i++) out[i] = (uint8_t)(out16[i / 4] >> (8 * (i % 4)));
    out += take; out_len -= take; counter++;
  }
}

typedef struct {
  uint32_t cv[8];
  uint64_t chunk_counter;
  uint8_t  buf[NGS_B3_BLOCK_LEN];
  uint8_t  buf_len;
  uint8_t  blocks_compressed;
} ngs_b3_chunk;

static void ngs_b3_chunk_init(ngs_b3_chunk *c, uint64_t counter) {
  int i;
  for (i = 0; i < 8; i++) c->cv[i] = NGS_B3_IV[i];
  c->chunk_counter = counter;
  c->buf_len = 0;
  c->blocks_compressed = 0;
}

static size_t ngs_b3_chunk_len(const ngs_b3_chunk *c) {
  return (size_t)c->blocks_compressed * NGS_B3_BLOCK_LEN + c->buf_len;
}

static void ngs_b3_chunk_update(ngs_b3_chunk *c, const uint8_t *data, size_t len) {
  while (len > 0) {
    size_t take;
    if (c->buf_len == NGS_B3_BLOCK_LEN) {
      uint32_t block[16], out16[16];
      int i;
      for (i = 0; i < 16; i++) ngs_load32le(c->buf + 4 * i, &block[i]);
      ngs_b3_compress(c->cv, block, c->chunk_counter, NGS_B3_BLOCK_LEN,
                      c->blocks_compressed == 0 ? NGS_B3_CHUNK_START : 0, out16);
      for (i = 0; i < 8; i++) c->cv[i] = out16[i];
      c->blocks_compressed++;
      c->buf_len = 0;
    }
    take = NGS_B3_BLOCK_LEN - c->buf_len;
    if (take > len) take = len;
    memcpy(c->buf + c->buf_len, data, take);
    c->buf_len = (uint8_t)(c->buf_len + take);
    data += take; len -= take;
  }
}

static void ngs_b3_chunk_output(const ngs_b3_chunk *c, ngs_b3_output *o) {
  int i;
  for (i = 0; i < 8; i++) o->cv[i] = c->cv[i];
  for (i = 0; i < 16; i++) {
    uint8_t b[4] = { 0, 0, 0, 0 };
    int j;
    for (j = 0; j < 4; j++) {
      size_t idx = (size_t)i * 4 + (size_t)j;
      if (idx < c->buf_len) b[j] = c->buf[idx];
    }
    o->block[i] = (uint32_t)b[0] | ((uint32_t)b[1] << 8) | ((uint32_t)b[2] << 16) | ((uint32_t)b[3] << 24);
  }
  o->counter = c->chunk_counter;
  o->block_len = c->buf_len;
  o->flags = NGS_B3_CHUNK_END | (c->blocks_compressed == 0 ? NGS_B3_CHUNK_START : 0);
}

static void ngs_b3_parent_output(const uint32_t left_cv[8], const uint32_t right_cv[8],
                                 ngs_b3_output *o) {
  int i;
  for (i = 0; i < 8; i++) {
    o->cv[i] = NGS_B3_IV[i];
    o->block[i] = left_cv[i];
    o->block[i + 8] = right_cv[i];
  }
  o->counter = 0;
  o->block_len = NGS_B3_BLOCK_LEN;
  o->flags = NGS_B3_PARENT;
}

typedef struct {
  ngs_b3_chunk chunk;
  uint32_t cv_stack[54][8];
  size_t   stack_len;
} ngs_blake3;

static void ngs_blake3_init(ngs_blake3 *h) {
  ngs_b3_chunk_init(&h->chunk, 0);
  h->stack_len = 0;
}

static void ngs_blake3_update(ngs_blake3 *h, const uint8_t *data, size_t len) {
  while (len > 0) {
    size_t take;
    if (ngs_b3_chunk_len(&h->chunk) == NGS_B3_CHUNK_LEN) {
      uint32_t cv[8];
      uint64_t total_chunks;
      ngs_b3_output o;
      ngs_b3_chunk_output(&h->chunk, &o);
      ngs_b3_output_cv(&o, cv);
      total_chunks = h->chunk.chunk_counter + 1;
      while ((total_chunks & 1u) == 0) {
        ngs_b3_output po;
        uint32_t merged[8];
        h->stack_len--;
        ngs_b3_parent_output(h->cv_stack[h->stack_len], cv, &po);
        ngs_b3_output_cv(&po, merged);
        memcpy(cv, merged, sizeof cv);
        total_chunks >>= 1;
      }
      memcpy(h->cv_stack[h->stack_len], cv, sizeof cv);
      h->stack_len++;
      ngs_b3_chunk_init(&h->chunk, h->chunk.chunk_counter + 1);
    }
    take = NGS_B3_CHUNK_LEN - ngs_b3_chunk_len(&h->chunk);
    if (take > len) take = len;
    ngs_b3_chunk_update(&h->chunk, data, take);
    data += take; len -= take;
  }
}

static void ngs_blake3_final(const ngs_blake3 *h, uint8_t *out, size_t out_len) {
  ngs_b3_output o;
  size_t i;
  ngs_b3_chunk_output(&h->chunk, &o);
  for (i = h->stack_len; i-- > 0; ) {
    ngs_b3_output po;
    uint32_t right_cv[8];
    ngs_b3_output_cv(&o, right_cv);
    ngs_b3_parent_output(h->cv_stack[i], right_cv, &po);
    o = po;
  }
  ngs_b3_output_root(&o, out, out_len);
}

static void ngs_blake3_hash(const uint8_t *data, size_t len, uint8_t out[32]) {
  ngs_blake3 h;
  ngs_blake3_init(&h);
  if (len > 0) ngs_blake3_update(&h, data, len);
  ngs_blake3_final(&h, out, 32);
}

/* ======================================================================
** 3a. SHA-512 (FIPS 180-4). Needed by Ed25519 (RFC 8032).
** ==================================================================== */
static const uint64_t NGS_SHA512_K[80] = {
  0x428a2f98d728ae22ULL, 0x7137449123ef65cdULL, 0xb5c0fbcfec4d3b2fULL, 0xe9b5dba58189dbbcULL,
  0x3956c25bf348b538ULL, 0x59f111f1b605d019ULL, 0x923f82a4af194f9bULL, 0xab1c5ed5da6d8118ULL,
  0xd807aa98a3030242ULL, 0x12835b0145706fbeULL, 0x243185be4ee4b28cULL, 0x550c7dc3d5ffb4e2ULL,
  0x72be5d74f27b896fULL, 0x80deb1fe3b1696b1ULL, 0x9bdc06a725c71235ULL, 0xc19bf174cf692694ULL,
  0xe49b69c19ef14ad2ULL, 0xefbe4786384f25e3ULL, 0x0fc19dc68b8cd5b5ULL, 0x240ca1cc77ac9c65ULL,
  0x2de92c6f592b0275ULL, 0x4a7484aa6ea6e483ULL, 0x5cb0a9dcbd41fbd4ULL, 0x76f988da831153b5ULL,
  0x983e5152ee66dfabULL, 0xa831c66d2db43210ULL, 0xb00327c898fb213fULL, 0xbf597fc7beef0ee4ULL,
  0xc6e00bf33da88fc2ULL, 0xd5a79147930aa725ULL, 0x06ca6351e003826fULL, 0x142929670a0e6e70ULL,
  0x27b70a8546d22ffcULL, 0x2e1b21385c26c926ULL, 0x4d2c6dfc5ac42aedULL, 0x53380d139d95b3dfULL,
  0x650a73548baf63deULL, 0x766a0abb3c77b2a8ULL, 0x81c2c92e47edaee6ULL, 0x92722c851482353bULL,
  0xa2bfe8a14cf10364ULL, 0xa81a664bbc423001ULL, 0xc24b8b70d0f89791ULL, 0xc76c51a30654be30ULL,
  0xd192e819d6ef5218ULL, 0xd69906245565a910ULL, 0xf40e35855771202aULL, 0x106aa07032bbd1b8ULL,
  0x19a4c116b8d2d0c8ULL, 0x1e376c085141ab53ULL, 0x2748774cdf8eeb99ULL, 0x34b0bcb5e19b48a8ULL,
  0x391c0cb3c5c95a63ULL, 0x4ed8aa4ae3418acbULL, 0x5b9cca4f7763e373ULL, 0x682e6ff3d6b2b8a3ULL,
  0x748f82ee5defb2fcULL, 0x78a5636f43172f60ULL, 0x84c87814a1f0ab72ULL, 0x8cc702081a6439ecULL,
  0x90befffa23631e28ULL, 0xa4506cebde82bde9ULL, 0xbef9a3f7b2c67915ULL, 0xc67178f2e372532bULL,
  0xca273eceea26619cULL, 0xd186b8c721c0c207ULL, 0xeada7dd6cde0eb1eULL, 0xf57d4f7fee6ed178ULL,
  0x06f067aa72176fbaULL, 0x0a637dc5a2c898a6ULL, 0x113f9804bef90daeULL, 0x1b710b35131c471bULL,
  0x28db77f523047d84ULL, 0x32caab7b40c72493ULL, 0x3c9ebe0a15c9bebcULL, 0x431d67c49c100d4cULL,
  0x4cc5d4becb3e42b6ULL, 0x597f299cfc657e2aULL, 0x5fcb6fab3ad6faecULL, 0x6c44198c4a475817ULL
};

typedef struct { uint64_t h[8]; uint8_t buf[128]; size_t buf_len; uint64_t total; } ngs_sha512_ctx;

static uint64_t ngs_rotr64(uint64_t x, int n) { return (x >> n) | (x << (64 - n)); }

static void ngs_sha512_block(ngs_sha512_ctx *c, const uint8_t *p) {
  uint64_t w[80], a, b, cc, d, e, f, g, h;
  int i;
  for (i = 0; i < 16; i++) {
    uint64_t v = 0;
    int j;
    for (j = 0; j < 8; j++) v = (v << 8) | p[i * 8 + j];
    w[i] = v;
  }
  for (i = 16; i < 80; i++) {
    uint64_t s0 = ngs_rotr64(w[i - 15], 1) ^ ngs_rotr64(w[i - 15], 8) ^ (w[i - 15] >> 7);
    uint64_t s1 = ngs_rotr64(w[i - 2], 19) ^ ngs_rotr64(w[i - 2], 61) ^ (w[i - 2] >> 6);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  a = c->h[0]; b = c->h[1]; cc = c->h[2]; d = c->h[3];
  e = c->h[4]; f = c->h[5]; g = c->h[6]; h = c->h[7];
  for (i = 0; i < 80; i++) {
    uint64_t S1 = ngs_rotr64(e, 14) ^ ngs_rotr64(e, 18) ^ ngs_rotr64(e, 41);
    uint64_t ch = (e & f) ^ (~e & g);
    uint64_t t1 = h + S1 + ch + NGS_SHA512_K[i] + w[i];
    uint64_t S0 = ngs_rotr64(a, 28) ^ ngs_rotr64(a, 34) ^ ngs_rotr64(a, 39);
    uint64_t mj = (a & b) ^ (a & cc) ^ (b & cc);
    uint64_t t2 = S0 + mj;
    h = g; g = f; f = e; e = d + t1; d = cc; cc = b; b = a; a = t1 + t2;
  }
  c->h[0] += a; c->h[1] += b; c->h[2] += cc; c->h[3] += d;
  c->h[4] += e; c->h[5] += f; c->h[6] += g; c->h[7] += h;
}

static void ngs_sha512_init(ngs_sha512_ctx *c) {
  static const uint64_t H0[8] = {
    0x6a09e667f3bcc908ULL, 0xbb67ae8584caa73bULL, 0x3c6ef372fe94f82bULL, 0xa54ff53a5f1d36f1ULL,
    0x510e527fade682d1ULL, 0x9b05688c2b3e6c1fULL, 0x1f83d9abfb41bd6bULL, 0x5be0cd19137e2179ULL
  };
  memcpy(c->h, H0, sizeof H0);
  c->buf_len = 0;
  c->total = 0;
}

static void ngs_sha512_update(ngs_sha512_ctx *c, const uint8_t *data, size_t len) {
  c->total += len;
  while (len > 0) {
    size_t take = 128 - c->buf_len;
    if (take > len) take = len;
    memcpy(c->buf + c->buf_len, data, take);
    c->buf_len += take;
    data += take; len -= take;
    if (c->buf_len == 128) { ngs_sha512_block(c, c->buf); c->buf_len = 0; }
  }
}

static void ngs_sha512_final(ngs_sha512_ctx *c, uint8_t out[64]) {
  uint64_t bitlen = c->total * 8;
  uint8_t pad = 0x80, zero = 0, lenbuf[16];
  int i;
  ngs_sha512_update(c, &pad, 1);
  while (c->buf_len != 112) ngs_sha512_update(c, &zero, 1);
  memset(lenbuf, 0, sizeof lenbuf);
  for (i = 0; i < 8; i++) lenbuf[15 - i] = (uint8_t)(bitlen >> (8 * i));
  /* the length block is fed directly, not counted in c->total */
  memcpy(c->buf + 112, lenbuf, 16);
  ngs_sha512_block(c, c->buf);
  for (i = 0; i < 8; i++) {
    uint64_t v = c->h[i];
    int j;
    for (j = 0; j < 8; j++) out[i * 8 + j] = (uint8_t)(v >> (56 - 8 * j));
  }
}

static void ngs_sha512(const uint8_t *data, size_t len, uint8_t out[64]) {
  ngs_sha512_ctx c;
  ngs_sha512_init(&c);
  if (len > 0) ngs_sha512_update(&c, data, len);
  ngs_sha512_final(&c, out);
}

/* ======================================================================
** 3b. Ed25519 (RFC 8032). Field arithmetic in radix 2^26 (limb widths
** alternate 26/25), in the style of the public-domain ref10 code, but
** written for NGS with generic carry and bit packing so every step is
** auditable. Constants d, I=sqrt(-1) and the base point are derived at
** context init from small integers by field exponentiation, so no large
** magic tables are trusted. Group order L is the RFC 8032 constant.
** ==================================================================== */
typedef int64_t ngs_fe[10];

static const uint8_t NGS_ED_L[32] = {
  0xed, 0xd3, 0xf5, 0x5c, 0x1a, 0x63, 0x12, 0x58, 0xd6, 0x9c, 0xf7, 0xa2,
  0xde, 0xf9, 0xde, 0x14, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10
};
static const uint8_t NGS_ED_P_BYTES[32] = {
  0xed, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
  0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
  0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x7f
};

static int ngs_fe_width(int i) { return (i & 1) ? 25 : 26; }
static int ngs_fe_offset(int i) {
  static const int off[10] = { 0, 26, 51, 77, 102, 128, 153, 179, 204, 230 };
  return off[i];
}

static void ngs_fe_0(ngs_fe h) { int i; for (i = 0; i < 10; i++) h[i] = 0; }
static void ngs_fe_1(ngs_fe h) { ngs_fe_0(h); h[0] = 1; }
static void ngs_fe_copy(ngs_fe h, const ngs_fe f) { memcpy(h, f, sizeof(ngs_fe)); }
static void ngs_fe_set_u32(ngs_fe h, uint32_t v) { ngs_fe_0(h); h[0] = (int64_t)v; }

static void ngs_fe_carry(ngs_fe h) {
  int i, pass;
  for (pass = 0; pass < 2; pass++) {
    for (i = 0; i < 9; i++) {
      int w = ngs_fe_width(i);
      int64_t c = h[i] >> w;              /* arithmetic shift: floor division */
      h[i] -= c * ((int64_t)1 << w);   /* not c << w: left shift of a negative value is UB (C11 6.5.7p4) */
      h[i + 1] += c;
    }
    {
      int64_t c = h[9] >> 25;
      h[9] -= c * ((int64_t)1 << 25);
      h[0] += 19 * c;
    }
  }
}

static void ngs_fe_add(ngs_fe h, const ngs_fe f, const ngs_fe g) {
  int i;
  for (i = 0; i < 10; i++) h[i] = f[i] + g[i];
}
static void ngs_fe_sub(ngs_fe h, const ngs_fe f, const ngs_fe g) {
  int i;
  for (i = 0; i < 10; i++) h[i] = f[i] - g[i];
}
static void ngs_fe_neg(ngs_fe h, const ngs_fe f) {
  int i;
  for (i = 0; i < 10; i++) h[i] = -f[i];
}

static void ngs_fe_mul(ngs_fe h, const ngs_fe f0, const ngs_fe g0) {
  ngs_fe f, g;
  int64_t s[10];
  int i, j;
  ngs_fe_copy(f, f0); ngs_fe_copy(g, g0);
  ngs_fe_carry(f); ngs_fe_carry(g);
  for (i = 0; i < 10; i++) s[i] = 0;
  /* The limbs alternate 26/25 bits (offsets 0,26,51,77,...), so the
  ** product of limbs i and j lands at bit offset off[i]+off[j], which is
  ** off[i+j] when at most one of i,j is odd and off[i+j]+1 when both are
  ** odd (hence the x2 for odd*odd, the same compensation ref10 applies
  ** by doubling the odd g limbs). Sums at or past bit 255 fold with the
  ** 2^255 = 19 (mod p) rule. Accumulator bound: ~20 terms x 38 x 2^52,
  ** far inside int64. */
  for (i = 0; i < 10; i++) {
    for (j = 0; j < 10; j++) {
      int64_t prod = f[i] * g[j];
      int64_t coeff = ((i & 1) && (j & 1)) ? 2 : 1;
      if (i + j < 10) s[i + j] += coeff * prod;
      else s[i + j - 10] += 19 * coeff * prod;
    }
  }
  for (i = 0; i < 10; i++) h[i] = s[i];
  ngs_fe_carry(h);
}
static void ngs_fe_sq(ngs_fe h, const ngs_fe f) { ngs_fe_mul(h, f, f); }

/* h = f^e, e a 32-byte little-endian exponent (square-and-multiply). */
static void ngs_fe_pow(ngs_fe h, const ngs_fe f, const uint8_t e[32]) {
  ngs_fe r;
  int bit, started = 0;
  ngs_fe_1(r);
  for (bit = 255; bit >= 0; bit--) {
    int b = (e[bit >> 3] >> (bit & 7)) & 1;
    if (!started && !b) continue;
    if (started) ngs_fe_sq(r, r);
    started = 1;
    if (b) ngs_fe_mul(r, r, f);
  }
  if (!started) ngs_fe_1(r);
  ngs_fe_copy(h, r);
}

static void ngs_fe_invert(ngs_fe h, const ngs_fe f) {
  /* exponent p-2 = 2^255 - 21 */
  static const uint8_t e[32] = {
    0xeb, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x7f
  };
  ngs_fe_pow(h, f, e);
}

static void ngs_fe_tobytes(uint8_t s[32], const ngs_fe f0) {
  ngs_fe h;
  int i, b, ge;
  ngs_fe_copy(h, f0);
  ngs_fe_carry(h);
  memset(s, 0, 32);
  for (i = 0; i < 10; i++) {
    int off = ngs_fe_offset(i), w = ngs_fe_width(i);
    uint64_t v = (uint64_t)h[i];
    for (b = 0; b < w; b++) {
      if ((v >> b) & 1u) {
        int pos = off + b;
        s[pos >> 3] |= (uint8_t)(1u << (pos & 7));
      }
    }
  }
  /* h < 2^255 + slack < 2p, so one conditional subtraction of p suffices */
  ge = 1;
  for (i = 31; i >= 0; i--) {
    if (s[i] > NGS_ED_P_BYTES[i]) { ge = 1; break; }
    if (s[i] < NGS_ED_P_BYTES[i]) { ge = 0; break; }
  }
  if (ge) {
    int borrow = 0;
    for (i = 0; i < 32; i++) {
      int v = (int)s[i] - (int)NGS_ED_P_BYTES[i] - borrow;
      if (v < 0) { v += 256; borrow = 1; } else borrow = 0;
      s[i] = (uint8_t)v;
    }
  }
}

static void ngs_fe_frombytes(ngs_fe h, const uint8_t s[32]) {
  int i, b;
  for (i = 0; i < 10; i++) {
    int off = ngs_fe_offset(i), w = ngs_fe_width(i);
    uint64_t v = 0;
    for (b = 0; b < w; b++) {
      int pos = off + b;
      if ((s[pos >> 3] >> (pos & 7)) & 1u) v |= (uint64_t)1 << b;
    }
    h[i] = (int64_t)v;
  }
}

static int ngs_fe_eq(const ngs_fe f, const ngs_fe g) {
  uint8_t a[32], b[32];
  ngs_fe_tobytes(a, f);
  ngs_fe_tobytes(b, g);
  return memcmp(a, b, 32) == 0;
}
static int ngs_fe_iszero(const ngs_fe f) {
  uint8_t a[32];
  int i, z = 1;
  ngs_fe_tobytes(a, f);
  for (i = 0; i < 32; i++) if (a[i]) z = 0;
  return z;
}

/* Group operations: extended coordinates, a = -1 (add-2008-hwcd / dbl-2008-hwcd). */
typedef struct { ngs_fe X, Y, Z, T; } ngs_ge_p3;
typedef struct { ngs_fe YmX, YpX, T2d; } ngs_ge_cached;

typedef struct {
  ngs_fe d;        /* -121665/121666 */
  ngs_fe d2;       /* 2*d */
  ngs_fe I;        /* sqrt(-1) */
  ngs_ge_p3 B;     /* base point */
  ngs_ge_cached Btab[15]; /* B*1 .. B*15 in cached form */
} ngs_ed_ctx;

static void ngs_ge_p3_identity(ngs_ge_p3 *p) {
  ngs_fe_0(p->X); ngs_fe_1(p->Y); ngs_fe_1(p->Z); ngs_fe_0(p->T);
}
static void ngs_ge_to_cached(const ngs_ed_ctx *ctx, ngs_ge_cached *c, const ngs_ge_p3 *p) {
  /* The cached form is affine (it carries no Z): normalize first. Calling
  ** this on a projective point with Z != 1 without normalizing was a real
  ** bug -- it corrupted every Btab entry past B itself, because the table
  ** build converts points whose Z is whatever the add formula produced. */
  ngs_fe zinv, x, y, t;
  ngs_fe_invert(zinv, p->Z);
  ngs_fe_mul(x, p->X, zinv);
  ngs_fe_mul(y, p->Y, zinv);
  ngs_fe_mul(t, p->T, zinv);
  ngs_fe_sub(c->YmX, y, x);
  ngs_fe_add(c->YpX, y, x);
  ngs_fe_mul(c->T2d, t, ctx->d2);
}

static void ngs_ge_add(ngs_ge_p3 *r, const ngs_ge_p3 *p, const ngs_ge_cached *q) {
  ngs_fe A, B, C, D, E, F, G, H, t1, t2;
  ngs_fe_sub(t1, p->Y, p->X);
  ngs_fe_mul(A, t1, q->YmX);
  ngs_fe_add(t2, p->Y, p->X);
  ngs_fe_mul(B, t2, q->YpX);
  ngs_fe_mul(C, p->T, q->T2d);
  /* D = 2*Z1*Z2. The cached form does not carry Z2: every addend used with
  ** this routine is affine (Z2 == 1) by construction, so D = 2*Z1. */
  ngs_fe_add(D, p->Z, p->Z);
  ngs_fe_sub(E, B, A);
  ngs_fe_sub(F, D, C);
  ngs_fe_add(G, D, C);
  ngs_fe_add(H, B, A);
  ngs_fe_mul(r->X, E, F);
  ngs_fe_mul(r->Y, G, H);
  ngs_fe_mul(r->T, E, H);
  ngs_fe_mul(r->Z, F, G);
}

static void ngs_ge_double(ngs_ge_p3 *r, const ngs_ge_p3 *p) {
  ngs_fe A, B, C, D, E, F, G, H, t;
  ngs_fe_sq(A, p->X);
  ngs_fe_sq(B, p->Y);
  ngs_fe_sq(C, p->Z);
  ngs_fe_add(C, C, C);
  ngs_fe_neg(D, A);
  ngs_fe_add(t, p->X, p->Y);
  ngs_fe_sq(t, t);
  ngs_fe_sub(t, t, A);
  ngs_fe_sub(E, t, B);
  ngs_fe_add(G, D, B);
  ngs_fe_sub(F, G, C);
  ngs_fe_sub(H, D, B);
  ngs_fe_mul(r->X, E, F);
  ngs_fe_mul(r->Y, G, H);
  ngs_fe_mul(r->T, E, H);
  ngs_fe_mul(r->Z, F, G);
}

/* Recover x from y and a sign bit; returns 0 on success. */
static int ngs_ed_recover_x(const ngs_ed_ctx *ctx, ngs_fe x, const ngs_fe y, int sign) {
  /* xx = (y^2 - 1) / (d y^2 + 1); x = xx^((p+3)/8), corrected by I. */
  static const uint8_t e_p38[32] = {   /* (p+3)/8 = 2^252 - 2 */
    0xfe, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x0f
  };
  ngs_fe y2, u, v, xx, x2;
  ngs_fe_sq(y2, y);
  ngs_fe_1(u); ngs_fe_sub(u, y2, u);
  ngs_fe_mul(v, y2, ctx->d); ngs_fe_1(xx); ngs_fe_add(v, v, xx);
  ngs_fe_invert(v, v);
  ngs_fe_mul(xx, u, v);
  ngs_fe_pow(x, xx, e_p38);
  ngs_fe_sq(x2, x);
  if (!ngs_fe_eq(x2, xx)) {
    ngs_fe_mul(x, x, ctx->I);
    ngs_fe_sq(x2, x);
    if (!ngs_fe_eq(x2, xx)) return -1;
  }
  {
    uint8_t xb[32];
    ngs_fe_tobytes(xb, x);
    if ((xb[0] & 1) != (uint8_t)sign) {
      if (ngs_fe_iszero(x)) return -1;   /* x = 0 with sign 1 is invalid (RFC 8032) */
      ngs_fe_neg(x, x);
    }
  }
  return 0;
}

static int ngs_ge_frombytes(const ngs_ed_ctx *ctx, ngs_ge_p3 *p, const uint8_t s[32]) {
  uint8_t yb[32];
  int sign;
  memcpy(yb, s, 32);
  sign = (yb[31] >> 7) & 1;
  yb[31] &= 0x7F;
  ngs_fe_frombytes(p->Y, yb);
  if (ngs_ed_recover_x(ctx, p->X, p->Y, sign) != 0) return -1;
  ngs_fe_1(p->Z);
  ngs_fe_mul(p->T, p->X, p->Y);
  return 0;
}

static void ngs_ge_tobytes(const ngs_ge_p3 *p, uint8_t s[32]) {
  ngs_fe zinv, x, y;
  ngs_fe_invert(zinv, p->Z);
  ngs_fe_mul(x, p->X, zinv);
  ngs_fe_mul(y, p->Y, zinv);
  ngs_fe_tobytes(s, y);
  {
    uint8_t xb[32];
    ngs_fe_tobytes(xb, x);
    s[31] |= (uint8_t)((xb[0] & 1) << 7);
  }
}

static void ngs_ed_ctx_init(ngs_ed_ctx *ctx) {
  ngs_fe t, inv;
  int i;
  /* d = -121665 / 121666 */
  ngs_fe_set_u32(t, 121666);
  ngs_fe_invert(inv, t);
  ngs_fe_set_u32(t, 121665);
  ngs_fe_mul(ctx->d, t, inv);
  ngs_fe_neg(ctx->d, ctx->d);
  ngs_fe_add(ctx->d2, ctx->d, ctx->d);
  /* I = 2^((p-1)/4); (p-1)/4 = 2^253 - 5 */
  {
    static const uint8_t e[32] = {
      0xfb, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
      0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff,
      0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x1f
    };
    ngs_fe_set_u32(t, 2);
    ngs_fe_pow(ctx->I, t, e);
  }
  /* base point: y = 4/5, x even */
  ngs_fe_set_u32(t, 5);
  ngs_fe_invert(inv, t);
  ngs_fe_set_u32(ctx->B.Y, 4);
  ngs_fe_mul(ctx->B.Y, ctx->B.Y, inv);
  (void)ngs_ed_recover_x(ctx, ctx->B.X, ctx->B.Y, 0);
  ngs_fe_1(ctx->B.Z);
  ngs_fe_mul(ctx->B.T, ctx->B.X, ctx->B.Y);
  /* table of B*1..B*15 */
  {
    ngs_ge_p3 acc;
    ngs_ge_cached bc;
    ngs_ge_to_cached(ctx, &bc, &ctx->B);
    ngs_ge_p3_identity(&acc);
    for (i = 0; i < 15; i++) {
      ngs_ge_p3 nxt;
      ngs_ge_add(&nxt, &acc, &bc);
      acc = nxt;
      ngs_ge_to_cached(ctx, &ctx->Btab[i], &acc);
    }
  }
}

/* out = scalar * B, scalar any 32-byte little-endian value. */
static void ngs_ge_scalarmult_base(const ngs_ed_ctx *ctx, ngs_ge_p3 *out, const uint8_t scalar[32]) {
  ngs_ge_p3 r;
  int nib, i;
  ngs_ge_p3_identity(&r);
  for (nib = 63; nib >= 0; nib--) {
    int digit;
    for (i = 0; i < 4; i++) ngs_ge_double(&r, &r);
    digit = (nib & 1) ? (scalar[nib >> 1] >> 4) & 0xF : scalar[nib >> 1] & 0xF;
    if (digit) {
      ngs_ge_p3 t;
      ngs_ge_add(&t, &r, &ctx->Btab[digit - 1]);
      r = t;
    }
  }
  *out = r;
}

/* out = scalar * p (variable point), scalar any 32-byte little-endian value. */
static void ngs_ge_scalarmult(const ngs_ed_ctx *ctx, ngs_ge_p3 *out,
                              const ngs_ge_p3 *p, const uint8_t scalar[32]) {
  ngs_ge_cached pc;
  ngs_ge_p3 r;
  int bit;
  ngs_ge_to_cached(ctx, &pc, p);
  ngs_ge_p3_identity(&r);
  for (bit = 255; bit >= 0; bit--) {
    ngs_ge_double(&r, &r);
    if ((scalar[bit >> 3] >> (bit & 7)) & 1) {
      ngs_ge_p3 t;
      ngs_ge_add(&t, &r, &pc);
      r = t;
    }
  }
  *out = r;
}

static int ngs_ge_eq(const ngs_ge_p3 *a, const ngs_ge_p3 *b) {
  ngs_fe x1, x2, y1, y2;
  ngs_fe_mul(x1, a->X, b->Z);
  ngs_fe_mul(x2, b->X, a->Z);
  ngs_fe_mul(y1, a->Y, b->Z);
  ngs_fe_mul(y2, b->Y, a->Z);
  return ngs_fe_eq(x1, x2) && ngs_fe_eq(y1, y2);
}

/* Scalar arithmetic mod L: bitwise reduction, obviously correct, not fast. */
static void ngs_sc_reduce_wide(uint32_t r[8], const uint32_t *in, size_t n_in) {
  uint32_t L[8], rem[9];
  size_t total_bits = n_in * 32, bi;
  int i;
  for (i = 0; i < 8; i++) {
    L[i] = (uint32_t)NGS_ED_L[4 * i] | ((uint32_t)NGS_ED_L[4 * i + 1] << 8) |
           ((uint32_t)NGS_ED_L[4 * i + 2] << 16) | ((uint32_t)NGS_ED_L[4 * i + 3] << 24);
  }
  for (i = 0; i < 9; i++) rem[i] = 0;
  for (bi = total_bits; bi-- > 0; ) {
    uint32_t carry = (in[bi >> 5] >> (bi & 31)) & 1u;
    for (i = 0; i < 9; i++) {
      uint32_t nc = rem[i] >> 31;
      rem[i] = (rem[i] << 1) | carry;
      carry = nc;
    }
    /* if rem >= L (as 256-bit value in rem[0..7], rem[8] overflow limb) */
    {
      int ge = 0, k;
      if (rem[8]) ge = 1;
      else {
        ge = 1;
        for (k = 7; k >= 0; k--) {
          if (rem[k] > L[k]) { ge = 1; break; }
          if (rem[k] < L[k]) { ge = 0; break; }
        }
      }
      if (ge) {
        uint64_t borrow = 0;
        for (k = 0; k < 8; k++) {
          uint64_t v = (uint64_t)rem[k] - L[k] - borrow;
          rem[k] = (uint32_t)v;
          borrow = (v >> 63) & 1u;
        }
        rem[8] = (uint32_t)((uint64_t)rem[8] - borrow);
      }
    }
  }
  for (i = 0; i < 8; i++) r[i] = rem[i];
}

static void ngs_sc_store(uint8_t out[32], const uint32_t limbs[8]) {
  int i;
  for (i = 0; i < 8; i++) ngs_store32le(out + 4 * i, limbs[i]);
}
static void ngs_sc_load(uint32_t limbs[8], const uint8_t in[32]) {
  int i;
  for (i = 0; i < 8; i++) ngs_load32le(in + 4 * i, &limbs[i]);
}

static void ngs_sc_reduce64(uint8_t out[32], const uint8_t in[64]) {
  uint32_t limbs[16], r[8];
  int i;
  for (i = 0; i < 16; i++) ngs_load32le(in + 4 * i, &limbs[i]);
  ngs_sc_reduce_wide(r, limbs, 16);
  ngs_sc_store(out, r);
}

/* s = (a*b + c) mod L */
static void ngs_sc_muladd(uint8_t s[32], const uint8_t a[32], const uint8_t b[32], const uint8_t c[32]) {
  uint32_t al[8], bl[8], cl[8], prod[16], r[8];
  int i, j;
  ngs_sc_load(al, a); ngs_sc_load(bl, b); ngs_sc_load(cl, c);
  for (i = 0; i < 16; i++) prod[i] = 0;
  for (i = 0; i < 8; i++) {
    uint64_t carry = 0;
    for (j = 0; j < 8; j++) {
      uint64_t v = (uint64_t)al[i] * bl[j] + prod[i + j] + carry;
      prod[i + j] = (uint32_t)v;
      carry = v >> 32;
    }
    prod[i + 8] = (uint32_t)carry;
  }
  {
    uint64_t carry = 0;
    for (i = 0; i < 8; i++) {
      uint64_t v = (uint64_t)prod[i] + cl[i] + carry;
      prod[i] = (uint32_t)v;
      carry = v >> 32;
    }
    i = 8;
    while (carry && i < 16) {
      uint64_t v = (uint64_t)prod[i] + carry;
      prod[i] = (uint32_t)v;
      carry = v >> 32;
      i++;
    }
  }
  ngs_sc_reduce_wide(r, prod, 16);
  ngs_sc_store(s, r);
}

static int ngs_sc_is_lt_L(const uint8_t s[32]) {
  int i;
  for (i = 31; i >= 0; i--) {
    if (s[i] < NGS_ED_L[i]) return 1;
    if (s[i] > NGS_ED_L[i]) return 0;
  }
  return 0;   /* equal to L is not < L */
}

static void ngs_ed25519_pubkey(const ngs_ed_ctx *ctx, const uint8_t seed[32], uint8_t pub[32]) {
  uint8_t h[64], a[32];
  ngs_ge_p3 A;
  ngs_sha512(seed, 32, h);
  memcpy(a, h, 32);
  a[0] &= 248; a[31] &= 63; a[31] |= 64;
  ngs_ge_scalarmult_base(ctx, &A, a);
  ngs_ge_tobytes(&A, pub);
  memset(h, 0, sizeof h); memset(a, 0, sizeof a);
}

static void ngs_ed25519_sign(const ngs_ed_ctx *ctx, const uint8_t seed[32],
                             const uint8_t *msg, size_t msg_len, uint8_t sig[64]) {
  uint8_t h[64], a[32], pub[32], rhash[64], r[32], khash[64], k[32];
  ngs_ge_p3 R;
  ngs_sha512_ctx c;
  ngs_sha512(seed, 32, h);
  memcpy(a, h, 32);
  a[0] &= 248; a[31] &= 63; a[31] |= 64;
  ngs_ed25519_pubkey(ctx, seed, pub);
  ngs_sha512_init(&c);
  ngs_sha512_update(&c, h + 32, 32);
  if (msg_len > 0) ngs_sha512_update(&c, msg, msg_len);
  ngs_sha512_final(&c, rhash);
  ngs_sc_reduce64(r, rhash);
  ngs_ge_scalarmult_base(ctx, &R, r);
  ngs_ge_tobytes(&R, sig);
  ngs_sha512_init(&c);
  ngs_sha512_update(&c, sig, 32);
  ngs_sha512_update(&c, pub, 32);
  if (msg_len > 0) ngs_sha512_update(&c, msg, msg_len);
  ngs_sha512_final(&c, khash);
  ngs_sc_reduce64(k, khash);
  ngs_sc_muladd(sig + 32, k, a, r);
  memset(h, 0, sizeof h); memset(a, 0, sizeof a);
  memset(rhash, 0, sizeof rhash); memset(r, 0, sizeof r);
  memset(khash, 0, sizeof khash); memset(k, 0, sizeof k);
}

/* Returns 1 if the signature is valid, 0 otherwise. */
static int ngs_ed25519_verify(const ngs_ed_ctx *ctx, const uint8_t pub[32],
                              const uint8_t *msg, size_t msg_len, const uint8_t sig[64]) {
  ngs_ge_p3 A, R, sB, kA, rhs;
  uint8_t khash[64], k[32];
  ngs_sha512_ctx c;
  ngs_ge_cached rc;
  ngs_ge_p3 t;
  if (!ngs_sc_is_lt_L(sig + 32)) return 0;
  if (ngs_ge_frombytes(ctx, &A, pub) != 0) return 0;
  if (ngs_ge_frombytes(ctx, &R, sig) != 0) return 0;
  ngs_sha512_init(&c);
  ngs_sha512_update(&c, sig, 32);
  ngs_sha512_update(&c, pub, 32);
  if (msg_len > 0) ngs_sha512_update(&c, msg, msg_len);
  ngs_sha512_final(&c, khash);
  ngs_sc_reduce64(k, khash);
  ngs_ge_scalarmult_base(ctx, &sB, sig + 32);
  ngs_ge_scalarmult(ctx, &kA, &A, k);
  ngs_ge_to_cached(ctx, &rc, &R);
  ngs_ge_add(&t, &kA, &rc);
  rhs = t;
  return ngs_ge_eq(&sB, &rhs);
}

/* ======================================================================
** 4. Canonical CBOR (RFC 8949 deterministic encoding): shortest-form
** heads, definite lengths, map keys in strictly increasing order.
** The encoder appends to a growable buffer; the decoder is a strict
** cursor used for fact payloads and checkpoints.
** ==================================================================== */
typedef struct { uint8_t *p; size_t len, cap; int oom; } ngs_buf;

static void ngs_buf_free(ngs_buf *b) { free(b->p); b->p = NULL; b->len = b->cap = 0; }

static int ngs_buf_reserve(ngs_buf *b, size_t extra) {
  size_t need, ncap;
  uint8_t *np;
  if (b->oom) return -1;
  if (extra > SIZE_MAX - b->len) { b->oom = 1; return -1; }
  need = b->len + extra;
  if (need <= b->cap) return 0;
  ncap = b->cap ? b->cap : 256;
  while (ncap < need) {
    if (ncap > SIZE_MAX / 2) { ncap = need; break; }
    ncap *= 2;
  }
  np = (uint8_t *)realloc(b->p, ncap);
  if (!np) { b->oom = 1; return -1; }
  b->p = np; b->cap = ncap;
  return 0;
}
static void ngs_buf_put(ngs_buf *b, const void *data, size_t len) {
  if (ngs_buf_reserve(b, len) != 0) return;
  if (len > 0) memcpy(b->p + b->len, data, len);
  b->len += len;
}
static void ngs_buf_u8(ngs_buf *b, uint8_t v) { ngs_buf_put(b, &v, 1); }

static void ngs_cbor_head(ngs_buf *b, unsigned major, uint64_t val) {
  uint8_t mt = (uint8_t)(major << 5);
  if (val < 24) {
    ngs_buf_u8(b, (uint8_t)(mt | (uint8_t)val));
  } else if (val <= 0xFFu) {
    ngs_buf_u8(b, (uint8_t)(mt | 24)); ngs_buf_u8(b, (uint8_t)val);
  } else if (val <= 0xFFFFu) {
    ngs_buf_u8(b, (uint8_t)(mt | 25));
    ngs_buf_u8(b, (uint8_t)(val >> 8)); ngs_buf_u8(b, (uint8_t)val);
  } else if (val <= 0xFFFFFFFFu) {
    ngs_buf_u8(b, (uint8_t)(mt | 26));
    ngs_buf_u8(b, (uint8_t)(val >> 24)); ngs_buf_u8(b, (uint8_t)(val >> 16));
    ngs_buf_u8(b, (uint8_t)(val >> 8)); ngs_buf_u8(b, (uint8_t)val);
  } else {
    int i;
    ngs_buf_u8(b, (uint8_t)(mt | 27));
    for (i = 7; i >= 0; i--) ngs_buf_u8(b, (uint8_t)(val >> (8 * i)));
  }
}
static void ngs_cbor_uint(ngs_buf *b, uint64_t v) { ngs_cbor_head(b, 0, v); }
static void ngs_cbor_int(ngs_buf *b, int64_t v) {
  if (v >= 0) ngs_cbor_head(b, 0, (uint64_t)v);
  else ngs_cbor_head(b, 1, (uint64_t)(-(v + 1)));
}
static void ngs_cbor_bytes(ngs_buf *b, const uint8_t *p, size_t n) {
  ngs_cbor_head(b, 2, n);
  if (n > 0) ngs_buf_put(b, p, n);
}
static void ngs_cbor_text(ngs_buf *b, const char *p, size_t n) {
  ngs_cbor_head(b, 3, n);
  if (n > 0) ngs_buf_put(b, p, n);
}
static void ngs_cbor_array(ngs_buf *b, uint64_t n) { ngs_cbor_head(b, 4, n); }
static void ngs_cbor_map(ngs_buf *b, uint64_t n) { ngs_cbor_head(b, 5, n); }

/* Strict decoder cursor. */
typedef struct { const uint8_t *p; size_t len, pos; } ngs_dec;

static int ngs_dec_head(ngs_dec *d, unsigned *major, uint64_t *val) {
  uint8_t ib, ai;
  uint64_t v;
  int i, nbytes;
  if (d->pos >= d->len) return -1;
  ib = d->p[d->pos++];
  *major = ib >> 5;
  ai = ib & 0x1F;
  if (ai < 24) { *val = ai; return 0; }
  if (ai == 24) nbytes = 1;
  else if (ai == 25) nbytes = 2;
  else if (ai == 26) nbytes = 4;
  else if (ai == 27) nbytes = 8;
  else return -1;                      /* indefinite / reserved: not canonical */
  if (d->len - d->pos < (size_t)nbytes) return -1;
  v = 0;
  for (i = 0; i < nbytes; i++) v = (v << 8) | d->p[d->pos++];
  /* shortest form: the value must not fit in a smaller head */
  if (nbytes == 1 && v < 24) return -1;
  if (nbytes == 2 && v <= 0xFFu) return -1;
  if (nbytes == 4 && v <= 0xFFFFu) return -1;
  if (nbytes == 8 && v <= 0xFFFFFFFFull) return -1;
  *val = v;
  return 0;
}
static int ngs_dec_uint(ngs_dec *d, uint64_t *v) {
  unsigned m;
  if (ngs_dec_head(d, &m, v) != 0 || m != 0) return -1;
  return 0;
}
static int ngs_dec_int(ngs_dec *d, int64_t *v) {
  unsigned m;
  uint64_t u;
  if (ngs_dec_head(d, &m, &u) != 0) return -1;
  if (m == 0) {
    if (u > (uint64_t)INT64_MAX) return -1;
    *v = (int64_t)u;
    return 0;
  }
  if (m == 1) {
    if (u > (uint64_t)INT64_MAX) return -1;   /* -1-u must stay >= INT64_MIN */
    *v = -1 - (int64_t)u;
    return 0;
  }
  return -1;
}
static int ngs_dec_bytes(ngs_dec *d, const uint8_t **p, size_t *n) {
  unsigned m;
  uint64_t v;
  if (ngs_dec_head(d, &m, &v) != 0 || m != 2) return -1;
  if (v > d->len - d->pos) return -1;
  *p = d->p + d->pos;
  *n = (size_t)v;
  d->pos += (size_t)v;
  return 0;
}
static int ngs_dec_text(ngs_dec *d, const char **p, size_t *n) {
  unsigned m;
  uint64_t v;
  if (ngs_dec_head(d, &m, &v) != 0 || m != 3) return -1;
  if (v > d->len - d->pos) return -1;
  *p = (const char *)(d->p + d->pos);
  *n = (size_t)v;
  d->pos += (size_t)v;
  return 0;
}
static int ngs_dec_array(ngs_dec *d, uint64_t *n) {
  unsigned m;
  if (ngs_dec_head(d, &m, n) != 0 || m != 4) return -1;
  return 0;
}
static int ngs_dec_map(ngs_dec *d, uint64_t *n) {
  unsigned m;
  if (ngs_dec_head(d, &m, n) != 0 || m != 5) return -1;
  return 0;
}

/* Skip one well-formed canonical item (any major type), depth-limited. */
static int ngs_dec_skip(ngs_dec *d, int depth) {
  unsigned m;
  uint64_t v, i;
  if (depth > 16) return -1;
  if (ngs_dec_head(d, &m, &v) != 0) return -1;
  switch (m) {
    case 0: case 1:
      return 0;
    case 2: case 3:
      if (v > d->len - d->pos) return -1;
      d->pos += (size_t)v;
      return 0;
    case 4:
      for (i = 0; i < v; i++) if (ngs_dec_skip(d, depth + 1) != 0) return -1;
      return 0;
    case 5: {
      const uint8_t *prev_key = NULL;
      size_t prev_len = 0;
      for (i = 0; i < v; i++) {
        size_t kstart = d->pos;
        size_t klen;
        if (ngs_dec_skip(d, depth + 1) != 0) return -1;
        klen = d->pos - kstart;
        if (prev_key) {
          /* canonical order: encoded keys strictly increasing (bytewise,
          ** shorter-first on a common prefix) */
          size_t minl = prev_len < klen ? prev_len : klen;
          int cmp = minl ? memcmp(prev_key, d->p + kstart, minl) : 0;
          if (cmp > 0 || (cmp == 0 && prev_len >= klen)) return -1;
        }
        prev_key = d->p + kstart;
        prev_len = klen;
        if (ngs_dec_skip(d, depth + 1) != 0) return -1;
      }
      return 0;
    }
    case 6:
      return ngs_dec_skip(d, depth + 1);
    case 7:
      return 0;   /* simple/float heads already consumed by dec_head */
    default:
      return -1;
  }
}

/* Validate a caller-supplied attrs blob: exactly one canonical CBOR item. */
static int ngs_cbor_validate(const uint8_t *p, size_t n) {
  ngs_dec d;
  d.p = p; d.len = n; d.pos = 0;
  if (n == 0) return -1;
  if (ngs_dec_skip(&d, 0) != 0) return -1;
  return d.pos == d.len ? 0 : -1;
}

/* ======================================================================
** 5. Platform layer (POSIX). SPEC 15: every OS capability the ISO C core
** cannot express lives here and only here: positional file I/O with
** 64-bit offsets, durability, atomic rename, the single-writer lock,
** entropy, a monotonic clock, mutexes, aligned allocation, secret wipe.
** ==================================================================== */
#include <unistd.h>
#include <fcntl.h>
#include <sys/file.h>
#include <errno.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <pthread.h>
#ifdef __linux__
#include <sys/random.h>
#endif

typedef struct { pthread_mutex_t m; } ngs_mutex;
static void ngs_mutex_init(ngs_mutex *x) { pthread_mutex_init(&x->m, NULL); }
static void ngs_mutex_lock(ngs_mutex *x) { pthread_mutex_lock(&x->m); }
static void ngs_mutex_unlock(ngs_mutex *x) { pthread_mutex_unlock(&x->m); }
static void ngs_mutex_destroy(ngs_mutex *x) { pthread_mutex_destroy(&x->m); }

/* Returned engine objects are single 16-aligned allocations (ngs.h "Align"). */
static void *ngs_alloc16(size_t n) {
  void *p = NULL;
  if (n == 0) n = 16;
  if (posix_memalign(&p, NGS_ALIGN_MAX, n) != 0) return NULL;
  return p;
}

static void ngs_wipe(void *p, size_t n) {
  volatile uint8_t *v = (volatile uint8_t *)p;
  size_t i;
  for (i = 0; i < n; i++) v[i] = 0;
}

static int64_t ngs_wall_us(void) {
  struct timespec ts;
  if (timespec_get(&ts, TIME_UTC) == 0) return 0;
  return (int64_t)ts.tv_sec * 1000000 + (int64_t)(ts.tv_nsec / 1000);
}
static int64_t ngs_mono_us(void) {
  struct timespec ts;
  if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
  return (int64_t)ts.tv_sec * 1000000 + (int64_t)(ts.tv_nsec / 1000);
}

static int ngs_p_mkdir(const char *path) {
  if (mkdir(path, 0755) == 0) return 0;
  return errno == EEXIST ? 0 : -1;
}
static int ngs_p_exists(const char *path) {
  struct stat st;
  return stat(path, &st) == 0;
}
static int ngs_p_isdir(const char *path) {
  struct stat st;
  return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
}
/* flags: 0 = read-only, 1 = read/write (no create), 2 = read/write + create */
static int ngs_p_open(const char *path, int mode) {
  int fl;
  if (mode == 0) fl = O_RDONLY;
  else if (mode == 1) fl = O_RDWR;
  else fl = O_RDWR | O_CREAT;
  return open(path, fl | O_CLOEXEC, 0644);
}
static int ngs_p_open_key(const char *path) {   /* secret file: 0600 */
  return open(path, O_RDWR | O_CREAT | O_CLOEXEC, 0600);
}
static void ngs_p_close(int fd) { if (fd >= 0) close(fd); }

static int ngs_p_pread_full(int fd, uint8_t *buf, size_t len, uint64_t off) {
  size_t got = 0;
  while (got < len) {
    ssize_t r = pread(fd, buf + got, len - got, (off_t)(off + got));
    if (r < 0) { if (errno == EINTR) continue; return -1; }
    if (r == 0) return -1;                       /* short file */
    got += (size_t)r;
  }
  return 0;
}
static int ngs_p_pwrite_full(int fd, const uint8_t *buf, size_t len, uint64_t off) {
  size_t put = 0;
  while (put < len) {
    ssize_t r = pwrite(fd, buf + put, len - put, (off_t)(off + put));
    if (r < 0) { if (errno == EINTR) continue; return -1; }
    put += (size_t)r;
  }
  return 0;
}
static int ngs_p_datasync(int fd) { return fdatasync(fd) == 0 ? 0 : -1; }
static int ngs_p_truncate(int fd, uint64_t len) { return ftruncate(fd, (off_t)len) == 0 ? 0 : -1; }
static int64_t ngs_p_size(int fd) {
  struct stat st;
  if (fstat(fd, &st) != 0) return -1;
  return (int64_t)st.st_size;
}
static int ngs_p_lock_nb(int fd) {   /* 0 = locked, 1 = busy, -1 = error */
  /* flock(2), not fcntl F_SETLK: POSIX fcntl locks are per-process and do
  ** not exclude a second handle opened by the SAME process, which would
  ** corrupt the log just as surely as a second process. flock locks are
  ** per open-file-description, so they exclude both, and release on close. */
  if (flock(fd, LOCK_EX | LOCK_NB) == 0) return 0;
  return (errno == EACCES || errno == EAGAIN || errno == EWOULDBLOCK) ? 1 : -1;
}
static int ngs_p_fsync_dir(const char *path) {
  int fd = open(path, O_RDONLY | O_CLOEXEC);
  int rc;
  if (fd < 0) return -1;
  rc = fsync(fd);
  close(fd);
  return rc == 0 ? 0 : -1;
}
static int ngs_p_random(uint8_t *buf, size_t len) {
#ifdef __linux__
  size_t got = 0;
  while (got < len) {
    ssize_t r = getrandom(buf + got, len - got, 0);
    if (r < 0) { if (errno == EINTR) continue; break; }
    got += (size_t)r;
  }
  if (got == len) return 0;
#endif
  {
    int fd = open("/dev/urandom", O_RDONLY | O_CLOEXEC);
    size_t got = 0;
    if (fd < 0) return -1;
    while (got < len) {
      ssize_t r = read(fd, buf + got, len - got);
      if (r < 0) { if (errno == EINTR) continue; close(fd); return -1; }
      if (r == 0) { close(fd); return -1; }
      got += (size_t)r;
    }
    close(fd);
    return 0;
  }
}

/* ======================================================================
** 6. The engine.
**
** On-disk (SPEC 3, M1 subset): <dir>/LOCK, <dir>/node.key (32-byte seed),
** <dir>/log/000001.seg, 000002.seg, ... Segment and record formats are
** exactly SPEC 3.1: 64-byte header (magic "NGSSEG\0\0", u16 format=1,
** u16 flags, u64 first_seq, 32-byte writer pubkey, u32 header_crc32c over
** the first 52 bytes, zero padding), then records
** u32 len | u8 type | payload | u32 crc32c(type || payload).
** MANIFEST/HEAD and SSTables are M2; recovery in M1 is a log replay.
**
** Fact payload: canonical CBOR map, integer keys in ascending order:
**   0 ns(text) 1 kind(uint) 2 writer(bytes32) 3 seq(uint) 4 prev(bytes32)
**   5 t_event(int) 6 t_record(int) 7 valid_from(int) 8 title(text)
**   9 body(text) 10 tags(array of text) 11 attrs(bytes: raw canonical CBOR)
**   12 schema(uint) 13 sig(bytes64)
** fact_id = BLAKE3 of the same map with key 9 replaced by
** body_hash(bytes32 = BLAKE3(body)) and key 13 omitted (SPEC 13.3:
** fact_id hashes over body_hash, not the body). sig = Ed25519 over fact_id.
** ==================================================================== */
#define NGS_REC_FACT 1
#define NGS_SEG_HDR 64
#define NGS_MAX_BODY (1024u * 1024u)
#define NGS_MAX_TAGS 1024u
#define NGS_MAX_TAG_LEN 4096u
#define NGS_DEFAULT_SEG_BYTES (64ull * 1024ull * 1024ull)

typedef struct {
  ngs_id id;
  char *ns; size_t ns_len;
  int32_t kind;
  ngs_pubkey writer;
  uint64_t seq;
  ngs_id prev;
  ngs_time t_event, t_record, valid_from;
  char *title; size_t title_len;
  uint8_t *body; size_t body_len;
  char **tags; size_t *tag_lens; size_t n_tags;
  uint8_t *attrs; size_t attrs_len;
  uint16_t schema;
  uint8_t sig[64];
} ngs_ent;

typedef struct { char *ns; size_t ns_len; uint64_t seq; ngs_id id; } ngs_nshead;

struct ngs {
  int rc_state;                 /* sticky open error; 0 = healthy */
  char err[256];
  ngs_mutex mu;
  int readonly;
  int have_secret;
  uint8_t seed[32];
  ngs_pubkey pub;
  int pub_known;
  ngs_ed_ctx ed;
  char *dir;
  int lock_fd;
  int seg_fd;                   /* append fd for the last segment (-1 none) */
  uint32_t cur_seg;
  uint64_t seg_size;            /* valid bytes in the current segment */
  uint64_t segment_bytes;
  int dirty;
  int corrupt;                  /* corruption found at open (preserved on disk) */
  ngs_ent *ents; size_t n_ents, cap_ents;
  uint32_t *htab; size_t hcap, hcount;
  ngs_nshead *heads; size_t n_heads, cap_heads;
  ngs_time last_trecord;
  uint64_t log_bytes;
};

static _Thread_local char ngs_tls_err[256];

static int ngs_set_err(ngs *db, int rc, const char *msg) {
  if (db) snprintf(db->err, sizeof db->err, "%s", msg);
  return rc;
}

static char *ngs_strdup_n(const char *p, size_t n) {
  char *s = (char *)malloc(n + 1);
  if (!s) return NULL;
  if (n > 0) memcpy(s, p, n);
  s[n] = '\0';
  return s;
}

static void ngs_ent_clear(ngs_ent *e) {
  size_t i;
  free(e->ns);
  free(e->title);
  free(e->body);
  if (e->tags) { for (i = 0; i < e->n_tags; i++) free(e->tags[i]); free(e->tags); }
  free(e->tag_lens);
  free(e->attrs);
  memset(e, 0, sizeof *e);
}
static void ngs_ents_free(ngs_ent *ents, size_t n) {
  size_t i;
  if (ents) { for (i = 0; i < n; i++) ngs_ent_clear(&ents[i]); free(ents); }
}
static void ngs_heads_free(ngs_nshead *heads, size_t n) {
  size_t i;
  if (heads) { for (i = 0; i < n; i++) free(heads[i].ns); free(heads); }
}

/* --- fact map encoding --- */
static void ngs_encode_fact(ngs_buf *b, int for_id,
                            const char *ns, size_t ns_len, int32_t kind,
                            const uint8_t *writer, uint64_t seq, const uint8_t *prev,
                            ngs_time t_event, ngs_time t_record, ngs_time valid_from,
                            const char *title, size_t title_len,
                            const uint8_t *body, size_t body_len,
                            const uint8_t *body_hash,
                            const ngs_str *tags, size_t n_tags,
                            const uint8_t *attrs, size_t attrs_len,
                            uint16_t schema, const uint8_t *sig) {
  size_t i;
  ngs_cbor_map(b, for_id ? 13 : 14);
  ngs_cbor_uint(b, 0); ngs_cbor_text(b, ns, ns_len);
  ngs_cbor_uint(b, 1); ngs_cbor_uint(b, (uint64_t)kind);
  ngs_cbor_uint(b, 2); ngs_cbor_bytes(b, writer, 32);
  ngs_cbor_uint(b, 3); ngs_cbor_uint(b, seq);
  ngs_cbor_uint(b, 4); ngs_cbor_bytes(b, prev, 32);
  ngs_cbor_uint(b, 5); ngs_cbor_int(b, t_event);
  ngs_cbor_uint(b, 6); ngs_cbor_int(b, t_record);
  ngs_cbor_uint(b, 7); ngs_cbor_int(b, valid_from);
  ngs_cbor_uint(b, 8); ngs_cbor_text(b, title, title_len);
  ngs_cbor_uint(b, 9);
  if (for_id) ngs_cbor_bytes(b, body_hash, 32);
  else ngs_cbor_text(b, (const char *)body, body_len);
  ngs_cbor_uint(b, 10); ngs_cbor_array(b, n_tags);
  for (i = 0; i < n_tags; i++) ngs_cbor_text(b, tags[i].p, tags[i].n);
  ngs_cbor_uint(b, 11); ngs_cbor_bytes(b, attrs, attrs_len);
  ngs_cbor_uint(b, 12); ngs_cbor_uint(b, schema);
  if (!for_id) { ngs_cbor_uint(b, 13); ngs_cbor_bytes(b, sig, 64); }
}

static void ngs_fact_id(const char *ns, size_t ns_len, int32_t kind,
                        const uint8_t *writer, uint64_t seq, const uint8_t *prev,
                        ngs_time t_event, ngs_time t_record, ngs_time valid_from,
                        const char *title, size_t title_len,
                        const uint8_t *body, size_t body_len,
                        const ngs_str *tags, size_t n_tags,
                        const uint8_t *attrs, size_t attrs_len,
                        uint16_t schema, uint8_t out_id[32], int *oom) {
  uint8_t bh[32];
  ngs_buf b;
  memset(&b, 0, sizeof b);
  ngs_blake3_hash(body, body_len, bh);
  ngs_encode_fact(&b, 1, ns, ns_len, kind, writer, seq, prev, t_event, t_record,
                  valid_from, title, title_len, body, body_len, bh, tags, n_tags,
                  attrs, attrs_len, schema, NULL);
  if (b.oom) { *oom = 1; ngs_buf_free(&b); return; }
  ngs_blake3_hash(b.p, b.len, out_id);
  ngs_buf_free(&b);
}

/* --- fact payload parsing (strict) --- */
typedef struct {
  const char *ns; size_t ns_len;
  int32_t kind;
  const uint8_t *writer;
  uint64_t seq;
  const uint8_t *prev;
  ngs_time t_event, t_record, valid_from;
  const char *title; size_t title_len;
  const uint8_t *body; size_t body_len;
  const uint8_t *tags_blob; uint64_t n_tags;   /* tags re-walked by caller */
  const uint8_t *attrs; size_t attrs_len;
  uint16_t schema;
  const uint8_t *sig;
} ngs_parsed;

static int ngs_parse_fact(const uint8_t *p, size_t n, ngs_parsed *out) {
  ngs_dec d;
  uint64_t nent, i;
  int64_t last_key = -1;
  unsigned seen = 0;
  d.p = p; d.len = n; d.pos = 0;
  memset(out, 0, sizeof *out);
  if (ngs_dec_map(&d, &nent) != 0 || nent != 14) return -1;
  for (i = 0; i < nent; i++) {
    uint64_t key;
    if (ngs_dec_uint(&d, &key) != 0) return -1;
    if ((int64_t)key <= last_key || key > 13) return -1;
    last_key = (int64_t)key;
    seen |= 1u << key;
    switch (key) {
      case 0: if (ngs_dec_text(&d, &out->ns, &out->ns_len) != 0) return -1; break;
      case 1: { uint64_t v; if (ngs_dec_uint(&d, &v) != 0 || v > 3) return -1; out->kind = (int32_t)v; } break;
      case 2: { size_t m; if (ngs_dec_bytes(&d, &out->writer, &m) != 0 || m != 32) return -1; } break;
      case 3: if (ngs_dec_uint(&d, &out->seq) != 0) return -1; break;
      case 4: { size_t m; if (ngs_dec_bytes(&d, &out->prev, &m) != 0 || m != 32) return -1; } break;
      case 5: if (ngs_dec_int(&d, &out->t_event) != 0) return -1; break;
      case 6: if (ngs_dec_int(&d, &out->t_record) != 0) return -1; break;
      case 7: if (ngs_dec_int(&d, &out->valid_from) != 0) return -1; break;
      case 8: if (ngs_dec_text(&d, &out->title, &out->title_len) != 0) return -1; break;
      case 9: { const char *bp; if (ngs_dec_text(&d, &bp, &out->body_len) != 0) return -1; out->body = (const uint8_t *)bp; } break;
      case 10: {
        uint64_t nt, j;
        out->tags_blob = d.p + d.pos;
        if (ngs_dec_array(&d, &nt) != 0 || nt > NGS_MAX_TAGS) return -1;
        out->n_tags = nt;
        for (j = 0; j < nt; j++) {
          const char *tp; size_t tn;
          if (ngs_dec_text(&d, &tp, &tn) != 0 || tn > NGS_MAX_TAG_LEN) return -1;
        }
      } break;
      case 11: if (ngs_dec_bytes(&d, &out->attrs, &out->attrs_len) != 0) return -1; break;
      case 12: { uint64_t v; if (ngs_dec_uint(&d, &v) != 0 || v > 0xFFFFu) return -1; out->schema = (uint16_t)v; } break;
      case 13: { size_t m; if (ngs_dec_bytes(&d, &out->sig, &m) != 0 || m != 64) return -1; } break;
      default: return -1;
    }
  }
  if (seen != 0x3FFFu) return -1;
  if (d.pos != d.len) return -1;
  if (out->ns_len == 0 || out->ns_len > NGS_MAX_NS_LEN) return -1;
  if (out->kind < 1) return -1;
  if (out->title_len > NGS_MAX_TITLE_LEN) return -1;
  if (out->body_len > NGS_MAX_BODY) return -1;
  if (out->attrs_len > NGS_MAX_ATTRS_LEN) return -1;
  return 0;
}

/* Copy a parsed fact into an owned ent. The payload buffer stays alive
** during the call; tags are re-walked from tags_blob. */
static int ngs_ent_from_parsed(ngs_ent *e, const ngs_parsed *pa) {
  uint64_t j;
  memset(e, 0, sizeof *e);
  e->ns = ngs_strdup_n(pa->ns, pa->ns_len);
  e->title = ngs_strdup_n(pa->title, pa->title_len);
  e->body = (uint8_t *)malloc(pa->body_len ? pa->body_len : 1);
  e->attrs = (uint8_t *)malloc(pa->attrs_len ? pa->attrs_len : 1);
  if (!e->ns || !e->title || !e->body || !e->attrs) goto oom;
  e->ns_len = pa->ns_len;
  e->kind = pa->kind;
  memcpy(e->writer.b, pa->writer, 32);
  e->seq = pa->seq;
  memcpy(e->prev.b, pa->prev, 32);
  e->t_event = pa->t_event; e->t_record = pa->t_record; e->valid_from = pa->valid_from;
  e->title_len = pa->title_len;
  if (pa->body_len > 0) memcpy(e->body, pa->body, pa->body_len);
  e->body_len = pa->body_len;
  if (pa->attrs_len > 0) memcpy(e->attrs, pa->attrs, pa->attrs_len);
  e->attrs_len = pa->attrs_len;
  e->schema = pa->schema;
  memcpy(e->sig, pa->sig, 64);
  e->n_tags = (size_t)pa->n_tags;
  if (pa->n_tags > 0) {
    ngs_dec td;
    td.p = pa->tags_blob; td.len = SIZE_MAX; td.pos = 0;
    {
      uint64_t nt;
      if (ngs_dec_array(&td, &nt) != 0) goto oom;
    }
    e->tags = (char **)calloc(pa->n_tags, sizeof(char *));
    e->tag_lens = (size_t *)calloc(pa->n_tags, sizeof(size_t));
    if (!e->tags || !e->tag_lens) goto oom;
    for (j = 0; j < pa->n_tags; j++) {
      const char *tp; size_t tn;
      /* bounds were validated by ngs_parse_fact; the walk is in-bounds */
      td.len = (size_t)-1;
      if (ngs_dec_text(&td, &tp, &tn) != 0) goto oom;
      e->tags[j] = ngs_strdup_n(tp, tn);
      if (!e->tags[j]) goto oom;
      e->tag_lens[j] = tn;
    }
  }
  return 0;
oom:
  ngs_ent_clear(e);
  return -1;
}

/* --- replay result --- */
typedef struct {
  ngs_ent *ents; size_t n_ents, cap_ents;
  ngs_nshead *heads; size_t n_heads, cap_heads;
  uint64_t log_bytes;
  int corrupt;
  uint32_t corrupt_seg;
  int torn;                    /* torn tail truncated/ignored at last segment */
  uint32_t last_seg;           /* highest segment number found (0 = none) */
  uint64_t last_seg_valid;     /* valid bytes in the last segment */
  ngs_time last_trecord;
  uint8_t adopted_pub[32];
  int adopted_pub_set;
} ngs_replay_out;

static ngs_nshead *ngs_head_find(ngs_nshead *heads, size_t n, const char *ns, size_t ns_len) {
  size_t i;
  for (i = 0; i < n; i++) {
    if (heads[i].ns_len == ns_len && memcmp(heads[i].ns, ns, ns_len) == 0) return &heads[i];
  }
  return NULL;
}

/* Takes ownership of *e only on success (return 0). */
static int ngs_replay_push(ngs_replay_out *ro, ngs_ent *e, const char *ns, size_t ns_len) {
  ngs_nshead *h;
  h = ngs_head_find(ro->heads, ro->n_heads, ns, ns_len);
  if (!h) {
    if (ro->n_heads == ro->cap_heads) {
      size_t ncap = ro->cap_heads ? ro->cap_heads * 2 : 16;
      ngs_nshead *nh = (ngs_nshead *)realloc(ro->heads, ncap * sizeof(ngs_nshead));
      if (!nh) return -1;
      ro->heads = nh; ro->cap_heads = ncap;
    }
    h = &ro->heads[ro->n_heads];
    h->ns = ngs_strdup_n(ns, ns_len);
    if (!h->ns) return -1;
    h->ns_len = ns_len;
    ro->n_heads++;
  }
  if (ro->n_ents == ro->cap_ents) {
    size_t ncap = ro->cap_ents ? ro->cap_ents * 2 : 64;
    ngs_ent *ne = (ngs_ent *)realloc(ro->ents, ncap * sizeof(ngs_ent));
    if (!ne) return -1;
    ro->ents = ne; ro->cap_ents = ncap;
  }
  h->seq = e->seq;
  h->id = e->id;
  ro->ents[ro->n_ents++] = *e;
  return 0;
}

/* Replay every segment under db->dir. verify_sigs=1 also checks Ed25519
** signatures (ngs_verify); open uses 0 (structural recovery). Facts are
** returned in ro->ents with recomputed ids; chain breaks, bad CRCs and
** parse failures set ro->corrupt and stop the replay at that record.
** A short tail at the end of the last segment sets ro->torn instead. */
static int ngs_replay_log(ngs *db, int verify_sigs, ngs_replay_out *ro) {
  char path[4096];
  uint32_t segno;
  memset(ro, 0, sizeof *ro);
  for (segno = 1; ; segno++) {
    int fd, is_last_probe;
    int64_t fsize;
    uint8_t hdr[NGS_SEG_HDR];
    uint64_t pos, valid_end;
    int seg_corrupt = 0, seg_torn = 0;
    ngs_buf recbuf;
    snprintf(path, sizeof path, "%s/log/%06u.seg", db->dir, (unsigned)segno);
    if (!ngs_p_exists(path)) break;
    fd = ngs_p_open(path, 0);
    if (fd < 0) return NGS_IOERR;
    /* is there a next segment? then this one is not last */
    {
      char npath[4096];
      snprintf(npath, sizeof npath, "%s/log/%06u.seg", db->dir, (unsigned)(segno + 1));
      is_last_probe = !ngs_p_exists(npath);
    }
    fsize = ngs_p_size(fd);
    if (fsize < 0) { ngs_p_close(fd); return NGS_IOERR; }
    memset(&recbuf, 0, sizeof recbuf);
    valid_end = 0;
    if (fsize == 0) {
      /* crash between create and header write: only ok as the last segment */
      if (!is_last_probe) seg_corrupt = 1;
      else seg_torn = 1;
      ngs_p_close(fd);
      ro->last_seg = segno;
      ro->last_seg_valid = 0;
      if (seg_corrupt) { ro->corrupt = 1; ro->corrupt_seg = segno; }
      if (seg_torn) ro->torn = 1;
      ngs_buf_free(&recbuf);
      break;
    }
    if (fsize < NGS_SEG_HDR) {
      ngs_p_close(fd);
      if (is_last_probe) { ro->torn = 1; ro->last_seg = segno; ro->last_seg_valid = 0; }
      else { ro->corrupt = 1; ro->corrupt_seg = segno; }
      ngs_buf_free(&recbuf);
      break;
    }
    if (ngs_p_pread_full(fd, hdr, NGS_SEG_HDR, 0) != 0) { ngs_p_close(fd); return NGS_IOERR; }
    if (memcmp(hdr, "NGSSEG\0\0", 8) != 0 || hdr[8] != NGS_FORMAT || hdr[9] != 0) {
      seg_corrupt = 1;
    } else {
      uint32_t stored, calc;
      memcpy(&stored, hdr + 52, 4);
      stored = (uint32_t)hdr[52] | ((uint32_t)hdr[53] << 8) | ((uint32_t)hdr[54] << 16) | ((uint32_t)hdr[55] << 24);
      calc = ngs_crc32c(hdr, 52, 0);
      if (stored != calc) seg_corrupt = 1;
      else {
        /* writer adoption / check */
        if (db->pub_known) {
          if (memcmp(hdr + 20, db->pub.b, 32) != 0) seg_corrupt = 1;
        } else {
          memcpy(ro->adopted_pub, hdr + 20, 32);
          ro->adopted_pub_set = 1;
          memcpy(db->pub.b, hdr + 20, 32);
          db->pub_known = 1;
        }
      }
    }
    if (seg_corrupt) {
      ngs_p_close(fd);
      ro->corrupt = 1; ro->corrupt_seg = segno;
      ro->last_seg = segno; ro->last_seg_valid = 0;
      ngs_buf_free(&recbuf);
      break;
    }
    valid_end = NGS_SEG_HDR;
    pos = NGS_SEG_HDR;
    while (pos < (uint64_t)fsize) {
      uint8_t prefix[5];
      uint32_t len;
      uint8_t type;
      uint64_t rec_total;
      if ((uint64_t)fsize - pos < 9) { seg_torn = 1; break; }   /* cannot hold a record */
      if (ngs_p_pread_full(fd, prefix, 5, pos) != 0) { ngs_p_close(fd); ngs_buf_free(&recbuf); return NGS_IOERR; }
      len = (uint32_t)prefix[0] | ((uint32_t)prefix[1] << 8) | ((uint32_t)prefix[2] << 16) | ((uint32_t)prefix[3] << 24);
      type = prefix[4];
      rec_total = 5ull + len + 4ull;
      if (rec_total > (uint64_t)fsize - pos) { seg_torn = 1; break; }  /* incomplete record */
      if (len > db->segment_bytes) { seg_corrupt = 1; break; }         /* impossible length */
      if (ngs_buf_reserve(&recbuf, len + 4) != 0) { ngs_p_close(fd); ngs_buf_free(&recbuf); return NGS_NOMEM; }
      if (ngs_p_pread_full(fd, recbuf.p, len + 4, pos + 5) != 0) { ngs_p_close(fd); ngs_buf_free(&recbuf); return NGS_IOERR; }
      {
        uint32_t stored = (uint32_t)recbuf.p[len] | ((uint32_t)recbuf.p[len + 1] << 8) |
                          ((uint32_t)recbuf.p[len + 2] << 16) | ((uint32_t)recbuf.p[len + 3] << 24);
        uint32_t calc = ngs_crc32c(&type, 1, 0);
        calc = ngs_crc32c(recbuf.p, len, calc);
        if (stored != calc) { seg_corrupt = 1; break; }
      }
      if (type == NGS_REC_FACT) {
        ngs_parsed pa;
        ngs_ent e;
        ngs_nshead *h;
        uint8_t id[32];
        int oom = 0;
        ngs_str *tagv = NULL;
        if (ngs_parse_fact(recbuf.p, len, &pa) != 0) { seg_corrupt = 1; break; }
        if (ngs_ent_from_parsed(&e, &pa) != 0) { ngs_p_close(fd); ngs_buf_free(&recbuf); return NGS_NOMEM; }
        /* recompute the id from the owned copy */
        if (e.n_tags > 0) {
          size_t j;
          tagv = (ngs_str *)malloc(e.n_tags * sizeof(ngs_str));
          if (!tagv) { ngs_ent_clear(&e); ngs_p_close(fd); ngs_buf_free(&recbuf); return NGS_NOMEM; }
          for (j = 0; j < e.n_tags; j++) { tagv[j].p = e.tags[j]; tagv[j].n = e.tag_lens[j]; }
        }
        ngs_fact_id(e.ns, e.ns_len, e.kind, e.writer.b, e.seq, e.prev.b,
                    e.t_event, e.t_record, e.valid_from, e.title, e.title_len,
                    e.body, e.body_len, tagv, e.n_tags, e.attrs, e.attrs_len,
                    e.schema, id, &oom);
        free(tagv);
        if (oom) { ngs_ent_clear(&e); ngs_p_close(fd); ngs_buf_free(&recbuf); return NGS_NOMEM; }
        memcpy(e.id.b, id, 32);
        /* chain check: gapless seq and prev linkage per (writer, ns) */
        h = ngs_head_find(ro->heads, ro->n_heads, e.ns, e.ns_len);
        if (h) {
          if (e.seq != h->seq + 1 || memcmp(e.prev.b, h->id.b, 32) != 0) {
            ngs_ent_clear(&e); seg_corrupt = 1; break;
          }
        } else {
          static const uint8_t zero32[32] = { 0 };
          if (e.seq != 1 || memcmp(e.prev.b, zero32, 32) != 0) {
            ngs_ent_clear(&e); seg_corrupt = 1; break;
          }
        }
        if (memcmp(e.writer.b, db->pub.b, 32) != 0 && db->pub_known) {
          ngs_ent_clear(&e); seg_corrupt = 1; break;
        }
        if (verify_sigs) {
          if (!ngs_ed25519_verify(&db->ed, e.writer.b, e.id.b, 32, e.sig)) {
            ngs_ent_clear(&e); seg_corrupt = 1; break;
          }
        }
        if (ngs_replay_push(ro, &e, e.ns, e.ns_len) != 0) {
          ngs_ent_clear(&e); ngs_p_close(fd); ngs_buf_free(&recbuf); return NGS_NOMEM;
        }
        if (e.t_record > ro->last_trecord) ro->last_trecord = e.t_record;
      } else if (type <= 5) {
        /* PAD / INVALIDATION / LINK / REDACTION / CHECKPOINT_REF: part of
        ** the log, not materialized as facts in M1. */
      } else {
        seg_corrupt = 1; break;
      }
      ro->log_bytes += rec_total;
      pos += rec_total;
      valid_end = pos;
    }
    ngs_p_close(fd);
    ngs_buf_free(&recbuf);
    ro->last_seg = segno;
    ro->last_seg_valid = valid_end;
    if (seg_corrupt) { ro->corrupt = 1; ro->corrupt_seg = segno; break; }
    if (seg_torn) {
      if (is_last_probe) ro->torn = 1;
      else { ro->corrupt = 1; ro->corrupt_seg = segno; }
      break;
    }
    if (!is_last_probe) continue;
    break;
  }
  return NGS_OK;
}

static void ngs_replay_out_free(ngs_replay_out *ro) {
  ngs_ents_free(ro->ents, ro->n_ents);
  ngs_heads_free(ro->heads, ro->n_heads);
  memset(ro, 0, sizeof *ro);
}

/* Merkle root over fact ids in log order; odd leaf promoted unchanged. */
static void ngs_merkle(const ngs_ent *ents, size_t n, uint8_t out[32]) {
  uint8_t *level, *next;
  size_t count = n, i;
  if (n == 0) { ngs_blake3_hash((const uint8_t *)"", 0, out); return; }
  level = (uint8_t *)malloc(count * 32);
  if (!level) { ngs_blake3_hash((const uint8_t *)"", 0, out); return; }
  for (i = 0; i < n; i++) memcpy(level + i * 32, ents[i].id.b, 32);
  while (count > 1) {
    size_t pairs = count / 2, j;
    next = (uint8_t *)malloc(((pairs + (count & 1)) * 32));
    if (!next) { free(level); ngs_blake3_hash((const uint8_t *)"", 0, out); return; }
    for (j = 0; j < pairs; j++) {
      uint8_t both[64];
      memcpy(both, level + j * 64, 64);
      ngs_blake3_hash(both, 64, next + j * 32);
    }
    if (count & 1) memcpy(next + pairs * 32, level + (count - 1) * 32, 32);
    free(level);
    level = next;
    count = pairs + (count & 1);
  }
  memcpy(out, level, 32);
  free(level);
}

/* --- small API helpers --- */
int ngs_libversion_number(void) { return NGS_VERSION_NUMBER; }
const char *ngs_libversion(void) { return NGS_VERSION; }

const char *ngs_errstr(int rc) {
  switch (rc) {
    case NGS_OK: return "ngs: no error";
    case NGS_ERROR: return "ngs: generic error";
    case NGS_NOTFOUND: return "ngs: not found";
    case NGS_BUSY: return "ngs: writer lock held by another process";
    case NGS_CORRUPT: return "ngs: corruption detected (CRC, chain or signature)";
    case NGS_NOGRANT: return "ngs: no write grant for this namespace";
    case NGS_MISMATCH: return "ngs: embedding tag mismatch";
    case NGS_QUARANTINED: return "ngs: segment quarantined";
    case NGS_NOMEM: return "ngs: out of memory";
    case NGS_IOERR: return "ngs: I/O error";
    case NGS_MISUSE: return "ngs: API misuse";
    case NGS_TOOBIG: return "ngs: item over the configured limit";
    default: return "ngs: unknown error";
  }
}

void ngs_free(void *p) { free(p); }

const char *ngs_errmsg(ngs *db) {
  if (!db) return "ngs: no handle";
  snprintf(ngs_tls_err, sizeof ngs_tls_err, "%s", db->err);
  return ngs_tls_err;
}

static void ngs_seg_path(char *buf, size_t cap, const char *dir, uint32_t segno) {
  snprintf(buf, cap, "%s/log/%06u.seg", dir, (unsigned)segno);
}

static int ngs_seg_write_header(int fd, const ngs_pubkey *pub, uint64_t first_seq) {
  uint8_t hdr[NGS_SEG_HDR];
  uint32_t crc;
  memset(hdr, 0, sizeof hdr);
  memcpy(hdr, "NGSSEG\0\0", 8);
  hdr[8] = NGS_FORMAT;
  ngs_store64le(hdr + 12, first_seq);
  memcpy(hdr + 20, pub->b, 32);
  crc = ngs_crc32c(hdr, 52, 0);
  ngs_store32le(hdr + 52, crc);
  if (ngs_p_pwrite_full(fd, hdr, NGS_SEG_HDR, 0) != 0) return -1;
  return ngs_p_datasync(fd);
}

static int ngs_seg_create(ngs *db, uint32_t segno, uint64_t first_seq, int *fd_out) {
  char path[4096];
  int fd;
  ngs_seg_path(path, sizeof path, db->dir, segno);
  fd = ngs_p_open(path, 2);
  if (fd < 0) return -1;
  if (ngs_p_truncate(fd, 0) != 0 || ngs_seg_write_header(fd, &db->pub, first_seq) != 0) {
    ngs_p_close(fd);
    return -1;
  }
  {
    char logdir[4096];
    snprintf(logdir, sizeof logdir, "%s/log", db->dir);
    (void)ngs_p_fsync_dir(logdir);
  }
  *fd_out = fd;
  return 0;
}

/* hash index over ents (open addressing, stores ent index + 1) */
static uint64_t ngs_id_hash(const ngs_id *id) {
  uint64_t x = ngs_load64le(id->b);
  x *= 0x9E3779B97F4A7C15ull;
  x ^= x >> 29;
  return x;
}
static int ngs_htab_rebuild(ngs *db, size_t want) {
  size_t cap = 64, i;
  uint32_t *nt;
  while (cap < want) cap *= 2;
  nt = (uint32_t *)calloc(cap, sizeof(uint32_t));
  if (!nt) return -1;
  for (i = 0; i < db->n_ents; i++) {
    size_t slot = (size_t)(ngs_id_hash(&db->ents[i].id) & (uint64_t)(cap - 1));
    while (nt[slot]) slot = (slot + 1) & (cap - 1);
    nt[slot] = (uint32_t)(i + 1);
  }
  free(db->htab);
  db->htab = nt;
  db->hcap = cap;
  db->hcount = db->n_ents;
  return 0;
}
static long ngs_htab_find(ngs *db, const ngs_id *id) {
  size_t slot;
  if (!db->htab || db->hcap == 0) return -1;
  slot = (size_t)(ngs_id_hash(id) & (uint64_t)(db->hcap - 1));
  while (db->htab[slot]) {
    size_t idx = db->htab[slot] - 1;
    if (memcmp(db->ents[idx].id.b, id->b, 32) == 0) return (long)idx;
    slot = (slot + 1) & (db->hcap - 1);
  }
  return -1;
}
static int ngs_htab_insert(ngs *db, size_t idx) {
  size_t slot;
  if ((db->hcount + 1) * 2 >= db->hcap) {
    if (ngs_htab_rebuild(db, (db->n_ents + 1) * 2) != 0) return -1;
    /* rebuild already inserted every ent including idx */
    return 0;
  }
  slot = (size_t)(ngs_id_hash(&db->ents[idx].id) & (uint64_t)(db->hcap - 1));
  while (db->htab[slot]) slot = (slot + 1) & (db->hcap - 1);
  db->htab[slot] = (uint32_t)(idx + 1);
  db->hcount++;
  return 0;
}

static ngs_nshead *ngs_db_head(ngs *db, const char *ns, size_t ns_len, int create) {
  ngs_nshead *h = ngs_head_find(db->heads, db->n_heads, ns, ns_len);
  if (h || !create) return h;
  if (db->n_heads == db->cap_heads) {
    size_t ncap = db->cap_heads ? db->cap_heads * 2 : 16;
    ngs_nshead *nh = (ngs_nshead *)realloc(db->heads, ncap * sizeof(ngs_nshead));
    if (!nh) return NULL;
    db->heads = nh; db->cap_heads = ncap;
  }
  h = &db->heads[db->n_heads];
  h->ns = ngs_strdup_n(ns, ns_len);
  if (!h->ns) return NULL;
  h->ns_len = ns_len;
  h->seq = 0;
  memset(&h->id, 0, sizeof h->id);
  db->n_heads++;
  return h;
}

#define NGS_OPT_OK(o, f) ((o)->size >= (uint32_t)(offsetof(ngs_open_opts, f) + sizeof(((ngs_open_opts *)0)->f)))
#define NGS_FIN_OK(i, f) ((i)->size >= (uint32_t)(offsetof(ngs_fact_in, f) + sizeof(((ngs_fact_in *)0)->f)))
#define NGS_SCAN_OK(o, f) ((o)->size >= (uint32_t)(offsetof(ngs_scan_opts, f) + sizeof(((ngs_scan_opts *)0)->f)))

int ngs_open(const char *dir, const ngs_open_opts *opts, ngs **out) {
  ngs *db;
  ngs_open_opts o;
  ngs_replay_out ro;
  int rc;
  if (!out) return NGS_MISUSE;
  *out = NULL;
  if (!dir || !dir[0]) return NGS_MISUSE;
  if (strlen(dir) > 3900) return NGS_TOOBIG;
  db = (ngs *)ngs_alloc16(sizeof(ngs));
  if (!db) return NGS_NOMEM;
  memset(db, 0, sizeof *db);
  *out = db;
  db->lock_fd = -1;
  db->seg_fd = -1;
  db->segment_bytes = NGS_DEFAULT_SEG_BYTES;
  ngs_mutex_init(&db->mu);
  ngs_crc_init();
  ngs_ed_ctx_init(&db->ed);
  (void)ngs_mono_us();   /* platform clock is live (deadlines arrive in M4) */

  /* options, read-what-fits per the ABI contract */
  {
    ngs_open_opts def = NGS_OPEN_OPTS_INIT;
    o = def;
    if (opts) {
      if (opts->size < 4) { rc = ngs_set_err(db, NGS_MISUSE, "ngs_open: opts.size too small"); goto fail; }
      if (NGS_OPT_OK(opts, flags)) o.flags = opts->flags;
      if (NGS_OPT_OK(opts, node_seckey)) o.node_seckey = opts->node_seckey;
      if (NGS_OPT_OK(opts, segment_bytes)) o.segment_bytes = opts->segment_bytes;
      if (NGS_OPT_OK(opts, group_commit_ms)) o.group_commit_ms = opts->group_commit_ms;
      if (NGS_OPT_OK(opts, checkpoint_every)) o.checkpoint_every = opts->checkpoint_every;
      if (NGS_OPT_OK(opts, shard_vec_split)) o.shard_vec_split = opts->shard_vec_split;
      if (NGS_OPT_OK(opts, root_pubkey)) o.root_pubkey = opts->root_pubkey;
    }
  }
  db->readonly = (o.flags & NGS_OPEN_READONLY) ? 1 : 0;
  if (o.segment_bytes >= 1024 * 1024) db->segment_bytes = o.segment_bytes;

  db->dir = ngs_strdup_n(dir, strlen(dir));
  if (!db->dir) { rc = NGS_NOMEM; goto fail; }

  if (!ngs_p_isdir(dir)) {
    if (db->readonly) { rc = ngs_set_err(db, NGS_ERROR, "ngs_open: no such directory"); goto fail; }
    if (ngs_p_mkdir(dir) != 0) { rc = ngs_set_err(db, NGS_IOERR, "ngs_open: cannot create directory"); goto fail; }
    (void)ngs_p_fsync_dir(".");
  }
  {
    char logdir[4096];
    snprintf(logdir, sizeof logdir, "%s/log", dir);
    if (!ngs_p_isdir(logdir)) {
      if (db->readonly) { rc = ngs_set_err(db, NGS_ERROR, "ngs_open: not an ngs directory (no log/)"); goto fail; }
      if (ngs_p_mkdir(logdir) != 0) { rc = ngs_set_err(db, NGS_IOERR, "ngs_open: cannot create log directory"); goto fail; }
    }
  }

  /* single-writer lock */
  if (!db->readonly) {
    char lockpath[4096];
    int lrc;
    snprintf(lockpath, sizeof lockpath, "%s/LOCK", dir);
    db->lock_fd = ngs_p_open(lockpath, 2);
    if (db->lock_fd < 0) { rc = ngs_set_err(db, NGS_IOERR, "ngs_open: cannot open LOCK"); goto fail; }
    lrc = ngs_p_lock_nb(db->lock_fd);
    if (lrc == 1) { rc = ngs_set_err(db, NGS_BUSY, "ngs_open: writer lock held by another process"); goto fail; }
    if (lrc != 0) { rc = ngs_set_err(db, NGS_IOERR, "ngs_open: lock failed"); goto fail; }
  }

  /* node key: supplied > stored > generated (CREATE, read/write only) */
  if (o.node_seckey) {
    memcpy(db->seed, o.node_seckey, 32);
    db->have_secret = 1;
  } else {
    char keypath[4096];
    snprintf(keypath, sizeof keypath, "%s/node.key", dir);
    if (ngs_p_exists(keypath)) {
      int fd = ngs_p_open(keypath, 0);
      uint8_t buf[64];
      int64_t sz;
      if (fd < 0) { rc = ngs_set_err(db, NGS_IOERR, "ngs_open: cannot read node.key"); goto fail; }
      sz = ngs_p_size(fd);
      if (sz != 32 || ngs_p_pread_full(fd, buf, 32, 0) != 0) {
        ngs_p_close(fd);
        rc = ngs_set_err(db, NGS_CORRUPT, "ngs_open: node.key is not a 32-byte seed");
        goto fail;
      }
      ngs_p_close(fd);
      memcpy(db->seed, buf, 32);
      db->have_secret = 1;
    } else if ((o.flags & NGS_OPEN_CREATE) && !db->readonly) {
      int fd;
      if (ngs_p_random(db->seed, 32) != 0) { rc = ngs_set_err(db, NGS_IOERR, "ngs_open: entropy failure"); goto fail; }
      fd = ngs_p_open_key(keypath);
      if (fd < 0 || ngs_p_pwrite_full(fd, db->seed, 32, 0) != 0 || ngs_p_datasync(fd) != 0) {
        if (fd >= 0) ngs_p_close(fd);
        rc = ngs_set_err(db, NGS_IOERR, "ngs_open: cannot write node.key");
        goto fail;
      }
      ngs_p_close(fd);
      (void)ngs_p_fsync_dir(dir);
      db->have_secret = 1;
    } else if (!db->readonly) {
      rc = ngs_set_err(db, NGS_ERROR, "ngs_open: no node key (supply node_seckey or NGS_OPEN_CREATE)");
      goto fail;
    }
  }
  if (db->have_secret) {
    ngs_ed25519_pubkey(&db->ed, db->seed, db->pub.b);
    db->pub_known = 1;
  }

  /* replay / recovery */
  rc = ngs_replay_log(db, 0, &ro);
  if (rc != NGS_OK) { ngs_replay_out_free(&ro); rc = ngs_set_err(db, rc, "ngs_open: log replay failed"); goto fail; }
  db->ents = ro.ents; db->n_ents = ro.n_ents; db->cap_ents = ro.cap_ents;
  db->heads = ro.heads; db->n_heads = ro.n_heads; db->cap_heads = ro.cap_heads;
  db->log_bytes = ro.log_bytes;
  db->last_trecord = ro.last_trecord;
  db->corrupt = ro.corrupt;
  if (ro.adopted_pub_set && !db->pub_known) {
    memcpy(db->pub.b, ro.adopted_pub, 32);
    db->pub_known = 1;
  }
  if (ngs_htab_rebuild(db, db->n_ents * 2 + 2) != 0) { rc = NGS_NOMEM; goto fail; }

  if (!db->readonly) {
    if (ro.last_seg == 0) {
      if (ngs_seg_create(db, 1, 0, &db->seg_fd) != 0) { rc = ngs_set_err(db, NGS_IOERR, "ngs_open: cannot create segment 1"); goto fail; }
      db->cur_seg = 1;
      db->seg_size = NGS_SEG_HDR;
    } else {
      char path[4096];
      db->cur_seg = ro.last_seg;
      ngs_seg_path(path, sizeof path, db->dir, db->cur_seg);
      db->seg_fd = ngs_p_open(path, 1);
      if (db->seg_fd < 0) { rc = ngs_set_err(db, NGS_IOERR, "ngs_open: cannot open last segment for append"); goto fail; }
      db->seg_size = ro.last_seg_valid;
      if (ro.torn && !ro.corrupt) {
        /* torn tail: truncate crash debris (SPEC 3.1) */
        if (ngs_p_truncate(db->seg_fd, ro.last_seg_valid) != 0) {
          rc = ngs_set_err(db, NGS_IOERR, "ngs_open: cannot truncate torn tail");
          goto fail;
        }
        if (ro.last_seg_valid == 0) {
          /* header never landed: rewrite it */
          if (ngs_seg_write_header(db->seg_fd, &db->pub, 0) != 0) {
            rc = ngs_set_err(db, NGS_IOERR, "ngs_open: cannot rewrite segment header");
            goto fail;
          }
          db->seg_size = NGS_SEG_HDR;
        }
        (void)ngs_p_datasync(db->seg_fd);
      }
      /* if ro.corrupt: the evidence stays on disk untouched; appends refuse */
    }
  }
  if (db->corrupt) {
    snprintf(db->err, sizeof db->err,
             "ngs_open: corruption in segment %u; valid prefix is readable, writes refuse, ngs_verify reports NGS_CORRUPT",
             (unsigned)ro.corrupt_seg);
  }
  return NGS_OK;

fail:
  db->rc_state = rc;
  if (!db->err[0]) snprintf(db->err, sizeof db->err, "%s", ngs_errstr(rc));
  return rc;
}

int ngs_close(ngs *db) {
  if (!db) return NGS_MISUSE;
  if (!db->rc_state && !db->readonly && db->seg_fd >= 0 && db->dirty) {
    (void)ngs_p_datasync(db->seg_fd);
  }
  if (db->seg_fd >= 0) ngs_p_close(db->seg_fd);
  if (db->lock_fd >= 0) ngs_p_close(db->lock_fd);
  ngs_ents_free(db->ents, db->n_ents);
  ngs_heads_free(db->heads, db->n_heads);
  free(db->htab);
  free(db->dir);
  ngs_wipe(db->seed, sizeof db->seed);
  ngs_mutex_destroy(&db->mu);
  free(db);
  return NGS_OK;
}

int ngs_node_pubkey(ngs *db, ngs_pubkey *out) {
  if (!db || !out) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  if (!db->pub_known) return ngs_set_err(db, NGS_ERROR, "ngs_node_pubkey: no writer key known");
  *out = db->pub;
  return NGS_OK;
}

int ngs_flush(ngs *db) {
  int rc = NGS_OK;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  ngs_mutex_lock(&db->mu);
  if (!db->readonly && db->seg_fd >= 0 && db->dirty) {
    if (ngs_p_datasync(db->seg_fd) != 0) rc = ngs_set_err(db, NGS_IOERR, "ngs_flush: fdatasync failed");
    else db->dirty = 0;
  }
  ngs_mutex_unlock(&db->mu);
  return rc;
}

/* --- writing --- */
typedef struct {
  const char *ns; size_t ns_len;
  int32_t kind;
  ngs_time t_event, valid_from;
  const char *title; size_t title_len;
  const uint8_t *body; size_t body_len;
  const ngs_str *tags; size_t n_tags;
  const uint8_t *attrs; size_t attrs_len;
  uint16_t schema;
} ngs_prep;

static const uint8_t NGS_EMPTY_ATTRS[1] = { 0xA0 };   /* canonical empty map */

static int ngs_prepare(ngs *db, const ngs_fact_in *in, ngs_prep *p) {
  memset(p, 0, sizeof *p);
  if (!in) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: NULL fact_in");
  if (in->size < 4 || !NGS_FIN_OK(in, ns) || !NGS_FIN_OK(in, kind)) {
    return ngs_set_err(db, NGS_MISUSE, "ngs_remember: fact_in.size too small");
  }
  p->ns = in->ns.p; p->ns_len = in->ns.n;
  if (!p->ns && p->ns_len > 0) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: ns.p NULL with n > 0");
  if (p->ns_len == 0) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: empty namespace");
  if (p->ns_len > NGS_MAX_NS_LEN) return ngs_set_err(db, NGS_TOOBIG, "ngs_remember: namespace over 255 bytes");
  p->kind = in->kind;
  if (p->kind != NGS_EPISODIC && p->kind != NGS_SEMANTIC && p->kind != NGS_PROCEDURAL) {
    return ngs_set_err(db, NGS_MISUSE, "ngs_remember: kind must be EPISODIC, SEMANTIC or PROCEDURAL");
  }
  p->t_event = NGS_FIN_OK(in, t_event) ? in->t_event : NGS_TIME_NOW;
  if (p->t_event == NGS_TIME_NOW) p->t_event = ngs_wall_us();
  p->valid_from = NGS_FIN_OK(in, valid_from) ? in->valid_from : NGS_TIME_NOW;
  if (p->valid_from == NGS_TIME_NOW) p->valid_from = p->t_event;
  if (NGS_FIN_OK(in, title)) {
    p->title = in->title.p; p->title_len = in->title.n;
    if (!p->title && p->title_len > 0) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: title.p NULL with n > 0");
    if (p->title_len > NGS_MAX_TITLE_LEN) return ngs_set_err(db, NGS_TOOBIG, "ngs_remember: title over 1 KiB");
  }
  if (NGS_FIN_OK(in, body)) {
    p->body = (const uint8_t *)in->body.p; p->body_len = in->body.n;
    if (!p->body && p->body_len > 0) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: body.p NULL with n > 0");
    if (p->body_len > NGS_MAX_BODY) return ngs_set_err(db, NGS_TOOBIG, "ngs_remember: body over 1 MiB");
  }
  if (!p->title) { p->title = ""; p->title_len = 0; }
  if (!p->body) { p->body = (const uint8_t *)""; p->body_len = 0; }
  if (NGS_FIN_OK(in, tags) && NGS_FIN_OK(in, n_tags)) {
    size_t i;
    p->tags = in->tags; p->n_tags = in->n_tags;
    if (p->n_tags > 0 && !p->tags) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: tags NULL with n_tags > 0");
    if (p->n_tags > NGS_MAX_TAGS) return ngs_set_err(db, NGS_TOOBIG, "ngs_remember: too many tags");
    for (i = 0; i < p->n_tags; i++) {
      if (!p->tags[i].p && p->tags[i].n > 0) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: tag p NULL with n > 0");
      if (p->tags[i].n > NGS_MAX_TAG_LEN) return ngs_set_err(db, NGS_TOOBIG, "ngs_remember: tag over 4 KiB");
    }
  }
  if (NGS_FIN_OK(in, attrs_cbor) && NGS_FIN_OK(in, attrs_len)) {
    p->attrs = in->attrs_cbor; p->attrs_len = in->attrs_len;
    if (!p->attrs && p->attrs_len > 0) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: attrs NULL with len > 0");
    if (p->attrs_len > NGS_MAX_ATTRS_LEN) return ngs_set_err(db, NGS_TOOBIG, "ngs_remember: attrs over 64 KiB");
    if (p->attrs_len > 0 && ngs_cbor_validate(p->attrs, p->attrs_len) != 0) {
      return ngs_set_err(db, NGS_MISUSE, "ngs_remember: attrs is not canonical CBOR");
    }
  }
  if (p->attrs_len == 0) { p->attrs = NGS_EMPTY_ATTRS; p->attrs_len = 1; }
  if (NGS_FIN_OK(in, schema)) p->schema = in->schema;
  if (NGS_FIN_OK(in, supersedes) && in->supersedes) {
    return ngs_set_err(db, NGS_MISUSE, "ngs_remember: supersedes is M3 (invalidation view), not M1");
  }
  if (NGS_FIN_OK(in, salience0)) {
    if (!isfinite((double)in->salience0)) {
      return ngs_set_err(db, NGS_MISUSE, "ngs_remember: salience0 must be finite");
    }
    /* salience is derived state (SPEC 5.3), not part of the logged fact;
    ** M1 validates it and lets it go. */
  }
  if (NGS_FIN_OK(in, vecs) && NGS_FIN_OK(in, n_vecs) && in->n_vecs > 0) {
    size_t i;
    if (!in->vecs) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: vecs NULL with n_vecs > 0");
    for (i = 0; i < in->n_vecs; i++) {
      const ngs_vec *v = &in->vecs[i];
      uint32_t j;
      if (v->dim == 0 || v->dim > NGS_MAX_DIM) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: vec dim out of range");
      if (!v->v) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: vec data NULL");
      if (!v->model_id.p && v->model_id.n > 0) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: vec model_id NULL with n > 0");
      for (j = 0; j < v->dim; j++) {
        if (!isfinite((double)v->v[j])) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: vec component not finite");
      }
    }
    /* vectors live in indexes (SPEC 5.1), not in the fact record; M4. */
  }
  if (NGS_FIN_OK(in, n_token_counts) && in->n_token_counts > 0) {
    if (!NGS_FIN_OK(in, tokenizer_ids) || !NGS_FIN_OK(in, token_counts) ||
        !in->tokenizer_ids || !in->token_counts) {
      return ngs_set_err(db, NGS_MISUSE, "ngs_remember: token counts need tokenizer_ids and token_counts");
    }
    /* token accounting is recall-side (SPEC 5.4), M4. */
  }
  return NGS_OK;
}

/* Append one prepared fact. Caller holds db->mu. sync_now forces the
** fdatasync for this record; otherwise the caller syncs at the end. */
static int ngs_append_one(ngs *db, const ngs_prep *p, int sync_now, ngs_id *out_id) {
  ngs_nshead *head;
  uint64_t seq;
  uint8_t prev[32];
  ngs_time t_record, now;
  uint8_t id[32], sig[64];
  int oom = 0, rc;
  ngs_buf payload, rec;
  ngs_ent e;

  head = ngs_db_head(db, p->ns, p->ns_len, 1);
  if (!head) return ngs_set_err(db, NGS_NOMEM, "ngs_remember: out of memory");
  seq = head->seq + 1;
  memcpy(prev, head->id.b, 32);

  now = ngs_wall_us();
  t_record = now > db->last_trecord ? now : db->last_trecord + 1;

  ngs_fact_id(p->ns, p->ns_len, p->kind, db->pub.b, seq, prev,
              p->t_event, t_record, p->valid_from, p->title, p->title_len,
              p->body, p->body_len, p->tags, p->n_tags, p->attrs, p->attrs_len,
              p->schema, id, &oom);
  if (oom) return ngs_set_err(db, NGS_NOMEM, "ngs_remember: out of memory");
  ngs_ed25519_sign(&db->ed, db->seed, id, 32, sig);

  memset(&payload, 0, sizeof payload);
  ngs_encode_fact(&payload, 0, p->ns, p->ns_len, p->kind, db->pub.b, seq, prev,
                  p->t_event, t_record, p->valid_from, p->title, p->title_len,
                  p->body, p->body_len, NULL, p->tags, p->n_tags,
                  p->attrs, p->attrs_len, p->schema, sig);
  if (payload.oom) { ngs_buf_free(&payload); return ngs_set_err(db, NGS_NOMEM, "ngs_remember: out of memory"); }

  memset(&rec, 0, sizeof rec);
  {
    uint8_t hdr5[5];
    uint32_t crc;
    ngs_store32le(hdr5, (uint32_t)payload.len);
    hdr5[4] = NGS_REC_FACT;
    ngs_buf_put(&rec, hdr5, 5);
    ngs_buf_put(&rec, payload.p, payload.len);
    crc = ngs_crc32c(&hdr5[4], 1, 0);
    crc = ngs_crc32c(payload.p, payload.len, crc);
    {
      uint8_t cb[4];
      ngs_store32le(cb, crc);
      ngs_buf_put(&rec, cb, 4);
    }
  }
  ngs_buf_free(&payload);
  if (rec.oom) { ngs_buf_free(&rec); return ngs_set_err(db, NGS_NOMEM, "ngs_remember: out of memory"); }

  /* segment rollover */
  if (db->seg_fd < 0) { ngs_buf_free(&rec); return ngs_set_err(db, NGS_IOERR, "ngs_remember: no active segment"); }
  if (db->seg_size >= NGS_SEG_HDR && db->seg_size + rec.len > db->segment_bytes) {
    int nfd = -1;
    if (ngs_seg_create(db, db->cur_seg + 1, seq, &nfd) != 0) {
      ngs_buf_free(&rec);
      return ngs_set_err(db, NGS_IOERR, "ngs_remember: segment rollover failed");
    }
    ngs_p_close(db->seg_fd);
    db->seg_fd = nfd;
    db->cur_seg += 1;
    db->seg_size = NGS_SEG_HDR;
  }
  {
    size_t rec_len = rec.len;   /* ngs_buf_free zeroes len; capture it first */
    if (ngs_p_pwrite_full(db->seg_fd, rec.p, rec_len, db->seg_size) != 0) {
      ngs_buf_free(&rec);
      db->dirty = 1;
      return ngs_set_err(db, NGS_IOERR, "ngs_remember: write failed (torn tail will be truncated on open)");
    }
    ngs_buf_free(&rec);
    db->seg_size += rec_len;
    db->log_bytes += rec_len;
  }
  if (sync_now) {
    if (ngs_p_datasync(db->seg_fd) != 0) {
      db->dirty = 1;
      return ngs_set_err(db, NGS_IOERR, "ngs_remember: fdatasync failed");
    }
    db->dirty = 0;
  } else {
    db->dirty = 1;
  }

  /* in-memory index */
  memset(&e, 0, sizeof e);
  memcpy(e.id.b, id, 32);
  e.ns = ngs_strdup_n(p->ns, p->ns_len);
  e.title = ngs_strdup_n(p->title, p->title_len);
  e.body = (uint8_t *)malloc(p->body_len ? p->body_len : 1);
  e.attrs = (uint8_t *)malloc(p->attrs_len ? p->attrs_len : 1);
  if (!e.ns || !e.title || !e.body || !e.attrs) { ngs_ent_clear(&e); return ngs_set_err(db, NGS_NOMEM, "ngs_remember: out of memory"); }
  e.ns_len = p->ns_len;
  e.kind = p->kind;
  e.writer = db->pub;
  e.seq = seq;
  memcpy(e.prev.b, prev, 32);
  e.t_event = p->t_event; e.t_record = t_record; e.valid_from = p->valid_from;
  e.title_len = p->title_len;
  if (p->body_len > 0) memcpy(e.body, p->body, p->body_len);
  e.body_len = p->body_len;
  if (p->attrs_len > 0) memcpy(e.attrs, p->attrs, p->attrs_len);
  e.attrs_len = p->attrs_len;
  e.schema = p->schema;
  memcpy(e.sig, sig, 64);
  if (p->n_tags > 0) {
    size_t i;
    e.tags = (char **)calloc(p->n_tags, sizeof(char *));
    e.tag_lens = (size_t *)calloc(p->n_tags, sizeof(size_t));
    if (!e.tags || !e.tag_lens) { ngs_ent_clear(&e); return ngs_set_err(db, NGS_NOMEM, "ngs_remember: out of memory"); }
    e.n_tags = p->n_tags;
    for (i = 0; i < p->n_tags; i++) {
      e.tags[i] = ngs_strdup_n(p->tags[i].p, p->tags[i].n);
      if (!e.tags[i]) { ngs_ent_clear(&e); return ngs_set_err(db, NGS_NOMEM, "ngs_remember: out of memory"); }
      e.tag_lens[i] = p->tags[i].n;
    }
  }
  if (db->n_ents == db->cap_ents) {
    size_t ncap = db->cap_ents ? db->cap_ents * 2 : 64;
    ngs_ent *ne = (ngs_ent *)realloc(db->ents, ncap * sizeof(ngs_ent));
    if (!ne) { ngs_ent_clear(&e); return ngs_set_err(db, NGS_NOMEM, "ngs_remember: out of memory"); }
    db->ents = ne; db->cap_ents = ncap;
  }
  db->ents[db->n_ents] = e;
  db->n_ents++;
  if (ngs_htab_insert(db, db->n_ents - 1) != 0) {
    (void)ngs_htab_rebuild(db, db->n_ents * 2 + 2);
  }
  head = ngs_db_head(db, p->ns, p->ns_len, 0);
  if (head) { head->seq = seq; memcpy(head->id.b, id, 32); }
  db->last_trecord = t_record;
  if (out_id) memcpy(out_id->b, id, 32);
  rc = NGS_OK;
  return rc;
}

int ngs_remember(ngs *db, const ngs_fact_in *in, int32_t flags, ngs_id *out_id) {
  ngs_prep p;
  int rc;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  if (flags & ~NGS_WRITE_NO_SYNC) return ngs_set_err(db, NGS_MISUSE, "ngs_remember: unknown flags");
  ngs_mutex_lock(&db->mu);
  if (db->readonly) { ngs_mutex_unlock(&db->mu); return ngs_set_err(db, NGS_ERROR, "ngs_remember: read-only handle"); }
  if (db->corrupt) { ngs_mutex_unlock(&db->mu); return ngs_set_err(db, NGS_CORRUPT, "ngs_remember: store is corrupt; writes refuse"); }
  if (!db->have_secret) { ngs_mutex_unlock(&db->mu); return ngs_set_err(db, NGS_ERROR, "ngs_remember: no node key"); }
  rc = ngs_prepare(db, in, &p);
  if (rc == NGS_OK) rc = ngs_append_one(db, &p, !(flags & NGS_WRITE_NO_SYNC), out_id);
  ngs_mutex_unlock(&db->mu);
  return rc;
}

int ngs_remember_many(ngs *db, const ngs_fact_in *in, size_t n, int32_t flags, ngs_id *out_ids) {
  ngs_prep *preps;
  size_t i;
  int rc = NGS_OK;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  if (flags & ~NGS_WRITE_NO_SYNC) return ngs_set_err(db, NGS_MISUSE, "ngs_remember_many: unknown flags");
  if (n == 0) return NGS_OK;
  if (!in) return ngs_set_err(db, NGS_MISUSE, "ngs_remember_many: NULL array");
  if (n > (size_t)1 << 20) return ngs_set_err(db, NGS_TOOBIG, "ngs_remember_many: batch too large");
  ngs_mutex_lock(&db->mu);
  if (db->readonly) { ngs_mutex_unlock(&db->mu); return ngs_set_err(db, NGS_ERROR, "ngs_remember_many: read-only handle"); }
  if (db->corrupt) { ngs_mutex_unlock(&db->mu); return ngs_set_err(db, NGS_CORRUPT, "ngs_remember_many: store is corrupt; writes refuse"); }
  if (!db->have_secret) { ngs_mutex_unlock(&db->mu); return ngs_set_err(db, NGS_ERROR, "ngs_remember_many: no node key"); }
  preps = (ngs_prep *)malloc(n * sizeof(ngs_prep));
  if (!preps) { ngs_mutex_unlock(&db->mu); return ngs_set_err(db, NGS_NOMEM, "ngs_remember_many: out of memory"); }
  for (i = 0; i < n; i++) {
    rc = ngs_prepare(db, &in[i], &preps[i]);
    if (rc != NGS_OK) { free(preps); ngs_mutex_unlock(&db->mu); return rc; }
  }
  for (i = 0; i < n; i++) {
    int last = (i + 1 == n);
    rc = ngs_append_one(db, &preps[i], last && !(flags & NGS_WRITE_NO_SYNC),
                        out_ids ? &out_ids[i] : NULL);
    if (rc != NGS_OK) break;
  }
  free(preps);
  ngs_mutex_unlock(&db->mu);
  return rc;
}

/* --- reading --- */
static size_t ngs_align8(size_t v) { return (v + 7) & ~(size_t)7; }

static ngs_fact *ngs_build_fact(const ngs_ent *e) {
  size_t total, i;
  uint8_t *base, *cur;
  ngs_fact *f;
  total = ngs_align8(sizeof(ngs_fact));
  total += ngs_align8(e->ns_len + 1);
  total += ngs_align8(e->title_len + 1);
  total += ngs_align8(e->body_len + 1);
  total += ngs_align8(e->n_tags * sizeof(ngs_str));
  for (i = 0; i < e->n_tags; i++) total += ngs_align8(e->tag_lens[i] + 1);
  total += e->attrs_len;
  base = (uint8_t *)ngs_alloc16(total);
  if (!base) return NULL;
  f = (ngs_fact *)base;
  memset(f, 0, sizeof *f);
  cur = base + ngs_align8(sizeof(ngs_fact));
  f->size = sizeof(ngs_fact);
  f->id = e->id;
  f->ns.p = (const char *)cur; f->ns.n = e->ns_len;
  memcpy(cur, e->ns, e->ns_len); cur[e->ns_len] = '\0';
  cur += ngs_align8(e->ns_len + 1);
  f->kind = e->kind;
  f->writer = e->writer;
  f->seq = e->seq;
  f->t_event = e->t_event; f->t_record = e->t_record;
  f->valid_from = e->valid_from; f->valid_to = NGS_TIME_MAX;
  memset(&f->superseded_by, 0, sizeof f->superseded_by);
  f->title.p = (const char *)cur; f->title.n = e->title_len;
  memcpy(cur, e->title, e->title_len); cur[e->title_len] = '\0';
  cur += ngs_align8(e->title_len + 1);
  f->body.p = (const char *)cur; f->body.n = e->body_len;
  if (e->body_len > 0) memcpy(cur, e->body, e->body_len);
  cur[e->body_len] = '\0';
  cur += ngs_align8(e->body_len + 1);
  if (e->n_tags > 0) {
    ngs_str *arr = (ngs_str *)cur;
    f->tags = arr;
    f->n_tags = e->n_tags;
    cur += ngs_align8(e->n_tags * sizeof(ngs_str));
    for (i = 0; i < e->n_tags; i++) {
      arr[i].p = (const char *)cur;
      arr[i].n = e->tag_lens[i];
      memcpy(cur, e->tags[i], e->tag_lens[i]);
      cur[e->tag_lens[i]] = '\0';
      cur += ngs_align8(e->tag_lens[i] + 1);
    }
  }
  f->attrs_cbor = cur;
  f->attrs_len = e->attrs_len;
  if (e->attrs_len > 0) memcpy(cur, e->attrs, e->attrs_len);
  f->schema = e->schema;
  f->redacted = 0;
  return f;
}

int ngs_get(ngs *db, const ngs_id *id, ngs_fact **out) {
  long idx;
  ngs_fact *f;
  if (!db || !id || !out) return NGS_MISUSE;
  *out = NULL;
  if (db->rc_state) return db->rc_state;
  ngs_mutex_lock(&db->mu);
  idx = ngs_htab_find(db, id);
  if (idx < 0) { ngs_mutex_unlock(&db->mu); return ngs_set_err(db, NGS_NOTFOUND, "ngs_get: unknown fact id"); }
  f = ngs_build_fact(&db->ents[idx]);
  ngs_mutex_unlock(&db->mu);
  if (!f) return ngs_set_err(db, NGS_NOMEM, "ngs_get: out of memory");
  *out = f;
  return NGS_OK;
}

struct ngs_iter {
  ngs *db;
  size_t *idx;
  size_t n, pos;
};

int ngs_scan(ngs *db, const ngs_scan_opts *o, ngs_iter **it) {
  ngs_scan_opts d = NGS_SCAN_OPTS_INIT;
  ngs_iter *iter;
  size_t i, count = 0;
  if (!db || !it) return NGS_MISUSE;
  *it = NULL;
  if (db->rc_state) return db->rc_state;
  if (o) {
    if (o->size < 4) return ngs_set_err(db, NGS_MISUSE, "ngs_scan: opts.size too small");
    if (NGS_SCAN_OK(o, ns)) d.ns = o->ns;
    if (NGS_SCAN_OK(o, writer)) d.writer = o->writer;
    if (NGS_SCAN_OK(o, since)) d.since = o->since;
    if (NGS_SCAN_OK(o, until)) d.until = o->until;
    if (NGS_SCAN_OK(o, include_derived)) d.include_derived = o->include_derived;
  }
  if (d.ns.p == NULL && d.ns.n > 0) return ngs_set_err(db, NGS_MISUSE, "ngs_scan: ns.p NULL with n > 0");
  iter = (ngs_iter *)malloc(sizeof(ngs_iter));
  if (!iter) return ngs_set_err(db, NGS_NOMEM, "ngs_scan: out of memory");
  iter->db = db;
  iter->n = 0; iter->pos = 0;
  iter->idx = NULL;
  ngs_mutex_lock(&db->mu);
  iter->idx = (size_t *)malloc((db->n_ents ? db->n_ents : 1) * sizeof(size_t));
  if (!iter->idx) { ngs_mutex_unlock(&db->mu); free(iter); return ngs_set_err(db, NGS_NOMEM, "ngs_scan: out of memory"); }
  for (i = 0; i < db->n_ents; i++) {
    ngs_ent *e = &db->ents[i];
    if (d.ns.n > 0 && (e->ns_len != d.ns.n || memcmp(e->ns, d.ns.p, d.ns.n) != 0)) continue;
    if (d.writer && memcmp(e->writer.b, d.writer->b, 32) != 0) continue;
    if (e->t_record < d.since || e->t_record > d.until) continue;
    iter->idx[count++] = i;
  }
  iter->n = count;
  ngs_mutex_unlock(&db->mu);
  *it = iter;
  return NGS_OK;
}

int ngs_iter_next(ngs_iter *it, ngs_fact **out) {
  ngs_fact *f;
  if (!it || !out) return NGS_MISUSE;
  *out = NULL;
  if (it->pos >= it->n) return NGS_NOTFOUND;
  ngs_mutex_lock(&it->db->mu);
  f = ngs_build_fact(&it->db->ents[it->idx[it->pos]]);
  ngs_mutex_unlock(&it->db->mu);
  if (!f) return NGS_NOMEM;
  it->pos++;
  *out = f;
  return NGS_OK;
}

void ngs_iter_close(ngs_iter *it) {
  if (!it) return;
  free(it->idx);
  free(it);
}

/* --- integrity: checkpoint + verify (SPEC 3.3) ---
** Checkpoint blob: canonical CBOR map
**   0 format(uint=1) 1 t_record(int) 2 fact_count(uint)
**   3 heads: array of [writer(bytes32), ns(text), seq(uint), head(bytes32)],
**     sorted by (writer, ns)
**   4 merkle_root(bytes32) 5 signer(bytes32) 6 sig(bytes64)
** sig = Ed25519 over BLAKE3 of the encoding of keys 0..5 (a 6-entry map). */
/* writers: optional per-head writer pubkeys (NULL = signer for all). */
static void ngs_encode_ckpt_head(ngs_buf *b, int with_sig, ngs_time t_record,
                                 uint64_t count, ngs_nshead **sorted, size_t n_heads,
                                 const uint8_t (*writers)[32],
                                 const uint8_t merkle[32], const uint8_t *signer,
                                 const uint8_t *sig) {
  size_t i;
  ngs_cbor_map(b, with_sig ? 7 : 6);
  ngs_cbor_uint(b, 0); ngs_cbor_uint(b, 1);
  ngs_cbor_uint(b, 1); ngs_cbor_int(b, t_record);
  ngs_cbor_uint(b, 2); ngs_cbor_uint(b, count);
  ngs_cbor_uint(b, 3); ngs_cbor_array(b, n_heads);
  for (i = 0; i < n_heads; i++) {
    ngs_cbor_array(b, 4);
    ngs_cbor_bytes(b, writers ? writers[i] : signer, 32);
    ngs_cbor_text(b, sorted[i]->ns, sorted[i]->ns_len);
    ngs_cbor_uint(b, sorted[i]->seq);
    ngs_cbor_bytes(b, sorted[i]->id.b, 32);
  }
  ngs_cbor_uint(b, 4); ngs_cbor_bytes(b, merkle, 32);
  ngs_cbor_uint(b, 5); ngs_cbor_bytes(b, signer, 32);
  if (with_sig) { ngs_cbor_uint(b, 6); ngs_cbor_bytes(b, sig, 64); }
}

static int ngs_head_ptr_cmp(const ngs_nshead *a, const ngs_nshead *b) {
  size_t minl = a->ns_len < b->ns_len ? a->ns_len : b->ns_len;
  int c = minl ? memcmp(a->ns, b->ns, minl) : 0;
  if (c) return c;
  if (a->ns_len < b->ns_len) return -1;
  if (a->ns_len > b->ns_len) return 1;
  return 0;
}

int ngs_checkpoint(ngs *db, uint8_t **ckpt, size_t *len) {
  ngs_nshead **sorted = NULL;
  uint8_t merkle[32], hash[32], sig[64];
  ngs_buf b;
  uint8_t *out;
  size_t i;
  int rc = NGS_OK;
  if (!db || !ckpt || !len) return NGS_MISUSE;
  *ckpt = NULL; *len = 0;
  if (db->rc_state) return db->rc_state;
  ngs_mutex_lock(&db->mu);
  if (!db->have_secret) { ngs_mutex_unlock(&db->mu); return ngs_set_err(db, NGS_ERROR, "ngs_checkpoint: needs the node key to sign"); }
  if (db->corrupt) { ngs_mutex_unlock(&db->mu); return ngs_set_err(db, NGS_CORRUPT, "ngs_checkpoint: store is corrupt"); }
  if (db->n_heads > 0) {
    sorted = (ngs_nshead **)malloc(db->n_heads * sizeof(ngs_nshead *));
    if (!sorted) { ngs_mutex_unlock(&db->mu); return ngs_set_err(db, NGS_NOMEM, "ngs_checkpoint: out of memory"); }
    for (i = 0; i < db->n_heads; i++) sorted[i] = &db->heads[i];
    /* insertion sort by ns (single writer in M1, so writer is constant) */
    for (i = 1; i < db->n_heads; i++) {
      ngs_nshead *key = sorted[i];
      size_t j = i;
      while (j > 0 && ngs_head_ptr_cmp(sorted[j - 1], key) > 0) { sorted[j] = sorted[j - 1]; j--; }
      sorted[j] = key;
    }
  }
  ngs_merkle(db->ents, db->n_ents, merkle);
  {
    ngs_time tr = ngs_wall_us();
    memset(&b, 0, sizeof b);
    ngs_encode_ckpt_head(&b, 0, tr, db->n_ents, sorted, db->n_heads, NULL, merkle, db->pub.b, NULL);
    if (b.oom) { rc = NGS_NOMEM; goto done; }
    ngs_blake3_hash(b.p, b.len, hash);
    ngs_ed25519_sign(&db->ed, db->seed, hash, 32, sig);
    ngs_buf_free(&b);
    memset(&b, 0, sizeof b);
    ngs_encode_ckpt_head(&b, 1, tr, db->n_ents, sorted, db->n_heads, NULL, merkle, db->pub.b, sig);
  }
  if (b.oom) { rc = NGS_NOMEM; goto done; }
  out = (uint8_t *)ngs_alloc16(b.len);
  if (!out) { rc = NGS_NOMEM; goto done; }
  memcpy(out, b.p, b.len);
  *ckpt = out;
  *len = b.len;
done:
  ngs_buf_free(&b);
  free(sorted);
  ngs_mutex_unlock(&db->mu);
  if (rc != NGS_OK) return ngs_set_err(db, rc, "ngs_checkpoint: out of memory");
  return NGS_OK;
}

/* Parse a checkpoint blob; on success fills the outputs (ns strings in
** heads_out are strdup'd; free with ngs_heads_free). */
typedef struct {
  ngs_time t_record;
  uint64_t count;
  ngs_nshead *heads; size_t n_heads;
  uint8_t (*writers)[32];
  uint8_t merkle[32];
  uint8_t signer[32];
  uint8_t sig[64];
  ngs_buf prefix;      /* re-encoded keys 0..5 for the signature check */
} ngs_ckpt_parsed;

static void ngs_ckpt_parsed_free(ngs_ckpt_parsed *c) {
  ngs_heads_free(c->heads, c->n_heads);
  free(c->writers);
  ngs_buf_free(&c->prefix);
  memset(c, 0, sizeof *c);
}

static int ngs_parse_ckpt(const uint8_t *p, size_t n, ngs_ckpt_parsed *out) {
  ngs_dec d;
  uint64_t nent, i;
  int64_t last_key = -1;
  unsigned seen = 0;
  ngs_nshead **sorted = NULL;
  d.p = p; d.len = n; d.pos = 0;
  memset(out, 0, sizeof *out);
  if (ngs_dec_map(&d, &nent) != 0 || nent != 7) return -1;
  for (i = 0; i < nent; i++) {
    uint64_t key;
    if (ngs_dec_uint(&d, &key) != 0) return -1;
    if ((int64_t)key <= last_key || key > 6) return -1;
    last_key = (int64_t)key;
    seen |= 1u << key;
    switch (key) {
      case 0: { uint64_t v; if (ngs_dec_uint(&d, &v) != 0 || v != 1) return -1; } break;
      case 1: if (ngs_dec_int(&d, &out->t_record) != 0) return -1; break;
      case 2: if (ngs_dec_uint(&d, &out->count) != 0) return -1; break;
      case 3: {
        uint64_t nh, j;
        if (ngs_dec_array(&d, &nh) != 0 || nh > (1u << 20)) return -1;
        out->n_heads = (size_t)nh;
        if (nh > 0) {
          out->heads = (ngs_nshead *)calloc(nh, sizeof(ngs_nshead));
          out->writers = (uint8_t (*)[32])calloc(nh, sizeof(uint8_t[32]));
          if (!out->heads || !out->writers) return -1;
          for (j = 0; j < nh; j++) {
            uint64_t arity;
            const uint8_t *w, *hid;
            const char *ns; size_t ns_len;
            uint64_t seq;
            if (ngs_dec_array(&d, &arity) != 0 || arity != 4) goto bad;
            {
              size_t m;
              if (ngs_dec_bytes(&d, &w, &m) != 0 || m != 32) goto bad;
            }
            if (ngs_dec_text(&d, &ns, &ns_len) != 0 || ns_len == 0 || ns_len > NGS_MAX_NS_LEN) goto bad;
            if (ngs_dec_uint(&d, &seq) != 0) goto bad;
            {
              size_t m;
              if (ngs_dec_bytes(&d, &hid, &m) != 0 || m != 32) goto bad;
            }
            out->heads[j].ns = ngs_strdup_n(ns, ns_len);
            if (!out->heads[j].ns) goto bad;
            out->heads[j].ns_len = ns_len;
            out->heads[j].seq = seq;
            memcpy(out->heads[j].id.b, hid, 32);
            memcpy(out->writers[j], w, 32);
          }
        }
      } break;
      case 4: { const uint8_t *m2; size_t m; if (ngs_dec_bytes(&d, &m2, &m) != 0 || m != 32) return -1; memcpy(out->merkle, m2, 32); } break;
      case 5: { const uint8_t *s2; size_t m; if (ngs_dec_bytes(&d, &s2, &m) != 0 || m != 32) return -1; memcpy(out->signer, s2, 32); } break;
      case 6: { const uint8_t *s3; size_t m; if (ngs_dec_bytes(&d, &s3, &m) != 0 || m != 64) return -1; memcpy(out->sig, s3, 64); } break;
      default: return -1;
    }
  }
  if (seen != 0x7Fu || d.pos != d.len) return -1;
  /* re-encode keys 0..5 canonically for the signature check */
  if (out->n_heads > 0) {
    size_t j;
    sorted = (ngs_nshead **)malloc(out->n_heads * sizeof(ngs_nshead *));
    if (!sorted) return -1;
    for (j = 0; j < out->n_heads; j++) sorted[j] = &out->heads[j];
  }
  memset(&out->prefix, 0, sizeof out->prefix);
  ngs_encode_ckpt_head(&out->prefix, 0, out->t_record, out->count, sorted,
                       out->n_heads, (const uint8_t (*)[32])out->writers,
                       out->merkle, out->signer, NULL);
  free(sorted);
  if (out->prefix.oom) return -1;
  return 0;
bad:
  return -1;
}

int ngs_verify(ngs *db, const uint8_t *ckpt, size_t len) {
  ngs_replay_out ro;
  int rc;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  if ((ckpt == NULL) != (len == 0)) return ngs_set_err(db, NGS_MISUSE, "ngs_verify: ckpt and len disagree");
  ngs_mutex_lock(&db->mu);
  rc = ngs_replay_log(db, 1, &ro);
  if (rc != NGS_OK) { ngs_mutex_unlock(&db->mu); return ngs_set_err(db, rc, "ngs_verify: log read failed"); }
  if (ro.corrupt) {
    ngs_replay_out_free(&ro);
    ngs_mutex_unlock(&db->mu);
    return ngs_set_err(db, NGS_CORRUPT, "ngs_verify: CRC, chain or signature check failed");
  }
  if (ckpt) {
    ngs_ckpt_parsed cp;
    uint8_t merkle[32], hash[32];
    size_t i;
    int bad = 0;
    if (ngs_parse_ckpt(ckpt, len, &cp) != 0) {
      ngs_ckpt_parsed_free(&cp);
      ngs_replay_out_free(&ro);
      ngs_mutex_unlock(&db->mu);
      return ngs_set_err(db, NGS_CORRUPT, "ngs_verify: checkpoint blob does not parse");
    }
    ngs_blake3_hash(cp.prefix.p, cp.prefix.len, hash);
    if (!ngs_ed25519_verify(&db->ed, cp.signer, hash, 32, cp.sig)) bad = 1;
    ngs_merkle(ro.ents, ro.n_ents, merkle);
    if (!bad && cp.count != ro.n_ents) bad = 1;
    if (!bad && memcmp(cp.merkle, merkle, 32) != 0) bad = 1;
    if (!bad && cp.n_heads != ro.n_heads) bad = 1;
    if (!bad) {
      for (i = 0; i < cp.n_heads; i++) {
        ngs_nshead *h = ngs_head_find(ro.heads, ro.n_heads, cp.heads[i].ns, cp.heads[i].ns_len);
        if (!h || h->seq != cp.heads[i].seq || memcmp(h->id.b, cp.heads[i].id.b, 32) != 0) { bad = 1; break; }
      }
    }
    ngs_ckpt_parsed_free(&cp);
    if (bad) {
      ngs_replay_out_free(&ro);
      ngs_mutex_unlock(&db->mu);
      return ngs_set_err(db, NGS_CORRUPT, "ngs_verify: checkpoint does not match the log");
    }
  }
  ngs_replay_out_free(&ro);
  ngs_mutex_unlock(&db->mu);
  return NGS_OK;
}

/* --- everything outside the M1 slice --- */
int ngs_invalidate(ngs *db, const ngs_id *id, ngs_str reason) {
  (void)id; (void)reason;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  return ngs_set_err(db, NGS_MISUSE, "ngs_invalidate: not in M1 (invalidation view is M3)");
}
int ngs_link(ngs *db, const ngs_id *a, const ngs_id *b, ngs_str rel, float weight, ngs_id *out_link_id) {
  (void)a; (void)b; (void)rel; (void)weight; (void)out_link_id;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  return ngs_set_err(db, NGS_MISUSE, "ngs_link: not in M1");
}
int ngs_redact(ngs *db, const ngs_id *id, ngs_str reason) {
  (void)id; (void)reason;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  return ngs_set_err(db, NGS_MISUSE, "ngs_redact: not in M1");
}
int ngs_grant(ngs *db, ngs_str ns, const ngs_pubkey *writer, ngs_id *out_grant_id) {
  (void)ns; (void)writer; (void)out_grant_id;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  return ngs_set_err(db, NGS_MISUSE, "ngs_grant: not in M1");
}
int ngs_recall(ngs *db, const ngs_query *q, ngs_results **out) {
  (void)q;
  if (out) *out = NULL;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  return ngs_set_err(db, NGS_MISUSE, "ngs_recall: not in M1 (fused recall is M4)");
}
int ngs_as_of(ngs *db, ngs_time t_valid, ngs_time t_record, const ngs_query *q, ngs_results **out) {
  (void)t_valid; (void)t_record; (void)q;
  if (out) *out = NULL;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  return ngs_set_err(db, NGS_MISUSE, "ngs_as_of: not in M1 (bitemporal view is M3)");
}
int ngs_mark(ngs *db, const ngs_id *id, int32_t mark) {
  (void)id; (void)mark;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  return ngs_set_err(db, NGS_MISUSE, "ngs_mark: not in M1 (salience state is M4)");
}
int ngs_rebuild(ngs *db) {
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  return ngs_set_err(db, NGS_MISUSE, "ngs_rebuild: not in M1 (derived indexes are M2)");
}
int ngs_heads(ngs *db, ngs_head **heads, size_t *n) {
  (void)heads; (void)n;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  return ngs_set_err(db, NGS_MISUSE, "ngs_heads: not in M1 (federation is M5)");
}
int ngs_sync_export(ngs *db, const ngs_head *since, size_t n_since, uint8_t **segment, size_t *len) {
  (void)since; (void)n_since; (void)segment; (void)len;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  return ngs_set_err(db, NGS_MISUSE, "ngs_sync_export: not in M1 (federation is M5)");
}
int ngs_sync_import(ngs *db, const uint8_t *segment, size_t len, ngs_sync_report **report) {
  (void)segment; (void)len;
  if (report) *report = NULL;
  if (!db) return NGS_MISUSE;
  if (db->rc_state) return db->rc_state;
  return ngs_set_err(db, NGS_MISUSE, "ngs_sync_import: not in M1 (federation is M5)");
}
/* M1 stats: every loaded entry is a FACT (no invalidation, links, redaction,
** vectors or recall yet), so those counters stay 0. The caller's size field
** versions the struct: we fill only the bytes the caller says it has. */
int ngs_stats(ngs *db, ngs_stats_t *out) {
  ngs_stats_t st;
  size_t n;
  if (!db || !out) return NGS_MISUSE;
  if (out->size < sizeof(uint32_t) + sizeof(uint64_t))
    return ngs_set_err(db, NGS_MISUSE, "ngs_stats: out->size too small (use NGS_STATS_INIT)");
  if (db->rc_state) return db->rc_state;
  memset(&st, 0, sizeof st);
  ngs_mutex_lock(&db->mu);
  st.facts = (uint64_t)db->n_ents;
  st.log_bytes = db->log_bytes;
  ngs_mutex_unlock(&db->mu);
  n = out->size < sizeof st ? out->size : sizeof st;
  st.size = out->size;
  memcpy(out, &st, n);
  return NGS_OK;
}
