/*
** crypto.c -- BLAKE3, SHA-512, Ed25519 and CRC32C, written from their
** specifications (BLAKE3 paper section 2; FIPS 180-4; RFC 8032; RFC 3720
** appendix B.4). No third-party code. Constants come from consts.inc, which
** tool/gen_consts.py derives from the definitions with exact integer math.
** Apache-2.0.
*/
#include "ngs_internal.h"

#include "consts.inc"

/* =============================== BLAKE3 =============================== */
enum { B3_CHUNK_START = 1, B3_CHUNK_END = 2, B3_PARENT = 4, B3_ROOT = 8 };
static const uint8_t B3_PERM[16] = {2, 6, 3, 10, 7, 0, 4, 13, 1, 11, 12, 5, 9, 14, 15, 8};

static uint32_t rotr32(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
static uint32_t ld32(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void st32(uint8_t *p, uint32_t v) {
  p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}

static void b3_g(uint32_t *s, int a, int b, int c, int d, uint32_t x, uint32_t y) {
  s[a] = s[a] + s[b] + x; s[d] = rotr32(s[d] ^ s[a], 16);
  s[c] = s[c] + s[d];     s[b] = rotr32(s[b] ^ s[c], 12);
  s[a] = s[a] + s[b] + y; s[d] = rotr32(s[d] ^ s[a], 8);
  s[c] = s[c] + s[d];     s[b] = rotr32(s[b] ^ s[c], 7);
}

/* Full 16-word compression output (first 8 words are the chaining value). */
static void b3_compress(const uint32_t cv[8], const uint8_t block[64], uint64_t counter,
                        uint32_t block_len, uint32_t flags, uint32_t out[16]) {
  uint32_t s[16], m[16], t[16];
  int r, i;
  for (i = 0; i < 16; i++) m[i] = ld32(block + 4 * i);
  for (i = 0; i < 8; i++) s[i] = cv[i];
  s[8] = BLAKE3_IV[0]; s[9] = BLAKE3_IV[1]; s[10] = BLAKE3_IV[2]; s[11] = BLAKE3_IV[3];
  s[12] = (uint32_t)counter; s[13] = (uint32_t)(counter >> 32);
  s[14] = block_len; s[15] = flags;
  for (r = 0; r < 7; r++) {
    b3_g(s, 0, 4, 8, 12, m[0], m[1]);   b3_g(s, 1, 5, 9, 13, m[2], m[3]);
    b3_g(s, 2, 6, 10, 14, m[4], m[5]);  b3_g(s, 3, 7, 11, 15, m[6], m[7]);
    b3_g(s, 0, 5, 10, 15, m[8], m[9]);  b3_g(s, 1, 6, 11, 12, m[10], m[11]);
    b3_g(s, 2, 7, 8, 13, m[12], m[13]); b3_g(s, 3, 4, 9, 14, m[14], m[15]);
    if (r < 6) {
      for (i = 0; i < 16; i++) t[i] = m[B3_PERM[i]];
      memcpy(m, t, sizeof m);
    }
  }
  for (i = 0; i < 8; i++) { out[i] = s[i] ^ s[i + 8]; out[i + 8] = s[i + 8] ^ cv[i]; }
}

static void b3_parent_cv(const uint32_t l[8], const uint32_t r[8], const uint32_t key[8],
                         uint32_t flags, uint32_t out[8]) {
  uint8_t block[64];
  uint32_t o[16];
  int i;
  for (i = 0; i < 8; i++) { st32(block + 4 * i, l[i]); st32(block + 32 + 4 * i, r[i]); }
  b3_compress(key, block, 0, 64, flags | B3_PARENT, o);
  memcpy(out, o, 32);
}

void ngs__blake3_init(ngs__blake3 *h) {
  memset(h, 0, sizeof *h);
  memcpy(h->key, BLAKE3_IV, sizeof h->key);
  memcpy(h->cv, BLAKE3_IV, sizeof h->cv);
}

static uint32_t b3_start_flag(const ngs__blake3 *h) { return h->blocks_compressed == 0 ? B3_CHUNK_START : 0; }
static size_t b3_chunk_len(const ngs__blake3 *h) { return 64u * h->blocks_compressed + h->block_len; }

void ngs__blake3_update(ngs__blake3 *h, const void *in, size_t n) {
  const uint8_t *p = (const uint8_t *)in;
  while (n > 0) {
    size_t take;
    if (b3_chunk_len(h) == 1024) {           /* chunk full: fold it into the tree */
      uint32_t o[16], cv[8];
      uint64_t total;
      b3_compress(h->cv, h->block, h->chunk_counter, h->block_len,
                  h->flags | b3_start_flag(h) | B3_CHUNK_END, o);
      memcpy(cv, o, 32);
      total = h->chunk_counter + 1;
      while ((total & 1) == 0) {
        h->stack_len--;
        b3_parent_cv(h->stack[h->stack_len], cv, h->key, h->flags, cv);
        total >>= 1;
      }
      memcpy(h->stack[h->stack_len++], cv, 32);
      h->chunk_counter++;
      memcpy(h->cv, h->key, sizeof h->cv);
      memset(h->block, 0, 64);
      h->block_len = 0;
      h->blocks_compressed = 0;
    }
    if (h->block_len == 64) {                /* block full and more input follows */
      uint32_t o[16];
      b3_compress(h->cv, h->block, h->chunk_counter, 64, h->flags | b3_start_flag(h), o);
      memcpy(h->cv, o, 32);
      h->blocks_compressed++;
      memset(h->block, 0, 64);
      h->block_len = 0;
    }
    take = 64u - h->block_len;
    if (take > 1024u - b3_chunk_len(h)) take = 1024u - b3_chunk_len(h);
    if (take > n) take = n;
    memcpy(h->block + h->block_len, p, take);
    h->block_len = (uint8_t)(h->block_len + take);
    p += take; n -= take;
  }
}

void ngs__blake3_final(const ngs__blake3 *h, uint8_t out[32]) {
  /* The current chunk's output node, then parents down the stack; the last
  ** compression gets ROOT. */
  uint32_t in_cv[8], o[16], flags;
  uint8_t block[64];
  uint64_t counter = h->chunk_counter;
  uint32_t block_len = h->block_len;
  int rem = h->stack_len, i;
  memcpy(in_cv, h->cv, 32);
  memcpy(block, h->block, 64);
  flags = h->flags | b3_start_flag(h) | B3_CHUNK_END;
  while (rem > 0) {
    uint32_t cv[8];
    b3_compress(in_cv, block, counter, block_len, flags, o);
    memcpy(cv, o, 32);
    rem--;
    for (i = 0; i < 8; i++) { st32(block + 4 * i, h->stack[rem][i]); st32(block + 32 + 4 * i, cv[i]); }
    memcpy(in_cv, h->key, 32);
    counter = 0; block_len = 64; flags = h->flags | B3_PARENT;
  }
  b3_compress(in_cv, block, counter, block_len, flags | B3_ROOT, o);
  for (i = 0; i < 8; i++) st32(out + 4 * i, o[i]);
}

void ngs__blake3_hash(const void *in, size_t n, uint8_t out[32]) {
  ngs__blake3 h;
  ngs__blake3_init(&h);
  ngs__blake3_update(&h, in, n);
  ngs__blake3_final(&h, out);
}

/* =============================== SHA-512 =============================== */
static uint64_t rotr64(uint64_t x, int n) { return (x >> n) | (x << (64 - n)); }
static uint64_t ld64be(const uint8_t *p) {
  uint64_t v = 0; int i;
  for (i = 0; i < 8; i++) v = (v << 8) | p[i];
  return v;
}
static void st64be(uint8_t *p, uint64_t v) {
  int i;
  for (i = 7; i >= 0; i--) { p[i] = (uint8_t)v; v >>= 8; }
}

static void sha512_block(uint64_t h[8], const uint8_t *b) {
  uint64_t w[80], a, bb, c, d, e, f, g, hh, t1, t2;
  int i;
  for (i = 0; i < 16; i++) w[i] = ld64be(b + 8 * i);
  for (i = 16; i < 80; i++) {
    uint64_t s0 = rotr64(w[i - 15], 1) ^ rotr64(w[i - 15], 8) ^ (w[i - 15] >> 7);
    uint64_t s1 = rotr64(w[i - 2], 19) ^ rotr64(w[i - 2], 61) ^ (w[i - 2] >> 6);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  a = h[0]; bb = h[1]; c = h[2]; d = h[3]; e = h[4]; f = h[5]; g = h[6]; hh = h[7];
  for (i = 0; i < 80; i++) {
    t1 = hh + (rotr64(e, 14) ^ rotr64(e, 18) ^ rotr64(e, 41)) + ((e & f) ^ (~e & g)) + SHA512_K[i] + w[i];
    t2 = (rotr64(a, 28) ^ rotr64(a, 34) ^ rotr64(a, 39)) + ((a & bb) ^ (a & c) ^ (bb & c));
    hh = g; g = f; f = e; e = d + t1; d = c; c = bb; bb = a; a = t1 + t2;
  }
  h[0] += a; h[1] += bb; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
}

/* Hashes up to three concatenated pieces (all Ed25519 needs). */
static void sha512_3(const uint8_t *a, size_t na, const uint8_t *b, size_t nb,
                     const uint8_t *c, size_t nc, uint8_t out[64]) {
  uint64_t h[8];
  uint8_t blk[128];
  size_t fill = 0, total = na + nb + nc;
  const uint8_t *parts[3];
  size_t lens[3];
  int k, i;
  parts[0] = a; parts[1] = b; parts[2] = c; lens[0] = na; lens[1] = nb; lens[2] = nc;
  memcpy(h, SHA512_IV, sizeof h);
  for (k = 0; k < 3; k++) {
    const uint8_t *p = parts[k];
    size_t n = lens[k];
    while (n > 0) {
      size_t take = 128 - fill;
      if (take > n) take = n;
      memcpy(blk + fill, p, take);
      fill += take; p += take; n -= take;
      if (fill == 128) { sha512_block(h, blk); fill = 0; }
    }
  }
  blk[fill++] = 0x80;
  if (fill > 112) { memset(blk + fill, 0, 128 - fill); sha512_block(h, blk); fill = 0; }
  memset(blk + fill, 0, 128 - fill);
  st64be(blk + 112, (uint64_t)(total >> 61));     /* high 64 bits of the bit length */
  st64be(blk + 120, (uint64_t)total << 3);
  sha512_block(h, blk);
  for (i = 0; i < 8; i++) st64be(out + 8 * i, h[i]);
}

void ngs__sha512(const void *in, size_t n, uint8_t out[64]) {
  sha512_3((const uint8_t *)in, n, NULL, 0, NULL, 0, out);
}

/* =============================== Ed25519 ===============================
** Field elements are 16 signed 64-bit limbs of 16 bits (radix 2^16), points
** use extended coordinates (X, Y, Z, T). Scalar multiplication is a constant-
** time ladder. Every shift of a possibly negative value goes through asr(). */
static const ngs__gf GF0 = {0}, GF1 = {1};

static void gf_cp(ngs__gf o, const ngs__gf a) { memcpy(o, a, sizeof(ngs__gf)); }

/* floor(x / 2^n) for any sign. ISO C leaves >> of a negative value
** implementation-defined, so negatives go through the complement. */
static int64_t asr(int64_t x, int n) { return x >= 0 ? x >> n : ~((~x) >> n); }

static void gf_carry(ngs__gf o) {
  int i;
  int64_t c;
  for (i = 0; i < 16; i++) {
    o[i] += (int64_t)1 << 16;
    c = asr(o[i], 16);
    if (i < 15) o[i + 1] += c - 1;
    else o[0] += 38 * (c - 1);
    o[i] -= c * 65536;
  }
}

static void gf_sel(ngs__gf p, ngs__gf q, int b) {
  int64_t t, c = ~((int64_t)b - 1);
  int i;
  for (i = 0; i < 16; i++) { t = c & (p[i] ^ q[i]); p[i] ^= t; q[i] ^= t; }
}

static void gf_pack(uint8_t o[32], const ngs__gf n) {
  ngs__gf m, t;
  int i, j, b;
  gf_cp(t, n);
  gf_carry(t); gf_carry(t); gf_carry(t);
  for (j = 0; j < 2; j++) {
    m[0] = t[0] - 0xffed;
    for (i = 1; i < 15; i++) {
      m[i] = t[i] - 0xffff - (asr(m[i - 1], 16) & 1);
      m[i - 1] &= 0xffff;
    }
    m[15] = t[15] - 0x7fff - (asr(m[14], 16) & 1);
    b = (int)(asr(m[15], 16) & 1);
    m[14] &= 0xffff;
    gf_sel(t, m, 1 - b);
  }
  for (i = 0; i < 16; i++) { o[2 * i] = (uint8_t)(t[i] & 0xff); o[2 * i + 1] = (uint8_t)((t[i] >> 8) & 0xff); }
}

static int gf_neq(const ngs__gf a, const ngs__gf b) {
  uint8_t c[32], d[32];
  gf_pack(c, a); gf_pack(d, b);
  return memcmp(c, d, 32) != 0;
}
static int gf_par(const ngs__gf a) { uint8_t d[32]; gf_pack(d, a); return d[0] & 1; }

static void gf_unpack(ngs__gf o, const uint8_t n[32]) {
  int i;
  for (i = 0; i < 16; i++) o[i] = n[2 * i] + ((int64_t)n[2 * i + 1] << 8);
  o[15] &= 0x7fff;
}

static void gf_add(ngs__gf o, const ngs__gf a, const ngs__gf b) { int i; for (i = 0; i < 16; i++) o[i] = a[i] + b[i]; }
static void gf_sub(ngs__gf o, const ngs__gf a, const ngs__gf b) { int i; for (i = 0; i < 16; i++) o[i] = a[i] - b[i]; }

static void gf_mul(ngs__gf o, const ngs__gf a, const ngs__gf b) {
  int64_t t[31];
  int i, j;
  memset(t, 0, sizeof t);
  for (i = 0; i < 16; i++) for (j = 0; j < 16; j++) t[i + j] += a[i] * b[j];
  for (i = 0; i < 15; i++) t[i] += 38 * t[i + 16];
  for (i = 0; i < 16; i++) o[i] = t[i];
  gf_carry(o); gf_carry(o);
}
static void gf_sq(ngs__gf o, const ngs__gf a) { gf_mul(o, a, a); }

static void gf_inv(ngs__gf o, const ngs__gf i) {   /* i^(p-2) */
  ngs__gf c;
  int a;
  gf_cp(c, i);
  for (a = 253; a >= 0; a--) { gf_sq(c, c); if (a != 2 && a != 4) gf_mul(c, c, i); }
  gf_cp(o, c);
}

static void gf_pow2523(ngs__gf o, const ngs__gf i) {   /* i^((p-5)/8) */
  ngs__gf c;
  int a;
  gf_cp(c, i);
  for (a = 250; a >= 0; a--) { gf_sq(c, c); if (a != 1) gf_mul(c, c, i); }
  gf_cp(o, c);
}

static void pt_add(ngs__gf p[4], ngs__gf q[4]) {
  ngs__gf a, b, c, d, t, e, f, g, h;
  gf_sub(a, p[1], p[0]); gf_sub(t, q[1], q[0]); gf_mul(a, a, t);
  gf_add(b, p[0], p[1]); gf_add(t, q[0], q[1]); gf_mul(b, b, t);
  gf_mul(c, p[3], q[3]); gf_mul(c, c, ED_D2);
  gf_mul(d, p[2], q[2]); gf_add(d, d, d);
  gf_sub(e, b, a); gf_sub(f, d, c); gf_add(g, d, c); gf_add(h, b, a);
  gf_mul(p[0], e, f); gf_mul(p[1], h, g); gf_mul(p[2], g, f); gf_mul(p[3], e, h);
}

static void pt_cswap(ngs__gf p[4], ngs__gf q[4], int b) {
  int i;
  for (i = 0; i < 4; i++) gf_sel(p[i], q[i], b);
}

static void pt_pack(uint8_t r[32], ngs__gf p[4]) {
  ngs__gf tx, ty, zi;
  gf_inv(zi, p[2]);
  gf_mul(tx, p[0], zi); gf_mul(ty, p[1], zi);
  gf_pack(r, ty);
  r[31] ^= (uint8_t)(gf_par(tx) << 7);
}

static void pt_scalarmult(ngs__gf p[4], ngs__gf q[4], const uint8_t s[32]) {
  int i;
  gf_cp(p[0], GF0); gf_cp(p[1], GF1); gf_cp(p[2], GF1); gf_cp(p[3], GF0);
  for (i = 255; i >= 0; i--) {
    int b = (s[i / 8] >> (i & 7)) & 1;
    pt_cswap(p, q, b);
    pt_add(q, p);
    pt_add(p, p);
    pt_cswap(p, q, b);
  }
}

static void pt_scalarbase(ngs__gf p[4], const uint8_t s[32]) {
  ngs__gf q[4];
  gf_cp(q[0], ED_BX); gf_cp(q[1], ED_BY); gf_cp(q[2], GF1); gf_mul(q[3], ED_BX, ED_BY);
  pt_scalarmult(p, q, s);
}

/* r = x mod L for a 64-limb little-endian number with byte-sized limbs. */
static void sc_modL(uint8_t r[32], int64_t x[64]) {
  int64_t carry;
  int i, j;
  for (i = 63; i >= 32; --i) {
    carry = 0;
    for (j = i - 32; j < i - 12; ++j) {
      x[j] += carry - 16 * x[i] * ED_L[j - (i - 32)];
      carry = asr(x[j] + 128, 8);
      x[j] -= carry * 256;
    }
    x[j] += carry;
    x[i] = 0;
  }
  carry = 0;
  for (j = 0; j < 32; ++j) {
    x[j] += carry - asr(x[31], 4) * ED_L[j];
    carry = asr(x[j], 8);
    x[j] &= 255;
  }
  for (j = 0; j < 32; ++j) x[j] -= carry * ED_L[j];
  for (i = 0; i < 32; ++i) { x[i + 1] += asr(x[i], 8); r[i] = (uint8_t)(x[i] & 255); }
}

static void sc_reduce(uint8_t r[64]) {
  int64_t x[64];
  int i;
  for (i = 0; i < 64; ++i) x[i] = (int64_t)(uint64_t)r[i];
  for (i = 0; i < 64; ++i) r[i] = 0;
  sc_modL(r, x);
}

static void ed_expand(const uint8_t seed[32], uint8_t d[64]) {
  ngs__sha512(seed, 32, d);
  d[0] &= 248; d[31] &= 127; d[31] |= 64;
}

void ngs__ed25519_pubkey(const uint8_t seed[32], uint8_t pk[32]) {
  uint8_t d[64];
  ngs__gf p[4];
  ed_expand(seed, d);
  pt_scalarbase(p, d);
  pt_pack(pk, p);
  ngs__wipe(d, sizeof d);
}

void ngs__ed25519_sign(uint8_t sig[64], const uint8_t *m, size_t n,
                       const uint8_t seed[32], const uint8_t pk[32]) {
  uint8_t d[64], r[64], h[64];
  int64_t x[64];
  ngs__gf p[4];
  int i, j;
  ed_expand(seed, d);
  sha512_3(d + 32, 32, m, n, NULL, 0, r);
  sc_reduce(r);
  pt_scalarbase(p, r);
  pt_pack(sig, p);
  sha512_3(sig, 32, pk, 32, m, n, h);
  sc_reduce(h);
  for (i = 0; i < 64; i++) x[i] = 0;
  for (i = 0; i < 32; i++) x[i] = (int64_t)(uint64_t)r[i];
  for (i = 0; i < 32; i++) for (j = 0; j < 32; j++) x[i + j] += h[i] * (int64_t)(uint64_t)d[j];
  sc_modL(sig + 32, x);
  ngs__wipe(d, sizeof d); ngs__wipe(r, sizeof r);
}

/* Decode -A (the negated public key point); -1 if not on the curve. */
static int pt_unpackneg(ngs__gf r[4], const uint8_t p[32]) {
  ngs__gf t, chk, num, den, den2, den4, den6;
  gf_cp(r[2], GF1);
  gf_unpack(r[1], p);
  gf_sq(num, r[1]);
  gf_mul(den, num, ED_D);
  gf_sub(num, num, r[2]);
  gf_add(den, r[2], den);
  gf_sq(den2, den); gf_sq(den4, den2); gf_mul(den6, den4, den2);
  gf_mul(t, den6, num); gf_mul(t, t, den);
  gf_pow2523(t, t);
  gf_mul(t, t, num); gf_mul(t, t, den); gf_mul(t, t, den);
  gf_mul(r[0], t, den);
  gf_sq(chk, r[0]); gf_mul(chk, chk, den);
  if (gf_neq(chk, num)) gf_mul(r[0], r[0], ED_I);
  gf_sq(chk, r[0]); gf_mul(chk, chk, den);
  if (gf_neq(chk, num)) return -1;
  if (gf_par(r[0]) == (p[31] >> 7)) gf_sub(r[0], GF0, r[0]);
  gf_mul(r[3], r[0], r[1]);
  return 0;
}

/* S must be canonical (S < L), which rejects the classic malleability. */
static int sc_lt_L(const uint8_t s[32]) {
  int i;
  for (i = 31; i >= 0; i--) {
    if (s[i] < ED_L[i]) return 1;
    if (s[i] > ED_L[i]) return 0;
  }
  return 0;
}

int ngs__ed25519_verify(const uint8_t sig[64], const uint8_t *m, size_t n, const uint8_t pk[32]) {
  uint8_t h[64], t[32];
  ngs__gf p[4], q[4];
  if (!sc_lt_L(sig + 32)) return -1;
  if (pt_unpackneg(q, pk) != 0) return -1;
  sha512_3(sig, 32, pk, 32, m, n, h);
  sc_reduce(h);
  pt_scalarmult(p, q, h);
  pt_scalarbase(q, sig + 32);
  pt_add(p, q);
  pt_pack(t, p);
  return memcmp(sig, t, 32) == 0 ? 0 : -1;
}

/* =============================== CRC32C ===============================
** Castagnoli polynomial, reflected (0x82F63B78), table built on first use.
** Building it twice under a race writes identical values, so it needs no lock
** for correctness; the flag is only an optimisation. */
static uint32_t crc_tab[256];
static volatile int crc_ready;

uint32_t ngs__crc32c(uint32_t crc, const void *p, size_t n) {
  const uint8_t *b = (const uint8_t *)p;
  if (!crc_ready) {
    uint32_t i, k, c;
    for (i = 0; i < 256; i++) {
      c = i;
      for (k = 0; k < 8; k++) c = (c & 1) ? (c >> 1) ^ 0x82F63B78u : c >> 1;
      crc_tab[i] = c;
    }
    crc_ready = 1;
  }
  crc = ~crc;
  while (n--) crc = crc_tab[(crc ^ *b++) & 0xff] ^ (crc >> 8);
  return ~crc;
}
