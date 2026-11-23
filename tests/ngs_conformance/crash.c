/*
** Black-box crash injection for an NGS engine (PR 1199 ngs.h, draft 0.3.1).
**
** Each round forks a writer that appends batches with ngs_remember_many and,
** after each call returns NGS_OK, records the acked ids in an ack file. The
** parent SIGKILLs the writer at a random moment, then reopens the database and
** checks, against everything acked so far:
**   crash_reopen          the database opens after every kill
**   crash_acked_survive   every acked fact is readable and unchanged
**   crash_batches_atomic  every batch is present in full or not at all
**   crash_verify          ngs_verify succeeds after every kill
**   crash_writes_resume   a fresh write succeeds after every kill
** Prints one PASS/FAIL line per check, then "SUMMARY <pass> <fail> kills=<n>
** acked=<n>". Exit status is the failure count.
**
** Limitation: SIGKILL kills the process, not the machine, so the page cache
** survives. This tests crash consistency of the engine's own write path, not
** fsync placement under power loss; that needs a VFS fault layer inside each
** entry and stays with each entry's own crash suite.
**
** Usage: crash <empty-scratch-dir> [rounds] [seed]
*/
#define _POSIX_C_SOURCE 200809L
#include "ngs.h"

#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define K 5               /* facts per batch */
#define MAX_ACKS 200000   /* acked batches tracked across all rounds */

typedef struct {
  uint32_t round, batch;
  ngs_id ids[K];
} ack_rec;

static ack_rec *acks;
static size_t n_acks;

static ngs_str S(const char *s) {
  ngs_str r;
  r.p = s;
  r.n = strlen(s);
  return r;
}

static int str_eq(ngs_str a, const char *b) {
  return a.n == strlen(b) && (a.n == 0 || memcmp(a.p, b, a.n) == 0);
}

static int open_db(const char *dir, ngs **db) {
  ngs_open_opts o = NGS_OPEN_OPTS_INIT;
  o.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  return ngs_open(dir, &o, db);
}

static void title_for(char *buf, size_t n, uint32_t round, uint32_t batch, int j) {
  snprintf(buf, n, "r%u-b%u-f%d", (unsigned)round, (unsigned)batch, j);
}

/* Writer: append batches forever, logging each acked batch. Never returns. */
static void writer(const char *dir, const char *ackpath, uint32_t round) {
  ngs *db = NULL;
  int fd = open(ackpath, O_WRONLY | O_APPEND | O_CREAT, 0600);
  uint32_t b;
  if (fd < 0 || open_db(dir, &db) != NGS_OK) _exit(3);
  for (b = 0;; b++) {
    ngs_fact_in in[K];
    char titles[K][48];
    ack_rec r;
    int j;
    for (j = 0; j < K; j++) {
      ngs_fact_in t = NGS_FACT_IN_INIT;
      title_for(titles[j], sizeof titles[j], round, b, j);
      t.ns = S("crash");
      t.kind = NGS_EPISODIC;
      t.title = S(titles[j]);
      t.body = S(titles[j]);
      in[j] = t;
    }
    if (ngs_remember_many(db, in, K, 0, r.ids) != NGS_OK) _exit(4);
    r.round = round;
    r.batch = b;
    if (write(fd, &r, sizeof r) != (ssize_t)sizeof r) _exit(5);
  }
}

/* Load the ack log; a record cut short by the kill is ignored (never acked
** from the checker's point of view, since its write did not complete). */
static void load_acks(const char *ackpath) {
  FILE *f = fopen(ackpath, "rb");
  n_acks = 0;
  if (!f) return;
  while (n_acks < MAX_ACKS && fread(&acks[n_acks], sizeof acks[0], 1, f) == 1) n_acks++;
  fclose(f);
}

int main(int argc, char **argv) {
  const char *dir;
  char ackpath[4096];
  int rounds, r, i;
  unsigned seed;
  int bad_open = 0, bad_ack = 0, bad_atomic = 0, bad_verify = 0, bad_resume = 0;
  int n_pass = 0, n_fail = 0, kills = 0;
  char why_ack[256] = "", why_atomic[256] = "";

  if (argc < 2) {
    fprintf(stderr, "usage: %s <empty-dir> [rounds] [seed]\n", argv[0]);
    return 125;
  }
  dir = argv[1];
  rounds = argc > 2 ? atoi(argv[2]) : 30;
  seed = argc > 3 ? (unsigned)strtoul(argv[3], NULL, 10) : 1085u;
  srand(seed);
  snprintf(ackpath, sizeof ackpath, "%s.acks", dir);
  unlink(ackpath);
  acks = calloc(MAX_ACKS, sizeof *acks);
  if (!acks) return 125;

  for (r = 0; r < rounds; r++) {
    pid_t pid;
    struct timespec ts;
    ngs *db = NULL;
    int rc;
    long us = 2000 + (rand() % 60000); /* 2 to 62 ms of writing */

    fflush(stdout);
    pid = fork();
    if (pid < 0) return 125;
    if (pid == 0) writer(dir, ackpath, (uint32_t)r);
    ts.tv_sec = us / 1000000;
    ts.tv_nsec = (us % 1000000) * 1000;
    nanosleep(&ts, NULL);
    kill(pid, SIGKILL);
    waitpid(pid, NULL, 0);
    kills++;

    load_acks(ackpath);
    rc = open_db(dir, &db);
    if (rc != NGS_OK) {
      bad_open++;
      continue;
    }

    /* every acked fact survives, unchanged */
    for (i = 0; i < (int)n_acks; i++) {
      int j;
      for (j = 0; j < K; j++) {
        ngs_fact *f = NULL;
        char t[48];
        title_for(t, sizeof t, acks[i].round, acks[i].batch, j);
        rc = ngs_get(db, &acks[i].ids[j], &f);
        if (rc != NGS_OK || !str_eq(f->title, t) || !str_eq(f->body, t)) {
          if (!bad_ack)
            snprintf(why_ack, sizeof why_ack, "round %d: acked %s %s", r, t,
                     rc == NGS_OK ? "changed" : ngs_errstr(rc));
          bad_ack++;
        }
        if (rc == NGS_OK) ngs_free(f);
      }
    }

    /* atomicity: count facts per (round,batch) seen by scan; must be K */
    {
      ngs_scan_opts so = NGS_SCAN_OPTS_INIT;
      ngs_iter *it = NULL;
      ngs_fact *f = NULL;
      /* counts[round][batch] packed as a small open-addressed table */
      enum { CAP = 1 << 17 };
      static uint64_t key[CAP];
      static int cnt[CAP];
      memset(key, 0, sizeof key);
      memset(cnt, 0, sizeof cnt);
      so.ns = S("crash");
      if (ngs_scan(db, &so, &it) == NGS_OK) {
        while (ngs_iter_next(it, &f) == NGS_OK) {
          unsigned rr, bb;
          int jj;
          char tb[64];
          size_t n = f->title.n < sizeof tb - 1 ? f->title.n : sizeof tb - 1;
          memcpy(tb, f->title.p, n);
          tb[n] = 0;
          if (sscanf(tb, "r%u-b%u-f%d", &rr, &bb, &jj) == 3) {
            uint64_t k = ((uint64_t)rr << 32 | bb) + 1;
            size_t h = (size_t)((k * 0x9E3779B97F4A7C15ull) >> 47) & (CAP - 1);
            while (key[h] && key[h] != k) h = (h + 1) & (CAP - 1);
            key[h] = k;
            cnt[h]++;
          }
          ngs_free(f);
          f = NULL;
        }
        ngs_iter_close(it);
      }
      for (i = 0; i < CAP; i++) {
        if (key[i] && cnt[i] != K) {
          if (!bad_atomic)
            snprintf(why_atomic, sizeof why_atomic, "round %d: batch r%u-b%u has %d of %d facts", r,
                     (unsigned)((key[i] - 1) >> 32), (unsigned)((key[i] - 1) & 0xffffffffu), cnt[i], K);
          bad_atomic++;
        }
      }
    }

    if (ngs_verify(db, NULL, 0) != NGS_OK) bad_verify++;
    {
      ngs_fact_in t = NGS_FACT_IN_INIT;
      ngs_id x;
      t.ns = S("crash-resume");
      t.kind = NGS_SEMANTIC;
      t.title = S("resume");
      t.body = S("resume");
      if (ngs_remember(db, &t, 0, &x) != NGS_OK) bad_resume++;
    }
    ngs_close(db);
  }

#define REPORT(cond, name, why)                    \
  do {                                             \
    if (cond) {                                    \
      printf("PASS %s\n", name);                   \
      n_pass++;                                    \
    } else {                                       \
      printf("FAIL %s: %s\n", name, why);          \
      n_fail++;                                    \
    }                                              \
  } while (0)
  {
    char w[128];
    snprintf(w, sizeof w, "%d of %d reopens failed", bad_open, kills);
    REPORT(bad_open == 0, "crash_reopen", w);
    REPORT(bad_ack == 0, "crash_acked_survive", why_ack);
    REPORT(bad_atomic == 0, "crash_batches_atomic", why_atomic);
    snprintf(w, sizeof w, "verify failed after %d kills", bad_verify);
    REPORT(bad_verify == 0, "crash_verify", w);
    snprintf(w, sizeof w, "write failed after %d kills", bad_resume);
    REPORT(bad_resume == 0, "crash_writes_resume", w);
  }
  printf("SUMMARY %d %d kills=%d acked=%zu\n", n_pass, n_fail, kills, n_acks * K);
  free(acks);
  unlink(ackpath);
  return n_fail;
}
