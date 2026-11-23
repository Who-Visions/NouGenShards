/* SPDX-License-Identifier: Apache-2.0 */
/* plat_posix.c -- platform layer for Linux and macOS (SPEC 15). Compiles to nothing on Windows. */
typedef int ngs_plat_posix_tu_not_empty;   /* ISO C: a translation unit needs a declaration */
#ifndef _WIN32

#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif
#ifndef _DEFAULT_SOURCE
#define _DEFAULT_SOURCE 1
#endif
#if defined(__APPLE__) && !defined(_DARWIN_C_SOURCE)
#define _DARWIN_C_SOURCE 1
#endif

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>     /* rename */
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
#if defined(__linux__) || defined(__APPLE__)
#include <sys/random.h>
#endif

#include "plat.h"

typedef struct { ngs_file base; int fd; } pfile;

struct ngs_mutex { pthread_mutex_t m; };
static pthread_mutex_t g_global = PTHREAD_MUTEX_INITIALIZER;

ngs_mutex *ngs__mutex_new(void) {
  ngs_mutex *m = (ngs_mutex *)malloc(sizeof *m);
  if (m && pthread_mutex_init(&m->m, NULL) != 0) { free(m); return NULL; }
  return m;
}
void ngs__mutex_lock(ngs_mutex *m)   { (void)pthread_mutex_lock(&m->m); }
void ngs__mutex_unlock(ngs_mutex *m) { (void)pthread_mutex_unlock(&m->m); }
void ngs__mutex_free(ngs_mutex *m)   { if (m) { (void)pthread_mutex_destroy(&m->m); free(m); } }
void ngs__global_lock(void)   { (void)pthread_mutex_lock(&g_global); }
void ngs__global_unlock(void) { (void)pthread_mutex_unlock(&g_global); }

/* A volatile byte loop: memset may be removed, memset_s (Annex K) and memset_explicit (C23) are out. */
void ngs__wipe(void *p, size_t n) {
  volatile unsigned char *q = (volatile unsigned char *)p;
  while (n--) *q++ = 0;
}

static int map_err(int e) {
  switch (e) {
    case ENOENT: case ENOTDIR: return NGS_NOTFOUND;
    case EAGAIN: case EACCES: case EBUSY: return NGS_BUSY;
    case ENOMEM: return NGS_NOMEM;
    default: return NGS_IOERR;
  }
}

static int p_open(ngs_vfs *v, const char *path, int flags, ngs_file **out) {
  int oflags = O_CLOEXEC, fd;
  pfile *f;
  (void)v;
  oflags |= (flags & NGS_VF_RDWR) ? O_RDWR : O_RDONLY;
  if (flags & NGS_VF_CREATE) oflags |= O_CREAT;
  fd = open(path, oflags, 0600);
  if (fd < 0) return map_err(errno);
  f = (pfile *)malloc(sizeof *f);
  if (!f) { close(fd); return NGS_NOMEM; }
  f->base.vfs = ngs__default_vfs(); f->fd = fd;
  *out = &f->base;
  return NGS_OK;
}

static int p_pread(ngs_file *fp, void *buf, size_t n, uint64_t off, size_t *got) {
  pfile *f = (pfile *)fp;
  size_t done = 0;
  while (done < n) {
    ssize_t r = pread(f->fd, (char *)buf + done, n - done, (off_t)(off + done));
    if (r < 0) { if (errno == EINTR) continue; return NGS_IOERR; }
    if (r == 0) break;
    done += (size_t)r;
  }
  *got = done;
  return NGS_OK;
}

static int p_pwrite(ngs_file *fp, const void *buf, size_t n, uint64_t off) {
  pfile *f = (pfile *)fp;
  size_t done = 0;
  while (done < n) {
    ssize_t w = pwrite(f->fd, (const char *)buf + done, n - done, (off_t)(off + done));
    if (w < 0) { if (errno == EINTR) continue; return NGS_IOERR; }
    if (w == 0) return NGS_IOERR;
    done += (size_t)w;
  }
  return NGS_OK;
}

static int sync_fd(int fd) {
#if defined(__APPLE__)
  /* fsync on macOS does not flush the drive cache; F_FULLFSYNC does. */
  if (fcntl(fd, F_FULLFSYNC) == 0) return NGS_OK;
  return fsync(fd) == 0 ? NGS_OK : NGS_IOERR;
#elif defined(__linux__)
  return fdatasync(fd) == 0 ? NGS_OK : NGS_IOERR;
#else
  return fsync(fd) == 0 ? NGS_OK : NGS_IOERR;
#endif
}

static int p_fsync(ngs_file *fp) { return sync_fd(((pfile *)fp)->fd); }
static int p_truncate(ngs_file *fp, uint64_t len) { return ftruncate(((pfile *)fp)->fd, (off_t)len) == 0 ? NGS_OK : NGS_IOERR; }

static int p_size(ngs_file *fp, uint64_t *out) {
  struct stat st;
  if (fstat(((pfile *)fp)->fd, &st) != 0) return NGS_IOERR;
  *out = (uint64_t)st.st_size;
  return NGS_OK;
}

static int p_close(ngs_file *fp) {
  pfile *f = (pfile *)fp;
  int rc = close(f->fd) == 0 ? NGS_OK : NGS_IOERR;
  free(f);
  return rc;
}

static int p_rename(ngs_vfs *v, const char *from, const char *to) {
  (void)v;
  return rename(from, to) == 0 ? NGS_OK : map_err(errno);
}

static int p_unlink(ngs_vfs *v, const char *path) {
  (void)v;
  return unlink(path) == 0 ? NGS_OK : map_err(errno);
}

static int p_mkdir(ngs_vfs *v, const char *path) {
  (void)v;
  if (mkdir(path, 0777) == 0 || errno == EEXIST) return NGS_OK;
  return map_err(errno);
}

static int p_fsync_dir(ngs_vfs *v, const char *path) {
  int fd, rc;
  (void)v;
  fd = open(path, O_RDONLY | O_CLOEXEC);
  if (fd < 0) return map_err(errno);
  rc = fsync(fd) == 0 ? NGS_OK : NGS_IOERR;
  close(fd);
  return rc;
}

static int p_list(ngs_vfs *v, const char *dir, int (*cb)(void *arg, const char *name), void *arg) {
  DIR *d = opendir(dir);
  struct dirent *e;
  int rc = NGS_OK;
  (void)v;
  if (!d) return map_err(errno);
  while ((e = readdir(d)) != NULL) {
    if (e->d_name[0] == '.' && (e->d_name[1] == 0 || (e->d_name[1] == '.' && e->d_name[2] == 0))) continue;
    rc = cb(arg, e->d_name);
    if (rc) break;
  }
  closedir(d);
  return rc;
}

/* flock(2) locks belong to the open file description, not the process: closing some other descriptor
** to the same file does not drop them (the fcntl F_SETLK trap), and a second open of the lock file,
** even in this process, conflicts. The core's open-directory table still refuses a second handle early. */
static int p_lock(ngs_vfs *v, const char *path, ngs_file **out) {
  ngs_file *f = NULL;
  int rc = p_open(v, path, NGS_VF_RDWR | NGS_VF_CREATE, &f);
  if (rc) return rc;
  if (flock(((pfile *)f)->fd, LOCK_EX | LOCK_NB) != 0) {
    rc = (errno == EWOULDBLOCK || errno == EAGAIN) ? NGS_BUSY : map_err(errno);
    p_close(f);
    return rc;
  }
  *out = f;
  return NGS_OK;
}

static int64_t p_now_us(ngs_vfs *v) {
  struct timespec ts;
  (void)v;
  if (timespec_get(&ts, TIME_UTC) != TIME_UTC) return 0;
  return (int64_t)ts.tv_sec * 1000000 + (int64_t)(ts.tv_nsec / 1000);
}

static int p_random(ngs_vfs *v, void *buf, size_t n) {
  size_t done = 0;
  (void)v;
#if defined(__linux__)
  while (done < n) {
    ssize_t r = getrandom((char *)buf + done, n - done, 0);
    if (r < 0) { if (errno == EINTR) continue; return NGS_IOERR; }
    done += (size_t)r;
  }
  return NGS_OK;
#elif defined(__APPLE__)
  while (done < n) {
    size_t chunk = (n - done) > 256 ? 256 : (n - done);   /* getentropy limit */
    if (getentropy((char *)buf + done, chunk) != 0) return NGS_IOERR;
    done += chunk;
  }
  return NGS_OK;
#else
  {
    int fd = open("/dev/urandom", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return NGS_IOERR;
    while (done < n) {
      ssize_t r = read(fd, (char *)buf + done, n - done);
      if (r < 0) { if (errno == EINTR) continue; close(fd); return NGS_IOERR; }
      if (r == 0) { close(fd); return NGS_IOERR; }
      done += (size_t)r;
    }
    close(fd);
    return NGS_OK;
  }
#endif
}

ngs_vfs *ngs__default_vfs(void) {
  static ngs_vfs vfs = { NULL, p_open, p_pread, p_pwrite, p_fsync, p_truncate, p_size, p_close,
                         p_rename, p_unlink, p_mkdir, p_fsync_dir, p_list, p_lock, p_now_us, p_random };
  return &vfs;
}

#endif /* !_WIN32 */
