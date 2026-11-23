/* SPDX-License-Identifier: Apache-2.0 */
/*
** cbor.c -- byte buffer, UTF-8 check, canonical CBOR, the FACT record codec, segment header and
** record framing.
**
** Canonical form (so fact_id is reproducible on every platform): definite lengths only, shortest
** integer heads, map keys are small unsigned integers in ascending order. The decoder accepts exactly
** this form and nothing else, so decode followed by encode is the identity.
**
** FACT payload = map(16): 0 id, 1 ns, 2 kind, 3 writer, 4 seq, 5 prev, 6 t_event, 7 t_record,
** 8 valid_from, 9 title, 10 body_hash, 11 tags, 12 attrs, 13 schema, 14 body, 15 sig.
** fact_id = BLAKE3(map(13) of keys 1..13): every field except id, body and sig, with the body
** represented by its hash (so a later redaction does not change the id; SPEC 2.2).
*/
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "ngs_int.h"

/* ------------------------------------------------------------ buffer */
void ngs__buf_free(ngs_buf *b) {
  free(b->p);
  b->p = NULL; b->n = b->cap = 0;
}

int ngs__buf_put(ngs_buf *b, const void *src, size_t n) {
  if (n > SIZE_MAX - b->n) return NGS_NOMEM;
  if (b->n + n > b->cap) {
    size_t nc = b->cap ? b->cap : 256;
    uint8_t *np;
    while (nc < b->n + n) {
      if (nc > SIZE_MAX / 2) return NGS_NOMEM;
      nc *= 2;
    }
    np = (uint8_t *)realloc(b->p, nc);
    if (!np) return NGS_NOMEM;
    b->p = np; b->cap = nc;
  }
  if (n) memcpy(b->p + b->n, src, n);
  b->n += n;
  return NGS_OK;
}

int ngs__buf_u8(ngs_buf *b, uint8_t v) { return ngs__buf_put(b, &v, 1); }

/* ------------------------------------------------------------- UTF-8 */
int ngs__utf8_ok(const uint8_t *s, size_t n) {
  size_t i = 0;
  while (i < n) {
    uint8_t c = s[i];
    if (c < 0x80) { i++; continue; }
    if (c >= 0xC2 && c <= 0xDF) {
      if (i + 1 >= n || (s[i + 1] & 0xC0) != 0x80) return 0;
      i += 2;
    } else if (c >= 0xE0 && c <= 0xEF) {
      if (i + 2 >= n || (s[i + 1] & 0xC0) != 0x80 || (s[i + 2] & 0xC0) != 0x80) return 0;
      if (c == 0xE0 && s[i + 1] < 0xA0) return 0;          /* overlong */
      if (c == 0xED && s[i + 1] > 0x9F) return 0;          /* surrogates */
      i += 3;
    } else if (c >= 0xF0 && c <= 0xF4) {
      if (i + 3 >= n || (s[i + 1] & 0xC0) != 0x80 || (s[i + 2] & 0xC0) != 0x80 || (s[i + 3] & 0xC0) != 0x80) return 0;
      if (c == 0xF0 && s[i + 1] < 0x90) return 0;          /* overlong */
      if (c == 0xF4 && s[i + 1] > 0x8F) return 0;          /* above U+10FFFF */
      i += 4;
    } else {
      return 0;
    }
  }
  return 1;
}

/* ----------------------------------------------------------- encoder */
int ngs__cbor_head(ngs_buf *b, int major, uint64_t v) {
  uint8_t m = (uint8_t)(major << 5), t[9];
  size_t k;
  if (v < 24) { t[0] = (uint8_t)(m | v); k = 1; }
  else if (v <= 0xFFu) { t[0] = (uint8_t)(m | 24); t[1] = (uint8_t)v; k = 2; }
  else if (v <= 0xFFFFu) { t[0] = (uint8_t)(m | 25); t[1] = (uint8_t)(v >> 8); t[2] = (uint8_t)v; k = 3; }
  else if (v <= 0xFFFFFFFFu) {
    t[0] = (uint8_t)(m | 26);
    t[1] = (uint8_t)(v >> 24); t[2] = (uint8_t)(v >> 16); t[3] = (uint8_t)(v >> 8); t[4] = (uint8_t)v;
    k = 5;
  } else {
    int i;
    t[0] = (uint8_t)(m | 27);
    for (i = 0; i < 8; i++) t[1 + i] = (uint8_t)(v >> (56 - 8 * i));
    k = 9;
  }
  return ngs__buf_put(b, t, k);
}

int ngs__cbor_uint(ngs_buf *b, uint64_t v) { return ngs__cbor_head(b, 0, v); }

int ngs__cbor_int(ngs_buf *b, int64_t v) {
  if (v >= 0) return ngs__cbor_head(b, 0, (uint64_t)v);
  return ngs__cbor_head(b, 1, (uint64_t)(-(v + 1)));        /* -1 - n without overflow */
}

int ngs__cbor_bytes(ngs_buf *b, const void *p, size_t n) {
  int rc = ngs__cbor_head(b, 2, (uint64_t)n);
  return rc ? rc : ngs__buf_put(b, p, n);
}

int ngs__cbor_text(ngs_buf *b, const void *p, size_t n) {
  int rc = ngs__cbor_head(b, 3, (uint64_t)n);
  return rc ? rc : ngs__buf_put(b, p, n);
}

/* ----------------------------------------------------------- decoder */
int ngs__cur_head(ngs_cur *c, int *major, uint64_t *v) {
  uint8_t ib;
  unsigned ai;
  size_t need = 0, i;
  uint64_t x = 0;
  if (c->bad || c->i >= c->n) { c->bad = 1; return NGS_CORRUPT; }
  ib = c->p[c->i++];
  *major = ib >> 5;
  ai = ib & 31u;
  if (ai < 24) { *v = ai; return NGS_OK; }
  if (ai == 24) need = 1; else if (ai == 25) need = 2; else if (ai == 26) need = 4; else if (ai == 27) need = 8;
  else { c->bad = 1; return NGS_CORRUPT; }                  /* reserved or indefinite length */
  if (c->n - c->i < need) { c->bad = 1; return NGS_CORRUPT; }
  for (i = 0; i < need; i++) x = (x << 8) | c->p[c->i + i];
  c->i += need;
  /* shortest form only */
  if ((ai == 24 && x < 24) || (ai == 25 && x <= 0xFFu) || (ai == 26 && x <= 0xFFFFu) || (ai == 27 && x <= 0xFFFFFFFFu)) {
    c->bad = 1; return NGS_CORRUPT;
  }
  *v = x;
  return NGS_OK;
}

int ngs__cur_uint(ngs_cur *c, uint64_t *v) {
  int major;
  if (ngs__cur_head(c, &major, v)) return NGS_CORRUPT;
  if (major != 0) { c->bad = 1; return NGS_CORRUPT; }
  return NGS_OK;
}

int ngs__cur_int(ngs_cur *c, int64_t *v) {
  int major;
  uint64_t x;
  if (ngs__cur_head(c, &major, &x)) return NGS_CORRUPT;
  if ((major != 0 && major != 1) || x > (uint64_t)INT64_MAX) { c->bad = 1; return NGS_CORRUPT; }
  *v = (major == 0) ? (int64_t)x : -1 - (int64_t)x;
  return NGS_OK;
}

static int cur_string(ngs_cur *c, int want, const uint8_t **p, size_t *n) {
  int major;
  uint64_t len;
  if (ngs__cur_head(c, &major, &len)) return NGS_CORRUPT;
  if (major != want || len > (uint64_t)(c->n - c->i)) { c->bad = 1; return NGS_CORRUPT; }
  *p = c->p + c->i;
  *n = (size_t)len;
  c->i += (size_t)len;
  return NGS_OK;
}

int ngs__cur_bytes(ngs_cur *c, const uint8_t **p, size_t *n) { return cur_string(c, 2, p, n); }

int ngs__cur_text(ngs_cur *c, const uint8_t **p, size_t *n) {
  if (cur_string(c, 3, p, n)) return NGS_CORRUPT;
  if (!ngs__utf8_ok(*p, *n)) { c->bad = 1; return NGS_CORRUPT; }
  return NGS_OK;
}

/* attrs are caller data and never interpreted: they only have to be one well-formed item,
** definite lengths, nesting <= 32, so a reader cannot be driven off the end of the buffer. */
static int skip_item(ngs_cur *c, int depth) {
  int major;
  uint64_t v, k;
  if (depth > 32) return NGS_CORRUPT;
  if (c->i >= c->n) return NGS_CORRUPT;
  if ((c->p[c->i] >> 5) == 7) {                              /* simple values and floats */
    unsigned ai = c->p[c->i] & 31u;
    size_t need = (ai < 24) ? 0 : (ai == 24 ? 1 : (ai == 25 ? 2 : (ai == 26 ? 4 : (ai == 27 ? 8 : 99))));
    if (need == 99 || ai == 31 || c->n - c->i - 1 < need) return NGS_CORRUPT;
    c->i += 1 + need;
    return NGS_OK;
  }
  if (ngs__cur_head(c, &major, &v)) return NGS_CORRUPT;
  switch (major) {
    case 0: case 1: return NGS_OK;
    case 2: case 3:
      if (v > (uint64_t)(c->n - c->i)) return NGS_CORRUPT;
      c->i += (size_t)v;
      return NGS_OK;
    case 4: case 5: {
      uint64_t count = (major == 5) ? v * 2 : v;
      if (major == 5 && v > (UINT64_MAX / 2)) return NGS_CORRUPT;
      if (count > (uint64_t)(c->n - c->i)) return NGS_CORRUPT;   /* every item is at least one byte */
      for (k = 0; k < count; k++) if (skip_item(c, depth + 1)) return NGS_CORRUPT;
      return NGS_OK;
    }
    case 6: return skip_item(c, depth + 1);                    /* tag wraps one item */
    default: return NGS_CORRUPT;
  }
}

int ngs__cbor_wellformed(const uint8_t *p, size_t n) {
  ngs_cur c;
  c.p = p; c.n = n; c.i = 0; c.bad = 0;
  if (n == 0) return NGS_CORRUPT;
  if (skip_item(&c, 0)) return NGS_CORRUPT;
  return c.i == n ? NGS_OK : NGS_CORRUPT;
}

/* --------------------------------------------------------- record codec */
int ngs__encode_tags(ngs_buf *out, const ngs_str *tags, size_t n) {
  size_t i;
  int rc = ngs__cbor_head(out, 4, (uint64_t)n);
  for (i = 0; !rc && i < n; i++) rc = ngs__cbor_text(out, tags[i].p, tags[i].n);
  return rc;
}

static int put_key(ngs_buf *b, unsigned k) { return ngs__cbor_head(b, 0, k); }

/* keys 1..13: the fields that make up the preimage, in ascending key order */
static int put_common(ngs_buf *b, const ngs_rec *r) {
  int rc;
#define NGS_T(x) do { rc = (x); if (rc) return rc; } while (0)
  NGS_T(put_key(b, 1));  NGS_T(ngs__cbor_text(b, r->ns, r->ns_len));
  NGS_T(put_key(b, 2));  NGS_T(ngs__cbor_uint(b, (uint64_t)r->kind));
  NGS_T(put_key(b, 3));  NGS_T(ngs__cbor_bytes(b, r->writer, 32));
  NGS_T(put_key(b, 4));  NGS_T(ngs__cbor_uint(b, r->seq));
  NGS_T(put_key(b, 5));  NGS_T(ngs__cbor_bytes(b, r->prev, 32));
  NGS_T(put_key(b, 6));  NGS_T(ngs__cbor_int(b, r->t_event));
  NGS_T(put_key(b, 7));  NGS_T(ngs__cbor_int(b, r->t_record));
  NGS_T(put_key(b, 8));  NGS_T(ngs__cbor_int(b, r->valid_from));
  NGS_T(put_key(b, 9));  NGS_T(ngs__cbor_text(b, r->title, r->title_len));
  NGS_T(put_key(b, 10)); NGS_T(ngs__cbor_bytes(b, r->body_hash, 32));
  NGS_T(put_key(b, 11)); NGS_T(ngs__buf_put(b, r->tags, r->tags_len));
  NGS_T(put_key(b, 12)); NGS_T(ngs__cbor_bytes(b, r->attrs, r->attrs_len));
  NGS_T(put_key(b, 13)); NGS_T(ngs__cbor_uint(b, r->schema));
  return NGS_OK;
}

static int preimage_id(const ngs_rec *r, uint8_t out[32]) {
  ngs_buf b = { NULL, 0, 0 };
  int rc = ngs__cbor_head(&b, 5, 13);
  if (!rc) rc = put_common(&b, r);
  if (!rc) ngs__blake3(b.p, b.n, out);
  ngs__buf_free(&b);
  return rc;
}

int ngs__rec_seal(ngs_rec *r, const uint8_t sk[64]) {
  uint8_t pk[32];
  int rc;
  ngs__blake3(r->body, r->body_len, r->body_hash);
  rc = preimage_id(r, r->id);
  if (rc) return rc;
  ngs__pub_from_sk(pk, sk);
  ngs__sign(r->sig, r->id, pk, sk);
  return NGS_OK;
}

int ngs__rec_encode(ngs_buf *out, const ngs_rec *r) {
  int rc = ngs__cbor_head(out, 5, 16);
  if (!rc) rc = put_key(out, 0);
  if (!rc) rc = ngs__cbor_bytes(out, r->id, 32);
  if (!rc) rc = put_common(out, r);
  if (!rc) rc = put_key(out, 14);
  if (!rc) rc = ngs__cbor_bytes(out, r->body, r->body_len);
  if (!rc) rc = put_key(out, 15);
  if (!rc) rc = ngs__cbor_bytes(out, r->sig, 64);
  return rc;
}

static int expect_key(ngs_cur *c, unsigned k) {
  uint64_t v;
  if (ngs__cur_uint(c, &v)) return NGS_CORRUPT;
  if (v != k) { c->bad = 1; return NGS_CORRUPT; }
  return NGS_OK;
}

static int get_fixed(ngs_cur *c, uint8_t *dst, size_t want) {
  const uint8_t *p;
  size_t n;
  if (ngs__cur_bytes(c, &p, &n) || n != want) { c->bad = 1; return NGS_CORRUPT; }
  memcpy(dst, p, want);
  return NGS_OK;
}

int ngs__rec_decode(const uint8_t *p, size_t n, ngs_rec *r) {
  ngs_cur c;
  int major;
  uint64_t v;
  size_t tags_start, tags_end;
  uint32_t t;
  const uint8_t *s;
  size_t sn;
  c.p = p; c.n = n; c.i = 0; c.bad = 0;
  memset(r, 0, sizeof *r);
#define NGS_D(x) do { if ((x) != NGS_OK) return NGS_CORRUPT; } while (0)
  NGS_D(ngs__cur_head(&c, &major, &v));
  if (major != 5 || v != 16) return NGS_CORRUPT;
  NGS_D(expect_key(&c, 0));  NGS_D(get_fixed(&c, r->id, 32));
  NGS_D(expect_key(&c, 1));  NGS_D(ngs__cur_text(&c, &r->ns, &r->ns_len));
  if (r->ns_len < 1 || r->ns_len > NGS_MAX_NS_LEN) return NGS_CORRUPT;
  NGS_D(expect_key(&c, 2));  NGS_D(ngs__cur_uint(&c, &v));
  if (v < NGS_EPISODIC || v > NGS_PROCEDURAL) return NGS_CORRUPT;
  r->kind = (int32_t)v;
  NGS_D(expect_key(&c, 3));  NGS_D(get_fixed(&c, r->writer, 32));
  NGS_D(expect_key(&c, 4));  NGS_D(ngs__cur_uint(&c, &r->seq));
  if (r->seq < 1) return NGS_CORRUPT;
  NGS_D(expect_key(&c, 5));  NGS_D(get_fixed(&c, r->prev, 32));
  NGS_D(expect_key(&c, 6));  NGS_D(ngs__cur_int(&c, &r->t_event));
  NGS_D(expect_key(&c, 7));  NGS_D(ngs__cur_int(&c, &r->t_record));
  NGS_D(expect_key(&c, 8));  NGS_D(ngs__cur_int(&c, &r->valid_from));
  NGS_D(expect_key(&c, 9));  NGS_D(ngs__cur_text(&c, &r->title, &r->title_len));
  if (r->title_len > NGS_MAX_TITLE_LEN) return NGS_CORRUPT;
  NGS_D(expect_key(&c, 10)); NGS_D(get_fixed(&c, r->body_hash, 32));
  NGS_D(expect_key(&c, 11));
  tags_start = c.i;
  NGS_D(ngs__cur_head(&c, &major, &v));
  if (major != 4 || v > NGS_MAX_TAGS) return NGS_CORRUPT;
  r->n_tags = (uint32_t)v;
  for (t = 0; t < r->n_tags; t++) {
    NGS_D(ngs__cur_text(&c, &s, &sn));
    if (sn > NGS_MAX_TAG) return NGS_CORRUPT;
  }
  tags_end = c.i;
  r->tags = p + tags_start; r->tags_len = tags_end - tags_start;
  NGS_D(expect_key(&c, 12)); NGS_D(ngs__cur_bytes(&c, &r->attrs, &r->attrs_len));
  if (r->attrs_len > NGS_MAX_ATTRS_LEN) return NGS_CORRUPT;
  if (r->attrs_len && ((r->attrs[0] >> 5) != 5 || ngs__cbor_wellformed(r->attrs, r->attrs_len))) return NGS_CORRUPT;
  NGS_D(expect_key(&c, 13)); NGS_D(ngs__cur_uint(&c, &v));
  if (v > 0xFFFFu) return NGS_CORRUPT;
  r->schema = (uint16_t)v;
  NGS_D(expect_key(&c, 14)); NGS_D(ngs__cur_bytes(&c, &r->body, &r->body_len));
  if (r->body_len > NGS_MAX_BODY || !ngs__utf8_ok(r->body, r->body_len)) return NGS_CORRUPT;
  NGS_D(expect_key(&c, 15)); NGS_D(get_fixed(&c, r->sig, 64));
  if (c.i != n) return NGS_CORRUPT;                          /* trailing bytes */
  return NGS_OK;
}

int ngs__rec_check_id(const ngs_rec *r) {
  uint8_t h[32];
  if (preimage_id(r, h) != NGS_OK) return NGS_NOMEM;
  if (memcmp(h, r->id, 32) != 0) return NGS_CORRUPT;
  ngs__blake3(r->body, r->body_len, h);
  return memcmp(h, r->body_hash, 32) == 0 ? NGS_OK : NGS_CORRUPT;
}

int ngs__rec_check_sig(const ngs_rec *r) {
  return ngs__verify_sig(r->sig, r->id, r->writer) ? NGS_OK : NGS_CORRUPT;
}

/* ------------------------------------------------- segment header, frame */
static void put_le16(uint8_t *d, uint16_t v) { d[0] = (uint8_t)v; d[1] = (uint8_t)(v >> 8); }
static void put_le32(uint8_t *d, uint32_t v) { d[0] = (uint8_t)v; d[1] = (uint8_t)(v >> 8); d[2] = (uint8_t)(v >> 16); d[3] = (uint8_t)(v >> 24); }
static void put_le64(uint8_t *d, uint64_t v) { int i; for (i = 0; i < 8; i++) d[i] = (uint8_t)(v >> (8 * i)); }
static uint16_t get_le16(const uint8_t *d) { return (uint16_t)(d[0] | (d[1] << 8)); }
static uint32_t get_le32(const uint8_t *d) { return (uint32_t)d[0] | ((uint32_t)d[1] << 8) | ((uint32_t)d[2] << 16) | ((uint32_t)d[3] << 24); }
static uint64_t get_le64(const uint8_t *d) { uint64_t v = 0; int i; for (i = 7; i >= 0; i--) v = (v << 8) | d[i]; return v; }

/* header (64 B): "NGSSEG\0\0" | u16 format=1 | u16 flags=0 | u64 first_ord | 32 B writer pubkey
** | u32 crc32c(bytes 0..51) | 8 B reserved zero. first_ord is the log-wide ordinal of the first
** record in the segment (SPEC 3.1 leaves the meaning of first_seq open; see the M1 notes). */
void ngs__seg_hdr_encode(uint8_t out[NGS_SEG_HDR], uint64_t first_ord, const uint8_t writer[32]) {
  static const uint8_t magic[8] = { 'N', 'G', 'S', 'S', 'E', 'G', 0, 0 };
  memset(out, 0, NGS_SEG_HDR);
  memcpy(out, magic, 8);
  put_le16(out + 8, NGS_FORMAT);
  put_le16(out + 10, 0);
  put_le64(out + 12, first_ord);
  memcpy(out + 20, writer, 32);
  put_le32(out + 52, ngs__crc32c(0, out, 52));
}

int ngs__seg_hdr_decode(const uint8_t in[NGS_SEG_HDR], uint64_t *first_ord, uint8_t writer[32]) {
  static const uint8_t magic[8] = { 'N', 'G', 'S', 'S', 'E', 'G', 0, 0 };
  size_t i;
  if (memcmp(in, magic, 8) != 0) return NGS_CORRUPT;
  if (get_le16(in + 8) != NGS_FORMAT || get_le16(in + 10) != 0) return NGS_CORRUPT;
  if (get_le32(in + 52) != ngs__crc32c(0, in, 52)) return NGS_CORRUPT;
  for (i = 56; i < NGS_SEG_HDR; i++) if (in[i] != 0) return NGS_CORRUPT;
  *first_ord = get_le64(in + 12);
  memcpy(writer, in + 20, 32);
  return NGS_OK;
}

/* record: u32 len | u8 type | payload[len] | u32 crc32c(type || payload) */
void ngs__frame_encode(uint8_t *dst, uint8_t type, const uint8_t *payload, uint32_t len) {
  uint32_t crc = ngs__crc32c(0, &type, 1);
  put_le32(dst, len);
  dst[4] = type;
  if (len) memcpy(dst + 5, payload, len);
  crc = ngs__crc32c(crc, payload, len);
  put_le32(dst + 5 + len, crc);
}
