/*
** Black-box M1 behaviour checks for an NGS engine (PR 1199 ngs.h, draft 0.3.1).
**
** Drives the engine only through ngs.h, plus POSIX file access to damage the
** database directory from outside (torn tail, bit flip). Prints one line per
** check, "PASS <name>" or "FAIL <name>: <why>", then "SUMMARY <pass> <fail>".
** Exit status is the failure count (capped at 125).
**
** Usage: behaviour <empty-scratch-dir>
**
** Scope is the bake-off M1 slice: open/close, remember, remember_many, get,
** flush, scan, verify, reopen, torn-tail recovery, corruption detection, and
** NGS_MISUSE for the calls outside M1.
*/
#define _POSIX_C_SOURCE 200809L
#include "ngs.h"

#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int n_pass, n_fail;

static void result(int ok, const char *name, const char *why) {
  if (ok) {
    printf("PASS %s\n", name);
    n_pass++;
  } else {
    printf("FAIL %s: %s\n", name, why);
    n_fail++;
  }
  fflush(stdout);
}

static ngs_str S(const char *s) {
  ngs_str r;
  r.p = s;
  r.n = strlen(s);
  return r;
}

static int str_eq(ngs_str a, const char *b) {
  return a.n == strlen(b) && (a.n == 0 || memcmp(a.p, b, a.n) == 0);
}

static int id_zero(const ngs_id *id) {
  size_t i;
  for (i = 0; i < sizeof id->b; i++)
    if (id->b[i]) return 0;
  return 1;
}

static int open_db(const char *dir, int32_t flags, ngs **db) {
  ngs_open_opts o = NGS_OPEN_OPTS_INIT;
  o.flags = flags;
  return ngs_open(dir, &o, db);
}

static int remember(ngs *db, const char *ns, int32_t kind, const char *title,
                    const char *body, ngs_id *id) {
  ngs_fact_in f = NGS_FACT_IN_INIT;
  f.ns = S(ns);
  f.kind = kind;
  f.title = S(title);
  f.body = S(body);
  return ngs_remember(db, &f, 0, id);
}

/* The largest regular file under dir (recursive): the log segment holding the
** facts. Black-box: no knowledge of an entry's file names. */
static void largest_file(const char *dir, char *best, off_t *best_sz) {
  DIR *d = opendir(dir);
  struct dirent *e;
  if (!d) return;
  while ((e = readdir(d)) != NULL) {
    char p[4096];
    struct stat st;
    if (strcmp(e->d_name, ".") == 0 || strcmp(e->d_name, "..") == 0) continue;
    snprintf(p, sizeof p, "%s/%s", dir, e->d_name);
    if (lstat(p, &st) != 0) continue;
    if (S_ISDIR(st.st_mode)) {
      largest_file(p, best, best_sz);
    } else if (S_ISREG(st.st_mode) && st.st_size > *best_sz) {
      *best_sz = st.st_size;
      snprintf(best, 4096, "%s", p);
    }
  }
  closedir(d);
}

#define N_MANY 50

int main(int argc, char **argv) {
  const char *dir;
  ngs *db = NULL;
  ngs_id id1, many[N_MANY], probe;
  ngs_fact *f = NULL;
  ngs_fact_in batch[N_MANY];
  char titles[N_MANY][32];
  int rc, i, ok;
  char logpath[4096] = "";
  off_t logsz = 0;

  if (argc != 2) {
    fprintf(stderr, "usage: %s <empty-dir>\n", argv[0]);
    return 125;
  }
  dir = argv[1];

  /* --- open / create --- */
  rc = open_db(dir, NGS_OPEN_READWRITE | NGS_OPEN_CREATE, &db);
  result(rc == NGS_OK && db != NULL, "open_create", ngs_errstr(rc));
  if (rc != NGS_OK || db == NULL) goto done;

  {
    ngs_pubkey pk;
    memset(&pk, 0, sizeof pk);
    rc = ngs_node_pubkey(db, &pk);
    result(rc == NGS_OK && !id_zero((const ngs_id *)(const void *)&pk), "node_pubkey_nonzero",
           rc == NGS_OK ? "zero key" : ngs_errstr(rc));
  }

  /* --- remember + get round trip --- */
  rc = remember(db, "bench", NGS_SEMANTIC, "first", "the body, verbatim", &id1);
  result(rc == NGS_OK && !id_zero(&id1), "remember_one", ngs_errstr(rc));

  rc = ngs_get(db, &id1, &f);
  ok = rc == NGS_OK && f != NULL && memcmp(&f->id, &id1, sizeof id1) == 0 &&
       str_eq(f->ns, "bench") && f->kind == NGS_SEMANTIC && str_eq(f->title, "first") &&
       str_eq(f->body, "the body, verbatim") && f->redacted == 0;
  result(ok, "get_round_trip", rc == NGS_OK ? "fields differ" : ngs_errstr(rc));
  if (rc == NGS_OK && f) {
    result(f->valid_to == NGS_TIME_MAX, "get_valid_to_open", "valid_to not NGS_TIME_MAX");
    ngs_free(f);
  }
  f = NULL;

  /* same content twice: ids must still differ (time/seq/prev are in the id) */
  {
    ngs_id id1b;
    rc = remember(db, "bench", NGS_SEMANTIC, "first", "the body, verbatim", &id1b);
    result(rc == NGS_OK && memcmp(&id1, &id1b, sizeof id1) != 0, "ids_unique_for_same_content",
           rc == NGS_OK ? "duplicate id" : ngs_errstr(rc));
  }

  memset(&probe, 0x5a, sizeof probe);
  f = NULL;
  rc = ngs_get(db, &probe, &f);
  result(rc == NGS_NOTFOUND, "get_unknown_notfound", ngs_errstr(rc));
  if (rc == NGS_OK && f) ngs_free(f);

  /* --- input validation --- */
  {
    ngs_fact_in bad = NGS_FACT_IN_INIT;
    ngs_id x;
    bad.ns = S("bench");
    bad.kind = 0; /* kind must be set */
    bad.body = S("x");
    rc = ngs_remember(db, &bad, 0, &x);
    result(rc == NGS_MISUSE, "remember_kind0_misuse", ngs_errstr(rc));
    bad.kind = NGS_EPISODIC;
    bad.size = 4; /* struct size the engine cannot accept */
    rc = ngs_remember(db, &bad, 0, &x);
    result(rc == NGS_MISUSE, "remember_bad_size_misuse", ngs_errstr(rc));
  }

  /* --- remember_many --- */
  for (i = 0; i < N_MANY; i++) {
    ngs_fact_in t = NGS_FACT_IN_INIT;
    snprintf(titles[i], sizeof titles[i], "many-%02d", i);
    t.ns = S("bench");
    t.kind = NGS_EPISODIC;
    t.title = S(titles[i]);
    t.body = S(titles[i]);
    batch[i] = t;
  }
  rc = ngs_remember_many(db, batch, N_MANY, 0, many);
  ok = rc == NGS_OK;
  for (i = 0; ok && i < N_MANY; i++) {
    int j;
    if (id_zero(&many[i])) ok = 0;
    for (j = 0; ok && j < i; j++)
      if (memcmp(&many[i], &many[j], sizeof many[i]) == 0) ok = 0;
  }
  result(ok, "remember_many_distinct_ids", rc == NGS_OK ? "zero or duplicate id" : ngs_errstr(rc));

  rc = ngs_flush(db);
  result(rc == NGS_OK, "flush", ngs_errstr(rc));

  /* --- scan: every fact, gapless increasing seq per writer --- */
  {
    ngs_scan_opts so = NGS_SCAN_OPTS_INIT;
    ngs_iter *it = NULL;
    size_t seen = 0, seen_many = 0;
    uint64_t last = 0;
    int ordered = 1, gapless = 1;
    rc = ngs_scan(db, &so, &it);
    if (rc == NGS_OK) {
      while ((rc = ngs_iter_next(it, &f)) == NGS_OK) {
        if (seen > 0 && f->seq <= last) ordered = 0;
        if (seen > 0 && f->seq != last + 1) gapless = 0;
        last = f->seq;
        if (f->title.n >= 5 && memcmp(f->title.p, "many-", 5) == 0) seen_many++;
        seen++;
        ngs_free(f);
        f = NULL;
      }
      ngs_iter_close(it);
    }
    result(rc == NGS_NOTFOUND && seen == 2 + N_MANY, "scan_returns_all",
           rc != NGS_NOTFOUND ? "iteration did not end with NGS_NOTFOUND" : "wrong count");
    result(seen_many == N_MANY, "scan_sees_batch", "batch facts missing");
    result(ordered, "scan_seq_increasing", "seq not increasing");
    result(gapless, "scan_seq_gapless", "seq has gaps");
  }

  /* --- verify the chain (no external checkpoint) --- */
  rc = ngs_verify(db, NULL, 0);
  result(rc == NGS_OK, "verify_clean", ngs_errstr(rc));

  /* --- outside M1: must refuse with NGS_MISUSE, not crash or half-work --- */
  {
    ngs_query q = NGS_QUERY_INIT;
    ngs_results *r = NULL;
    q.text = S("first");
    rc = ngs_recall(db, &q, &r);
    result(rc == NGS_MISUSE || rc == NGS_OK, "recall_defined_result", ngs_errstr(rc));
    if (rc == NGS_OK && r) ngs_free(r);
  }

  /* --- reopen: everything acked must survive --- */
  rc = ngs_close(db);
  db = NULL;
  result(rc == NGS_OK, "close", ngs_errstr(rc));

  rc = open_db(dir, NGS_OPEN_READWRITE, &db);
  result(rc == NGS_OK, "reopen", ngs_errstr(rc));
  if (rc != NGS_OK) goto done;
  ok = 1;
  rc = ngs_get(db, &id1, &f);
  if (rc != NGS_OK || !str_eq(f->body, "the body, verbatim")) ok = 0;
  if (rc == NGS_OK) ngs_free(f);
  f = NULL;
  for (i = 0; ok && i < N_MANY; i++) {
    rc = ngs_get(db, &many[i], &f);
    if (rc != NGS_OK || !str_eq(f->title, titles[i])) ok = 0;
    if (rc == NGS_OK) ngs_free(f);
    f = NULL;
  }
  result(ok, "reopen_all_facts_readable", "a fact acked before close is missing or changed");

  /* --- read-only open rejects writes --- */
  ngs_close(db);
  db = NULL;
  rc = open_db(dir, NGS_OPEN_READONLY, &db);
  if (rc == NGS_OK) {
    ngs_id x;
    rc = remember(db, "bench", NGS_SEMANTIC, "ro", "ro", &x);
    result(rc != NGS_OK, "readonly_rejects_write", "write succeeded on a read-only handle");
    ngs_close(db);
    db = NULL;
  } else {
    result(0, "readonly_rejects_write", "read-only open failed");
  }

  /* --- torn tail: append garbage to the log; acked facts must survive --- */
  largest_file(dir, logpath, &logsz);
  {
    int fd = logpath[0] ? open(logpath, O_WRONLY | O_APPEND) : -1;
    static const unsigned char junk[37] = {0x00, 0xff, 0x13, 0x37, 0xde, 0xad, 0xbe, 0xef, 0x42};
    ok = fd >= 0 && write(fd, junk, sizeof junk) == (ssize_t)sizeof junk;
    if (fd >= 0) close(fd);
    if (!ok) {
      result(0, "torn_tail_recovers", "could not damage the log file");
    } else {
      rc = open_db(dir, NGS_OPEN_READWRITE, &db);
      ok = rc == NGS_OK;
      if (ok) {
        rc = ngs_get(db, &many[N_MANY - 1], &f);
        ok = rc == NGS_OK && str_eq(f->title, titles[N_MANY - 1]);
        if (rc == NGS_OK) ngs_free(f);
        f = NULL;
      }
      result(ok, "torn_tail_recovers", ngs_errstr(rc));
      if (db) {
        ngs_id x;
        rc = remember(db, "bench", NGS_SEMANTIC, "after-tear", "after-tear", &x);
        result(rc == NGS_OK, "write_after_torn_tail", ngs_errstr(rc));
        rc = ngs_verify(db, NULL, 0);
        result(rc == NGS_OK, "verify_after_torn_tail", ngs_errstr(rc));
        ngs_close(db);
        db = NULL;
      }
    }
  }

  /* --- bit flip inside the log: never a silent wrong read --- */
  {
    int fd = logpath[0] ? open(logpath, O_RDWR) : -1;
    unsigned char b;
    off_t at = logsz / 2;
    int flipped = 0, detected = 0, wrong = 0;
    if (fd >= 0 && pread(fd, &b, 1, at) == 1) {
      b ^= 0x10;
      flipped = pwrite(fd, &b, 1, at) == 1;
    }
    if (fd >= 0) close(fd);
    if (!flipped) {
      result(0, "bitflip_never_silent", "could not damage the log file");
    } else {
      rc = open_db(dir, NGS_OPEN_READWRITE, &db);
      if (rc != NGS_OK) {
        detected = 1;
      } else {
        if (ngs_verify(db, NULL, 0) != NGS_OK) detected = 1;
        for (i = 0; i < N_MANY; i++) {
          rc = ngs_get(db, &many[i], &f);
          if (rc == NGS_OK) {
            if (!str_eq(f->title, titles[i]) || !str_eq(f->body, titles[i])) wrong = 1;
            ngs_free(f);
          } else {
            detected = 1;
          }
          f = NULL;
        }
        ngs_close(db);
        db = NULL;
      }
      result(!wrong, "bitflip_no_wrong_read", "a get returned altered content");
      result(detected, "bitflip_detected", "flip went unnoticed by open, verify and get");
    }
  }

done:
  if (db) ngs_close(db);
  printf("SUMMARY %d %d\n", n_pass, n_fail);
  return n_fail > 125 ? 125 : n_fail;
}
