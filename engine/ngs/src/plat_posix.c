/*
** plat_posix.c -- the POSIX half of the platform layer (SPEC 15).
** The only file that includes OS headers or reads errno. Apache-2.0.
*/
#include "ngs_internal.h"

#if !defined(_WIN32)
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
#if defined(__APPLE__)
#include <sys/random.h>
#endif

struct ngs__file { int fd; };

static int px_err(void) {
  switch (errno) {
    case ENOMEM: return NGS_NOMEM;
    case EAGAIN: case EACCES: return NGS_BUSY;
    default: return NGS_IOERR;
  }
}

static int px_open(const char *path, int create, ngs__file **out) {
  int fl = O_RDWR | O_CLOEXEC | (create ? O_CREAT : 0);
  int fd;
  ngs__file *f;
  *out = NULL;
  do { fd = open(path, fl, 0600); } while (fd < 0 && errno == EINTR);
  if (fd < 0) return errno == ENOENT ? NGS_NOTFOUND : NGS_IOERR;
  f = (ngs__file *)malloc(sizeof *f);
  if (!f) { close(fd); return NGS_NOMEM; }
  f->fd = fd;
  *out = f;
  return NGS_OK;
}

static int px_close(ngs__file *f) {
  int rc = 0;
  if (!f) return NGS_OK;
  if (close(f->fd) != 0 && errno != EINTR) rc = NGS_IOERR;
  free(f);
  return rc;
}

static int px_pread(ngs__file *f, void *buf, size_t n, uint64_t off, size_t *got) {
  size_t done = 0;
  while (done < n) {
    ssize_t k = pread(f->fd, (char *)buf + done, n - done, (off_t)(off + done));
    if (k < 0) { if (errno == EINTR) continue; return NGS_IOERR; }
    if (k == 0) break;
    done += (size_t)k;
  }
  *got = done;
  return NGS_OK;
}

static int px_pwrite(ngs__file *f, const void *buf, size_t n, uint64_t off) {
  size_t done = 0;
  while (done < n) {
    ssize_t k = pwrite(f->fd, (const char *)buf + done, n - done, (off_t)(off + done));
    if (k < 0) { if (errno == EINTR) continue; return px_err(); }
    done += (size_t)k;
  }
  return NGS_OK;
}

static int px_sync(ngs__file *f) {
#if defined(__APPLE__) && defined(F_FULLFSYNC)
  /* fsync on macOS does not flush the drive cache; F_FULLFSYNC does. Fall
  ** back to fsync on filesystems that refuse it. */
  if (fcntl(f->fd, F_FULLFSYNC) == 0) return NGS_OK;
  return fsync(f->fd) == 0 ? NGS_OK : NGS_IOERR;
#elif defined(__linux__)
  return fdatasync(f->fd) == 0 ? NGS_OK : NGS_IOERR;
#else
  return fsync(f->fd) == 0 ? NGS_OK : NGS_IOERR;
#endif
}

static int px_truncate(ngs__file *f, uint64_t size) {
  return ftruncate(f->fd, (off_t)size) == 0 ? NGS_OK : NGS_IOERR;
}

static int px_size(ngs__file *f, uint64_t *out) {
  struct stat st;
  if (fstat(f->fd, &st) != 0) return NGS_IOERR;
  *out = (uint64_t)st.st_size;
  return NGS_OK;
}

static int px_mkdir(const char *path) {
  if (mkdir(path, 0700) == 0 || errno == EEXIST) return NGS_OK;
  return NGS_IOERR;
}

static int px_sync_dir(const char *path) {
  int fd = open(path, O_RDONLY | O_CLOEXEC);
  int rc;
  if (fd < 0) return NGS_IOERR;
  rc = fsync(fd) == 0 ? NGS_OK : NGS_IOERR;
  close(fd);
  return rc;
}

static int px_exists(const char *path, int *out) {
  struct stat st;
  *out = stat(path, &st) == 0;
  return NGS_OK;
}

/* flock, not fcntl(F_SETLK) as SPEC 15 lists: fcntl record locks belong to
** the process, so a second handle in the same process would also get the
** lock, and closing ANY descriptor of the file drops it. flock locks belong
** to the open file description, so two handles exclude each other even
** inside one process. (Local filesystems; NFS is out of scope for M1.) */
static int px_lock(ngs__file *f) {
  if (flock(f->fd, LOCK_EX | LOCK_NB) == 0) return NGS_OK;
  return (errno == EWOULDBLOCK || errno == EAGAIN) ? NGS_BUSY : NGS_IOERR;
}

static int px_random(void *buf, size_t n) {
  size_t done = 0;
  while (done < n) {   /* getentropy caps each call at 256 bytes */
    size_t k = n - done > 256 ? 256 : n - done;
    if (getentropy((char *)buf + done, k) != 0) return NGS_IOERR;
    done += k;
  }
  return NGS_OK;
}

static const ngs__vfs px_vfs = {
  px_open, px_close, px_pread, px_pwrite, px_sync, px_truncate, px_size,
  px_mkdir, px_sync_dir, px_exists, px_lock, px_random
};
const ngs__vfs *ngs__vfs_posix(void) { return &px_vfs; }

void ngs__wipe(void *p, size_t n) {
  volatile uint8_t *v = (volatile uint8_t *)p;
  while (n--) *v++ = 0;
}

struct ngs__mutex { pthread_mutex_t m; };
int ngs__mutex_new(ngs__mutex **out) {
  ngs__mutex *m = (ngs__mutex *)malloc(sizeof *m);
  *out = NULL;
  if (!m) return NGS_NOMEM;
  if (pthread_mutex_init(&m->m, NULL) != 0) { free(m); return NGS_ERROR; }
  *out = m;
  return NGS_OK;
}
void ngs__mutex_free(ngs__mutex *m) { if (m) { pthread_mutex_destroy(&m->m); free(m); } }
void ngs__mutex_lock(ngs__mutex *m) { pthread_mutex_lock(&m->m); }
void ngs__mutex_unlock(ngs__mutex *m) { pthread_mutex_unlock(&m->m); }

struct ngs__cond { pthread_cond_t c; };
int ngs__cond_new(ngs__cond **out) {
  ngs__cond *c = (ngs__cond *)malloc(sizeof *c);
  *out = NULL;
  if (!c) return NGS_NOMEM;
  if (pthread_cond_init(&c->c, NULL) != 0) { free(c); return NGS_ERROR; }
  *out = c;
  return NGS_OK;
}
void ngs__cond_free(ngs__cond *c) { if (c) { pthread_cond_destroy(&c->c); free(c); } }
void ngs__cond_wait(ngs__cond *c, ngs__mutex *m) { pthread_cond_wait(&c->c, &m->m); }
void ngs__cond_broadcast(ngs__cond *c) { pthread_cond_broadcast(&c->c); }

static pthread_mutex_t g_lock = PTHREAD_MUTEX_INITIALIZER;
void ngs__global_lock(void) { pthread_mutex_lock(&g_lock); }
void ngs__global_unlock(void) { pthread_mutex_unlock(&g_lock); }

#endif /* !_WIN32 */

static const ngs__vfs *g_vfs;
const ngs__vfs *ngs__vfs_get(void) { return g_vfs ? g_vfs : ngs__vfs_posix(); }
void ngs__vfs_set(const ngs__vfs *v) { g_vfs = v; }
