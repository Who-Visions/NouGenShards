/*
** cbor.c -- the canonical CBOR subset NGS records use (RFC 8949 section
** 4.2.1, core deterministic encoding): shortest-form heads, definite lengths,
** no floats, no tags. The reader rejects anything a canonical writer would not
** produce, so an id recomputed from decoded bytes always matches. Apache-2.0.
*/
#include "ngs_internal.h"

void ngs__buf_free(ngs__buf *b) { free(b->p); b->p = NULL; b->n = b->cap = 0; }

void ngs__buf_put(ngs__buf *b, const void *p, size_t n) {
  if (b->oom || n == 0) return;
  if (n > SIZE_MAX - b->n) { b->oom = 1; return; }
  if (b->n + n > b->cap) {
    size_t cap = b->cap ? b->cap : 256;
    uint8_t *q;
    while (cap < b->n + n) {
      if (cap > SIZE_MAX / 2) { cap = b->n + n; break; }
      cap *= 2;
    }
    q = (uint8_t *)realloc(b->p, cap);
    if (!q) { b->oom = 1; return; }
    b->p = q; b->cap = cap;
  }
  memcpy(b->p + b->n, p, n);
  b->n += n;
}

void ngs__cbor_head(ngs__buf *b, int major, uint64_t v) {
  uint8_t h[9];
  size_t n, i;
  uint8_t mt = (uint8_t)(major << 5);
  if (v < 24)              { h[0] = (uint8_t)(mt | v); n = 1; }
  else if (v <= 0xff)      { h[0] = mt | 24; n = 2; }
  else if (v <= 0xffff)    { h[0] = mt | 25; n = 3; }
  else if (v <= 0xffffffffu) { h[0] = mt | 26; n = 5; }
  else                     { h[0] = mt | 27; n = 9; }
  for (i = n - 1; i >= 1; i--) { h[i] = (uint8_t)(v & 0xff); v >>= 8; }
  ngs__buf_put(b, h, n);
}

void ngs__cbor_uint(ngs__buf *b, uint64_t v) { ngs__cbor_head(b, 0, v); }
void ngs__cbor_int(ngs__buf *b, int64_t v) {
  /* Negative n encodes as major 1 with -1 - n, computed without overflow. */
  if (v >= 0) ngs__cbor_head(b, 0, (uint64_t)v);
  else ngs__cbor_head(b, 1, ~(uint64_t)v);
}
void ngs__cbor_bytes(ngs__buf *b, const void *p, size_t n) { ngs__cbor_head(b, 2, (uint64_t)n); ngs__buf_put(b, p, n); }
void ngs__cbor_text(ngs__buf *b, const char *p, size_t n) { ngs__cbor_head(b, 3, (uint64_t)n); ngs__buf_put(b, p, n); }

int ngs__cbor_get_head(ngs__rd *r, int *major, uint64_t *v) {
  uint8_t ib, ai;
  size_t n, i;
  uint64_t x = 0;
  if (r->err || r->p >= r->end) { r->err = 1; return -1; }
  ib = *r->p++;
  *major = ib >> 5;
  ai = ib & 31;
  if (ai < 24) { *v = ai; return 0; }
  if (ai > 27) { r->err = 1; return -1; }       /* reserved or indefinite */
  n = (size_t)1 << (ai - 24);
  if ((size_t)(r->end - r->p) < n) { r->err = 1; return -1; }
  for (i = 0; i < n; i++) x = (x << 8) | *r->p++;
  /* canonical: the shortest head that fits */
  if ((n == 1 && x < 24) || (n == 2 && x <= 0xff) || (n == 4 && x <= 0xffff) ||
      (n == 8 && x <= 0xffffffffu)) { r->err = 1; return -1; }
  *v = x;
  return 0;
}

int ngs__cbor_get_uint(ngs__rd *r, uint64_t *v) {
  int m;
  if (ngs__cbor_get_head(r, &m, v) || m != 0) { r->err = 1; return -1; }
  return 0;
}

int ngs__cbor_get_int(ngs__rd *r, int64_t *v) {
  int m;
  uint64_t x;
  if (ngs__cbor_get_head(r, &m, &x)) return -1;
  if (m == 0 && x <= (uint64_t)INT64_MAX) { *v = (int64_t)x; return 0; }
  if (m == 1 && x <= (uint64_t)INT64_MAX) { *v = -(int64_t)x - 1; return 0; }
  r->err = 1;
  return -1;
}

static int get_str(ngs__rd *r, int want, const uint8_t **p, size_t *n) {
  int m;
  uint64_t len;
  if (ngs__cbor_get_head(r, &m, &len) || m != want) { r->err = 1; return -1; }
  if (len > (uint64_t)(r->end - r->p)) { r->err = 1; return -1; }
  *p = r->p; *n = (size_t)len;
  r->p += len;
  return 0;
}
int ngs__cbor_get_bytes(ngs__rd *r, const uint8_t **p, size_t *n) { return get_str(r, 2, p, n); }
int ngs__cbor_get_text(ngs__rd *r, const char **p, size_t *n) {
  const uint8_t *q;
  if (get_str(r, 3, &q, n)) return -1;
  *p = (const char *)q;
  return 0;
}

int ngs__cbor_skip(ngs__rd *r, int depth) {
  int m;
  uint64_t v, i;
  if (depth > 32) { r->err = 1; return -1; }
  if (ngs__cbor_get_head(r, &m, &v)) return -1;
  switch (m) {
    case 0: case 1: return 0;
    case 2: case 3:
      if (v > (uint64_t)(r->end - r->p)) { r->err = 1; return -1; }
      r->p += v; return 0;
    case 4:
      for (i = 0; i < v; i++) if (ngs__cbor_skip(r, depth + 1)) return -1;
      return 0;
    case 5:
      for (i = 0; i < v; i++) {
        if (ngs__cbor_skip(r, depth + 1) || ngs__cbor_skip(r, depth + 1)) return -1;
      }
      return 0;
    case 7:   /* simple values only (false/true/null/undefined); no floats */
      if (v >= 20 && v <= 23) return 0;
      r->err = 1; return -1;
    default:  /* tags are not part of the NGS subset */
      r->err = 1; return -1;
  }
}
