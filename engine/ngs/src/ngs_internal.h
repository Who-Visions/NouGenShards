/*
** ngs_internal.h -- private declarations shared by the NGS M1 sources.
** Phoebus bake-off entry (feat/ngs-m1-phoebus). Apache-2.0.
*/
#ifndef NGS_INTERNAL_H
#define NGS_INTERNAL_H

/* Feature macros must precede every system header (the amalgamation keeps
** this file first). Only plat_posix.c uses what they expose. */
#if defined(__APPLE__) && !defined(_DARWIN_C_SOURCE)
#  define _DARWIN_C_SOURCE 1
#elif !defined(_WIN32) && !defined(_DEFAULT_SOURCE)
#  define _DEFAULT_SOURCE 1
#endif
#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE) && !defined(__APPLE__)
#  define _POSIX_C_SOURCE 200809L
#endif

#include "ngs.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

/* ---------- platform layer (SPEC 15): the only OS-specific surface ----------
** Every function returns 0 or a NGS_* error code. A test VFS replaces the
** whole table, which is how the crash harness injects at every function. */
typedef struct ngs__file ngs__file;
typedef struct ngs__vfs {
  int  (*open)(const char *path, int create, ngs__file **out);
  int  (*close)(ngs__file *f);
  int  (*pread)(ngs__file *f, void *buf, size_t n, uint64_t off, size_t *got);
  int  (*pwrite)(ngs__file *f, const void *buf, size_t n, uint64_t off);
  int  (*sync)(ngs__file *f);
  int  (*truncate)(ngs__file *f, uint64_t size);
  int  (*size)(ngs__file *f, uint64_t *out);
  int  (*mkdir)(const char *path);           /* NGS_OK if it already exists */
  int  (*sync_dir)(const char *path);
  int  (*exists)(const char *path, int *out);
  int  (*lock)(ngs__file *f);                /* NGS_BUSY if held elsewhere */
  int  (*random)(void *buf, size_t n);
} ngs__vfs;

const ngs__vfs *ngs__vfs_posix(void);
const ngs__vfs *ngs__vfs_get(void);
void ngs__vfs_set(const ngs__vfs *v);       /* test hook; NULL restores POSIX */
void ngs__wipe(void *p, size_t n);

/* mutex (pthread on POSIX) */
typedef struct ngs__mutex ngs__mutex;
int  ngs__mutex_new(ngs__mutex **m);
void ngs__mutex_free(ngs__mutex *m);
void ngs__mutex_lock(ngs__mutex *m);
void ngs__mutex_unlock(ngs__mutex *m);

/* ---------- hashing, signing, checksums ---------- */
typedef struct {
  uint32_t key[8], cv[8];
  uint8_t  block[64];
  uint8_t  block_len, blocks_compressed;
  uint64_t chunk_counter;
  uint32_t stack[54][8];
  uint8_t  stack_len;
  uint32_t flags;
} ngs__blake3;
void ngs__blake3_init(ngs__blake3 *h);
void ngs__blake3_update(ngs__blake3 *h, const void *in, size_t n);
void ngs__blake3_final(const ngs__blake3 *h, uint8_t out[32]);
void ngs__blake3_hash(const void *in, size_t n, uint8_t out[32]);

void ngs__sha512(const void *in, size_t n, uint8_t out[64]);

typedef int64_t ngs__gf[16];
void ngs__ed25519_pubkey(const uint8_t seed[32], uint8_t pk[32]);
void ngs__ed25519_sign(uint8_t sig[64], const uint8_t *m, size_t n,
                       const uint8_t seed[32], const uint8_t pk[32]);
int  ngs__ed25519_verify(const uint8_t sig[64], const uint8_t *m, size_t n,
                         const uint8_t pk[32]);   /* 0 = valid */

uint32_t ngs__crc32c(uint32_t crc, const void *p, size_t n);

/* ---------- canonical CBOR (RFC 8949 4.2.1 core deterministic) ---------- */
typedef struct { uint8_t *p; size_t n, cap; int oom; } ngs__buf;
void ngs__buf_free(ngs__buf *b);
void ngs__buf_put(ngs__buf *b, const void *p, size_t n);
void ngs__cbor_head(ngs__buf *b, int major, uint64_t v);
void ngs__cbor_uint(ngs__buf *b, uint64_t v);
void ngs__cbor_int(ngs__buf *b, int64_t v);
void ngs__cbor_bytes(ngs__buf *b, const void *p, size_t n);
void ngs__cbor_text(ngs__buf *b, const char *p, size_t n);

typedef struct { const uint8_t *p, *end; int err; } ngs__rd;
/* Readers enforce canonical form: shortest heads, no indefinite lengths. */
int ngs__cbor_get_head(ngs__rd *r, int *major, uint64_t *v);
int ngs__cbor_get_uint(ngs__rd *r, uint64_t *v);
int ngs__cbor_get_int(ngs__rd *r, int64_t *v);
int ngs__cbor_get_bytes(ngs__rd *r, const uint8_t **p, size_t *n);
int ngs__cbor_get_text(ngs__rd *r, const char **p, size_t *n);
int ngs__cbor_skip(ngs__rd *r, int depth);   /* skip one well-formed item */

#endif
