/* SPDX-License-Identifier: Apache-2.0 */
/*
** plat.h -- the platform layer (SPEC section 15). The only OS-specific code in
** NGS. The core calls nothing but this interface; the crash harness replaces it
** with an in-memory filesystem, so every function below is a fault-injection
** point. Implemented twice: plat_posix.c and plat_win32.c.
**
** Every function returns the same codes on both sides: 0 (NGS_OK), NGS_NOTFOUND,
** NGS_BUSY, NGS_NOMEM or NGS_IOERR. This is the only place errno or
** GetLastError is read.
*/
#ifndef NGS_PLAT_H
#define NGS_PLAT_H

#include "ngs.h"

#include <stddef.h>
#include <stdint.h>

typedef struct ngs_vfs  ngs_vfs;
typedef struct ngs_file ngs_file;

struct ngs_file { ngs_vfs *vfs; };          /* implementations embed this first */

#define NGS_VF_RDONLY 1
#define NGS_VF_RDWR   2
#define NGS_VF_CREATE 4

struct ngs_vfs {
  void *ctx;
  /* NGS_NOTFOUND when the file is missing and NGS_VF_CREATE is not set. */
  int (*open)(ngs_vfs *v, const char *path, int flags, ngs_file **out);
  int (*pread)(ngs_file *f, void *buf, size_t n, uint64_t off, size_t *got);   /* *got < n only at end of file */
  int (*pwrite)(ngs_file *f, const void *buf, size_t n, uint64_t off);
  int (*fsync)(ngs_file *f);                 /* make written data durable (fdatasync / F_FULLFSYNC / FlushFileBuffers) */
  int (*truncate)(ngs_file *f, uint64_t len);
  int (*size)(ngs_file *f, uint64_t *out);
  int (*close)(ngs_file *f);
  int (*rename)(ngs_vfs *v, const char *from, const char *to);   /* replaces the target */
  int (*unlink)(ngs_vfs *v, const char *path);
  int (*mkdir)(ngs_vfs *v, const char *path);                    /* ok if it exists */
  int (*fsync_dir)(ngs_vfs *v, const char *path);                /* make a create/rename durable */
  int (*list)(ngs_vfs *v, const char *dir, int (*cb)(void *arg, const char *name), void *arg);
  int (*lock)(ngs_vfs *v, const char *path, ngs_file **out);     /* exclusive; NGS_BUSY if held; close releases */
  int64_t (*now_us)(ngs_vfs *v);                                 /* wall clock, microseconds since the epoch */
  int (*random)(ngs_vfs *v, void *buf, size_t n);                /* CSPRNG */
};

/* The real filesystem. */
ngs_vfs *ngs__default_vfs(void);

/* Wipe a secret so the compiler cannot drop the store. */
void ngs__wipe(void *p, size_t n);

/* A mutex for one handle, and one process-wide lock (open-directory table). */
typedef struct ngs_mutex ngs_mutex;
ngs_mutex *ngs__mutex_new(void);
void ngs__mutex_lock(ngs_mutex *m);
void ngs__mutex_unlock(ngs_mutex *m);
void ngs__mutex_free(ngs_mutex *m);
void ngs__global_lock(void);
void ngs__global_unlock(void);

#endif /* NGS_PLAT_H */
