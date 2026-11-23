/*
** smoke_posix.c -- the amalgamation on a real filesystem: create, write a
** batch and singles across segments, reopen, verify, lock exclusion, and a
** torn tail cut by hand. Usage: smoke_posix <fresh directory>
*/
#include "ngs.h"
#include <stdio.h>
#include <string.h>

static int fails;
#define CHECK(c) do { if (!(c)) { fails++; fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); } } while (0)

int main(int argc, char **argv) {
  ngs_open_opts o = NGS_OPEN_OPTS_INIT;
  ngs *db = NULL, *db2 = NULL;
  ngs_id ids[40];
  ngs_fact *f = NULL;
  ngs_stats_t st = NGS_STATS_INIT;
  char seg[512];
  FILE *fp;
  long sz;
  int i;
  if (argc != 2) return 2;
  o.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  o.segment_bytes = 4096;
  CHECK(ngs_open(argv[1], &o, &db) == NGS_OK);
  for (i = 0; i < 40; i++) {
    ngs_fact_in in = NGS_FACT_IN_INIT;
    char body[120];
    snprintf(body, sizeof body, "smoke fact %d: the deploy region for project kestrel is us-east-2", i);
    in.ns.p = "kestrel"; in.ns.n = 7; in.kind = NGS_EPISODIC;
    in.title.p = "smoke"; in.title.n = 5;
    in.body.p = body; in.body.n = strlen(body);
    CHECK(ngs_remember(db, &in, i % 5 ? NGS_WRITE_NO_SYNC : 0, &ids[i]) == NGS_OK);
  }
  CHECK(ngs_flush(db) == NGS_OK);
  o.flags = NGS_OPEN_READWRITE;
  CHECK(ngs_open(argv[1], &o, &db2) == NGS_BUSY);     /* fcntl lock held */
  ngs_close(db2);
  CHECK(ngs_close(db) == NGS_OK);
  CHECK(ngs_open(argv[1], &o, &db) == NGS_OK);
  CHECK(ngs_verify(db, NULL, 0) == NGS_OK);
  CHECK(ngs_stats(db, &st) == NGS_OK && st.facts == 40);
  CHECK(ngs_get(db, &ids[39], &f) == NGS_OK && f && f->seq == 40);
  ngs_free(f);
  ngs_close(db);
  /* cut the last segment mid-record: open truncates the torn tail */
  for (i = 1;; i++) {
    snprintf(seg, sizeof seg, "%s/log/%06d.seg", argv[1], i + 1);
    fp = fopen(seg, "rb");
    if (!fp) break;
    fclose(fp);
  }
  snprintf(seg, sizeof seg, "%s/log/%06d.seg", argv[1], i);
  fp = fopen(seg, "r+b");
  CHECK(fp != NULL);
  if (fp) {
    fseek(fp, 0, SEEK_END);
    sz = ftell(fp);
    fclose(fp);
    if (sz > 80) {
      fp = fopen(seg, "r+b");
      /* rewrite the file shorter by 7 bytes: a classic torn tail */
      {
        static char buf[1 << 16];
        size_t n = fread(buf, 1, (size_t)sz, fp);
        fclose(fp);
        fp = fopen(seg, "wb");
        fwrite(buf, 1, n - 7, fp);
        fclose(fp);
      }
    }
  }
  CHECK(ngs_open(argv[1], &o, &db) == NGS_OK);
  CHECK(ngs_verify(db, NULL, 0) == NGS_OK);
  CHECK(ngs_stats(db, &st) == NGS_OK && st.facts == 39);
  CHECK(ngs_get(db, &ids[38], &f) == NGS_OK);
  ngs_free(f);
  ngs_close(db);
  printf("posix smoke: %s\n", fails ? "FAILED" : "ok (40 facts, reopen, lock, torn tail)");
  return fails ? 1 : 0;
}
