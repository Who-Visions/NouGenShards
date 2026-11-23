/* SPDX-License-Identifier: Apache-2.0 */
/*
** ngs_int.h -- internal declarations for the NGS M1 core. Not installed.
** The core includes only the headers SPEC 14 allows; the OS is reached through plat.h.
*/
#ifndef NGS_INT_H
#define NGS_INT_H

#include "ngs.h"
#include "plat.h"

#include <stddef.h>
#include <stdint.h>

/* Open with an explicit VFS (the public ngs_open uses the default one). */
int ngs__open_vfs(const char *dir, const ngs_open_opts *opts, ngs_vfs *vfs, ngs **out);

/* Every entry point of ngs.h that M1 does not implement returns this:
** NGS_MISUSE with errmsg "not in M1". */
int ngs__not_in_m1(ngs *db);

/* ---------------------------------------------------------- byte buffer */
typedef struct { uint8_t *p; size_t n, cap; } ngs_buf;
void ngs__buf_free(ngs_buf *b);
int  ngs__buf_put(ngs_buf *b, const void *src, size_t n);   /* 0 ok, else NGS_NOMEM */
int  ngs__buf_u8(ngs_buf *b, uint8_t v);

/* ---------------------------------------------------- crc32c, utf-8, hash */
uint32_t ngs__crc32c(uint32_t prev, const void *p, size_t n);   /* prev=0 to start; chains */
int  ngs__utf8_ok(const uint8_t *s, size_t n);                   /* 1 = strictly valid */
void ngs__blake3(const void *p, size_t n, uint8_t out[32]);
void ngs__keypair(uint8_t pk[32], uint8_t sk[64], const uint8_t seed[32]);
void ngs__pub_from_sk(uint8_t pk[32], const uint8_t sk[64]);
void ngs__sign(uint8_t sig[64], const uint8_t msg[32], const uint8_t pk[32], const uint8_t sk[64]);
int  ngs__verify_sig(const uint8_t sig[64], const uint8_t msg[32], const uint8_t pk[32]);

/* ------------------------------------------------------- canonical CBOR */
/* Deterministic subset: definite lengths, shortest integers, ascending small-int map keys. */
int  ngs__cbor_head(ngs_buf *b, int major, uint64_t v);
int  ngs__cbor_uint(ngs_buf *b, uint64_t v);
int  ngs__cbor_int(ngs_buf *b, int64_t v);
int  ngs__cbor_bytes(ngs_buf *b, const void *p, size_t n);
int  ngs__cbor_text(ngs_buf *b, const void *p, size_t n);

typedef struct { const uint8_t *p; size_t n, i; int bad; } ngs_cur;
int  ngs__cur_head(ngs_cur *c, int *major, uint64_t *v);        /* strict shortest form; 0 ok, else NGS_CORRUPT */
int  ngs__cur_uint(ngs_cur *c, uint64_t *v);
int  ngs__cur_int(ngs_cur *c, int64_t *v);
int  ngs__cur_bytes(ngs_cur *c, const uint8_t **p, size_t *n);
int  ngs__cur_text(ngs_cur *c, const uint8_t **p, size_t *n);   /* validates UTF-8 */
int  ngs__cbor_wellformed(const uint8_t *p, size_t n);          /* exactly one item, definite lengths, depth-limited */

/* ------------------------------------------------------- fact record codec */
#define NGS_REC_PAD      0
#define NGS_REC_FACT     1
#define NGS_REC_PENDING  0x80    /* batch member: committed by the next record that lacks this bit */

#define NGS_MAX_BODY     (1024u * 1024u)
#define NGS_MAX_TAGS     1024u
#define NGS_MAX_TAG      1024u
#define NGS_MAX_REC      (4u * 1024u * 1024u)

typedef struct {
  uint8_t  id[32];
  uint8_t  writer[32];
  uint8_t  prev[32];
  uint8_t  sig[64];
  uint8_t  body_hash[32];
  uint64_t seq;
  int64_t  t_event, t_record, valid_from;
  int32_t  kind;
  uint16_t schema;
  const uint8_t *ns;    size_t ns_len;
  const uint8_t *title; size_t title_len;
  const uint8_t *body;  size_t body_len;
  const uint8_t *attrs; size_t attrs_len;
  const uint8_t *tags;  size_t tags_len;   /* canonical CBOR array of text, as stored */
  uint32_t n_tags;
} ngs_rec;

/* Canonical CBOR array of text for the tags; caller frees via ngs__buf_free. */
int ngs__encode_tags(ngs_buf *out, const ngs_str *tags, size_t n);

/* Fills r->body_hash, r->id, r->sig from the other fields (sk signs). */
int ngs__rec_seal(ngs_rec *r, const uint8_t sk[64]);
/* Payload of a FACT record. */
int ngs__rec_encode(ngs_buf *out, const ngs_rec *r);
/* Strict decode. Pointers borrow from p. Returns 0 or NGS_CORRUPT. Does not hash or verify. */
int ngs__rec_decode(const uint8_t *p, size_t n, ngs_rec *r);
/* 0 if the stored id equals BLAKE3 of the canonical preimage and the body hash matches the body. */
int ngs__rec_check_id(const ngs_rec *r);
/* 0 if the signature verifies under r->writer. */
int ngs__rec_check_sig(const ngs_rec *r);

/* ---------------------------------------------------------- segment format */
#define NGS_SEG_HDR 64
#define NGS_FRAME_OVERHEAD 9             /* u32 len + u8 type + u32 crc */
void ngs__seg_hdr_encode(uint8_t out[NGS_SEG_HDR], uint64_t first_ord, const uint8_t writer[32]);
/* 0 ok; NGS_CORRUPT when magic/format/reserved/crc is wrong. */
int  ngs__seg_hdr_decode(const uint8_t in[NGS_SEG_HDR], uint64_t *first_ord, uint8_t writer[32]);
/* dst must hold NGS_FRAME_OVERHEAD + len bytes. */
void ngs__frame_encode(uint8_t *dst, uint8_t type, const uint8_t *payload, uint32_t len);

#endif /* NGS_INT_H */
