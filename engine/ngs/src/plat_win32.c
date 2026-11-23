/* SPDX-License-Identifier: Apache-2.0 */
/* plat_win32.c -- platform layer for Windows (SPEC 15). Compiles to nothing elsewhere. */
typedef int ngs_plat_win32_tu_not_empty;   /* ISO C: a translation unit needs a declaration */
#ifdef _WIN32

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <bcrypt.h>

#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "plat.h"

typedef struct { ngs_file base; HANDLE h; } wfile;

struct ngs_mutex { SRWLOCK l; };
static SRWLOCK g_global = SRWLOCK_INIT;

ngs_mutex *ngs__mutex_new(void) {
  ngs_mutex *m = (ngs_mutex *)malloc(sizeof *m);
  if (m) InitializeSRWLock(&m->l);
  return m;
}
void ngs__mutex_lock(ngs_mutex *m)   { AcquireSRWLockExclusive(&m->l); }
void ngs__mutex_unlock(ngs_mutex *m) { ReleaseSRWLockExclusive(&m->l); }
void ngs__mutex_free(ngs_mutex *m)   { free(m); }
void ngs__global_lock(void)   { AcquireSRWLockExclusive(&g_global); }
void ngs__global_unlock(void) { ReleaseSRWLockExclusive(&g_global); }

void ngs__wipe(void *p, size_t n) { if (p && n) SecureZeroMemory(p, n); }

static int map_err(DWORD e) {
  switch (e) {
    case ERROR_FILE_NOT_FOUND: case ERROR_PATH_NOT_FOUND: return NGS_NOTFOUND;
    case ERROR_SHARING_VIOLATION: case ERROR_LOCK_VIOLATION: return NGS_BUSY;
    case ERROR_NOT_ENOUGH_MEMORY: case ERROR_OUTOFMEMORY: return NGS_NOMEM;
    default: return NGS_IOERR;
  }
}

/* UTF-8 path to UTF-16; the API promises UTF-8 paths, the ANSI code page would break them. */
static wchar_t *to_wide(const char *u8) {
  int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, u8, -1, NULL, 0);
  wchar_t *w;
  if (n <= 0) return NULL;
  w = (wchar_t *)malloc(sizeof(wchar_t) * (size_t)n);
  if (!w) return NULL;
  if (!MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, u8, -1, w, n)) { free(w); return NULL; }
  return w;
}

static int w_open(ngs_vfs *v, const char *path, int flags, ngs_file **out) {
  wchar_t *w = to_wide(path);
  DWORD access = GENERIC_READ, disp = OPEN_EXISTING;
  HANDLE h;
  wfile *f;
  (void)v;
  if (!w) return NGS_IOERR;
  if (flags & NGS_VF_RDWR) access |= GENERIC_WRITE;
  if (flags & NGS_VF_CREATE) disp = OPEN_ALWAYS;
  h = CreateFileW(w, access, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL, disp,
                  FILE_ATTRIBUTE_NORMAL, NULL);
  free(w);
  if (h == INVALID_HANDLE_VALUE) return map_err(GetLastError());
  f = (wfile *)malloc(sizeof *f);
  if (!f) { CloseHandle(h); return NGS_NOMEM; }
  f->base.vfs = ngs__default_vfs(); f->h = h;
  *out = &f->base;
  return NGS_OK;
}

static int w_pread(ngs_file *fp, void *buf, size_t n, uint64_t off, size_t *got) {
  wfile *f = (wfile *)fp;
  size_t done = 0;
  while (done < n) {
    OVERLAPPED ov;
    DWORD chunk = (DWORD)((n - done) > 0x40000000u ? 0x40000000u : (n - done)), r = 0;
    uint64_t o = off + done;
    memset(&ov, 0, sizeof ov);
    ov.Offset = (DWORD)(o & 0xFFFFFFFFu); ov.OffsetHigh = (DWORD)(o >> 32);
    if (!ReadFile(f->h, (char *)buf + done, chunk, &r, &ov)) {
      DWORD e = GetLastError();
      if (e == ERROR_HANDLE_EOF) break;
      return NGS_IOERR;
    }
    if (r == 0) break;
    done += r;
  }
  *got = done;
  return NGS_OK;
}

static int w_pwrite(ngs_file *fp, const void *buf, size_t n, uint64_t off) {
  wfile *f = (wfile *)fp;
  size_t done = 0;
  while (done < n) {
    OVERLAPPED ov;
    DWORD chunk = (DWORD)((n - done) > 0x40000000u ? 0x40000000u : (n - done)), w = 0;
    uint64_t o = off + done;
    memset(&ov, 0, sizeof ov);
    ov.Offset = (DWORD)(o & 0xFFFFFFFFu); ov.OffsetHigh = (DWORD)(o >> 32);
    if (!WriteFile(f->h, (const char *)buf + done, chunk, &w, &ov) || w == 0) return NGS_IOERR;
    done += w;
  }
  return NGS_OK;
}

static int w_fsync(ngs_file *fp) { return FlushFileBuffers(((wfile *)fp)->h) ? NGS_OK : NGS_IOERR; }

static int w_truncate(ngs_file *fp, uint64_t len) {
  LARGE_INTEGER li;
  li.QuadPart = (LONGLONG)len;
  if (!SetFilePointerEx(((wfile *)fp)->h, li, NULL, FILE_BEGIN)) return NGS_IOERR;
  return SetEndOfFile(((wfile *)fp)->h) ? NGS_OK : NGS_IOERR;
}

static int w_size(ngs_file *fp, uint64_t *out) {
  LARGE_INTEGER li;
  if (!GetFileSizeEx(((wfile *)fp)->h, &li)) return NGS_IOERR;
  *out = (uint64_t)li.QuadPart;
  return NGS_OK;
}

static int w_close(ngs_file *fp) {
  wfile *f = (wfile *)fp;
  BOOL ok = CloseHandle(f->h);
  free(f);
  return ok ? NGS_OK : NGS_IOERR;
}

static int w_rename(ngs_vfs *v, const char *from, const char *to) {
  wchar_t *a = to_wide(from), *b = to_wide(to);
  int rc = NGS_IOERR;
  (void)v;
  if (a && b) rc = MoveFileExW(a, b, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) ? NGS_OK : map_err(GetLastError());
  free(a); free(b);
  return rc;
}

static int w_unlink(ngs_vfs *v, const char *path) {
  wchar_t *w = to_wide(path);
  int rc = NGS_IOERR;
  (void)v;
  if (w) rc = DeleteFileW(w) ? NGS_OK : map_err(GetLastError());
  free(w);
  return rc;
}

static int w_mkdir(ngs_vfs *v, const char *path) {
  wchar_t *w = to_wide(path);
  int rc = NGS_IOERR;
  (void)v;
  if (w) {
    if (CreateDirectoryW(w, NULL)) rc = NGS_OK;
    else rc = (GetLastError() == ERROR_ALREADY_EXISTS) ? NGS_OK : map_err(GetLastError());
  }
  free(w);
  return rc;
}

/* NTFS journals metadata and MoveFileExW(WRITE_THROUGH) covers renames; there is no portable
** directory flush on Win32. Documented limit: a file creation is made durable by FlushFileBuffers
** on the file itself. */
static int w_fsync_dir(ngs_vfs *v, const char *path) { (void)v; (void)path; return NGS_OK; }

static int w_list(ngs_vfs *v, const char *dir, int (*cb)(void *arg, const char *name), void *arg) {
  size_t dl = strlen(dir);
  char *pat = (char *)malloc(dl + 3);
  wchar_t *wp;
  WIN32_FIND_DATAW fd;
  HANDLE h;
  int rc = NGS_OK;
  (void)v;
  if (!pat) return NGS_NOMEM;
  memcpy(pat, dir, dl); pat[dl] = '/'; pat[dl + 1] = '*'; pat[dl + 2] = 0;
  wp = to_wide(pat);
  free(pat);
  if (!wp) return NGS_IOERR;
  h = FindFirstFileW(wp, &fd);
  free(wp);
  if (h == INVALID_HANDLE_VALUE) return (GetLastError() == ERROR_FILE_NOT_FOUND) ? NGS_OK : map_err(GetLastError());
  do {
    char name[1024];
    if (fd.cFileName[0] == L'.' && (fd.cFileName[1] == 0 || (fd.cFileName[1] == L'.' && fd.cFileName[2] == 0))) continue;
    if (!WideCharToMultiByte(CP_UTF8, 0, fd.cFileName, -1, name, (int)sizeof name, NULL, NULL)) continue;
    rc = cb(arg, name);
    if (rc) break;
  } while (FindNextFileW(h, &fd));
  FindClose(h);
  return rc;
}

static int w_lock(ngs_vfs *v, const char *path, ngs_file **out) {
  ngs_file *f = NULL;
  OVERLAPPED ov;
  int rc = w_open(v, path, NGS_VF_RDWR | NGS_VF_CREATE, &f);
  if (rc) return rc;
  memset(&ov, 0, sizeof ov);
  if (!LockFileEx(((wfile *)f)->h, LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, &ov)) {
    rc = map_err(GetLastError());
    if (rc == NGS_IOERR && GetLastError() == ERROR_IO_PENDING) rc = NGS_BUSY;
    w_close(f);
    return rc;
  }
  *out = f;
  return NGS_OK;
}

static int64_t w_now_us(ngs_vfs *v) {
  struct timespec ts;
  (void)v;
  if (timespec_get(&ts, TIME_UTC) != TIME_UTC) return 0;
  return (int64_t)ts.tv_sec * 1000000 + (int64_t)(ts.tv_nsec / 1000);
}

static int w_random(ngs_vfs *v, void *buf, size_t n) {
  size_t done = 0;
  (void)v;
  while (done < n) {
    ULONG chunk = (ULONG)((n - done) > 0x10000u ? 0x10000u : (n - done));
    if (BCryptGenRandom(NULL, (PUCHAR)buf + done, chunk, BCRYPT_USE_SYSTEM_PREFERRED_RNG) != 0) return NGS_IOERR;
    done += chunk;
  }
  return NGS_OK;
}

ngs_vfs *ngs__default_vfs(void) {
  static ngs_vfs vfs = { NULL, w_open, w_pread, w_pwrite, w_fsync, w_truncate, w_size, w_close,
                         w_rename, w_unlink, w_mkdir, w_fsync_dir, w_list, w_lock, w_now_us, w_random };
  return &vfs;
}

#endif /* _WIN32 */
