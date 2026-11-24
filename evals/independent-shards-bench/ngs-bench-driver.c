/* ngs-bench-driver.c — thin CLI over the NGS prototype for the independent
** Shards benchmark.
**
** Two modes, both parameterized (UDD HHT: every value that names a
** document, a query, or a tuning arrives as an argument):
**
**   ingest --store DIR --ns NS --doc FILE --title-prefix PREFIX --tags CSV
**     Split FILE on "## " section headers (the same rule as the fleet
**     shard_doc: first part is "Intro" when non-empty, chunks under 200
**     chars are skipped, bodies capped at 6000 chars), ingest the
**     sections as one atomic ngs_remember_many batch, print JSON
**     {"ingested": N, "sections": [...]}.
**
**   recall --store DIR --ns NS --query TEXT --k N --token-budget N
**          [--min-confidence F]
**     Run ngs_recall with the keyword arm only (vec NULL), print JSON
**     {"hits": [{"title","score","confidence","tokens","stub","body"}],
**      "abstained","arms_complete","timed_out","tokens_used",
**      "tokens_budget","best_confidence","min_confidence"}.
**
** The store is LOCAL ONLY (a directory under the bench dir). It never
** touches the fleet shards or the live node. Exit 0 on success, 1 on
** engine error (message on stderr as JSON).
*/
#define _POSIX_C_SOURCE 200809L /* strdup */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "ngs.h"

static void die(const char *what, ngs *db) {
  const char *m = db ? ngs_errmsg(db) : "no db";
  fprintf(stderr, "{\"error\": \"%s: %s\"}\n", what, m ? m : "?");
  exit(1);
}

static ngs_str S(const char *s) { ngs_str r = { s, strlen(s) }; return r; }

/* JSON-escape a byte string (UTF-8 passes through; control chars, quote
** and backslash are escaped). */
static void json_str(FILE *f, const char *p, size_t n) {
  fputc('"', f);
  for (size_t i = 0; i < n; i++) {
    unsigned char c = (unsigned char)p[i];
    switch (c) {
      case '"':  fputs("\\\"", f); break;
      case '\\': fputs("\\\\", f); break;
      case '\n': fputs("\\n", f); break;
      case '\r': fputs("\\r", f); break;
      case '\t': fputs("\\t", f); break;
      case '\b': fputs("\\b", f); break;
      case '\f': fputs("\\f", f); break;
      default:
        if (c < 0x20) fprintf(f, "\\u%04x", c);
        else fputc(c, f);
    }
  }
  fputc('"', f);
}

static char *read_file(const char *path, size_t *out_n) {
  FILE *f = fopen(path, "rb");
  if (!f) { fprintf(stderr, "{\"error\": \"cannot open %s\"}\n", path); exit(1); }
  fseek(f, 0, SEEK_END);
  long n = ftell(f);
  fseek(f, 0, SEEK_SET);
  if (n < 0) n = 0;
  char *buf = malloc((size_t)n + 1);
  if (!buf) { fprintf(stderr, "{\"error\": \"oom\"}\n"); exit(1); }
  if (n > 0 && fread(buf, 1, (size_t)n, f) != (size_t)n) {
    fprintf(stderr, "{\"error\": \"short read %s\"}\n", path); exit(1);
  }
  fclose(f);
  buf[n] = '\0';
  *out_n = (size_t)n;
  return buf;
}

/* Split text on lines starting with "## ". Returns section headers and
** bodies (body includes the "## " header line, mirroring shard_doc).
** The caller frees the returned arrays. */
typedef struct { char *head; char *body; size_t body_len; } section_t;

static section_t *split_sections(const char *text, size_t n, size_t *out_count) {
  size_t cap = 16, count = 0;
  section_t *secs = malloc(cap * sizeof *secs);
  size_t pos = 0;
  /* Find all "## " line starts. */
  size_t *starts = NULL; size_t nstarts = 0, scap = 0;
  size_t i = 0;
  while (i < n) {
    int at_line_start = (i == 0) || (text[i - 1] == '\n');
    if (at_line_start && i + 2 < n && text[i] == '#' && text[i + 1] == '#' &&
        text[i + 2] == ' ') {
      if (nstarts == scap) { scap = scap ? scap * 2 : 16; starts = realloc(starts, scap * sizeof *starts); }
      starts[nstarts++] = i;
    }
    i++;
  }
  /* Intro: text before the first header. */
  size_t first = nstarts ? starts[0] : n;
  if (first > 0) {
    /* strip leading/trailing whitespace for the length check only */
    size_t a = 0, b = first;
    while (a < b && (text[a] == ' ' || text[a] == '\n' || text[a] == '\r' || text[a] == '\t')) a++;
    while (b > a && (text[b-1] == ' ' || text[b-1] == '\n' || text[b-1] == '\r' || text[b-1] == '\t')) b--;
    if (b - a >= 200) {
      if (count == cap) { cap *= 2; secs = realloc(secs, cap * sizeof *secs); }
      secs[count].head = strdup("Intro");
      secs[count].body_len = first;
      secs[count].body = malloc(first + 1);
      memcpy(secs[count].body, text, first);
      secs[count].body[first] = '\0';
      count++;
    }
  }
  for (size_t s = 0; s < nstarts; s++) {
    size_t begin = starts[s];
    size_t end = (s + 1 < nstarts) ? starts[s + 1] : n;
    /* header = first line after "## " */
    size_t eol = begin;
    while (eol < end && text[eol] != '\n') eol++;
    size_t hlen = (eol > begin + 3) ? (eol - (begin + 3)) : 0;
    /* strip trailing whitespace from the header */
    while (hlen > 0 && (text[begin + 3 + hlen - 1] == ' ' || text[begin + 3 + hlen - 1] == '\r' || text[begin + 3 + hlen - 1] == '\t')) hlen--;
    /* body length check on stripped content */
    size_t a = begin, b = end;
    while (a < b && (text[a] == ' ' || text[a] == '\n' || text[a] == '\r' || text[a] == '\t')) a++;
    while (b > a && (text[b-1] == ' ' || text[b-1] == '\n' || text[b-1] == '\r' || text[b-1] == '\t')) b--;
    if (b - a < 200) continue;
    if (count == cap) { cap *= 2; secs = realloc(secs, cap * sizeof *secs); }
    secs[count].head = malloc(hlen + 1);
    memcpy(secs[count].head, text + begin + 3, hlen);
    secs[count].head[hlen] = '\0';
    secs[count].body_len = end - begin;
    secs[count].body = malloc(end - begin + 1);
    memcpy(secs[count].body, text + begin, end - begin);
    secs[count].body[end - begin] = '\0';
    count++;
  }
  free(starts);
  (void)pos;
  *out_count = count;
  return secs;
}

static ngs *open_store(const char *dir) {
  ngs_open_opts o = NGS_OPEN_OPTS_INIT;
  o.flags = NGS_OPEN_CREATE | NGS_OPEN_READWRITE;
  ngs *db = NULL;
  int rc = ngs_open(dir, &o, &db);
  if (rc != NGS_OK) die("ngs_open", db);
  return db;
}

static const char *arg_val(int argc, char **argv, const char *name, const char *dflt) {
  for (int i = 1; i + 1 < argc; i++)
    if (strcmp(argv[i], name) == 0) return argv[i + 1];
  return dflt;
}

static int arg_flag(int argc, char **argv, const char *name) {
  for (int i = 1; i < argc; i++)
    if (strcmp(argv[i], name) == 0) return 1;
  return 0;
}

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "usage: %s ingest|recall [options]\n", argv[0]);
    return 1;
  }
  const char *mode = argv[1];
  const char *store = arg_val(argc, argv, "--store", NULL);
  const char *ns = arg_val(argc, argv, "--ns", "bench");
  if (!store) { fprintf(stderr, "{\"error\": \"--store required\"}\n"); return 1; }

  if (strcmp(mode, "ingest") == 0) {
    const char *doc = arg_val(argc, argv, "--doc", NULL);
    const char *prefix = arg_val(argc, argv, "--title-prefix", "Bench doc");
    const char *tags_csv = arg_val(argc, argv, "--tags", "");
    if (!doc) { fprintf(stderr, "{\"error\": \"--doc required\"}\n"); return 1; }
    size_t n = 0;
    char *text = read_file(doc, &n);
    size_t nsec = 0;
    section_t *secs = split_sections(text, n, &nsec);
    /* tags: split CSV */
    ngs_str tags[16]; size_t n_tags = 0;
    char *tc = strdup(tags_csv);
    for (char *t = strtok(tc, ","); t && n_tags < 16; t = strtok(NULL, ",")) {
      while (*t == ' ') t++;
      size_t L = strlen(t);
      while (L && t[L-1] == ' ') t[--L] = '\0';
      if (L) { tags[n_tags].p = t; tags[n_tags].n = L; n_tags++; }
    }
    ngs *db = open_store(store);
    ngs_fact_in *ins = calloc(nsec, sizeof *ins);
    ngs_id *ids = calloc(nsec, sizeof *ids);
    char **titles = calloc(nsec, sizeof *titles);
    for (size_t i = 0; i < nsec; i++) {
      size_t tlen = strlen(prefix) + 3 + strlen(secs[i].head) + 1;
      titles[i] = malloc(tlen);
      snprintf(titles[i], tlen, "%s — %s", prefix, secs[i].head);
      ins[i] = (ngs_fact_in)NGS_FACT_IN_INIT;
      ins[i].ns = S(ns);
      ins[i].kind = NGS_SEMANTIC;
      ins[i].title = S(titles[i]);
      size_t blen = secs[i].body_len > 6000 ? 6000 : secs[i].body_len;
      /* body as an ngs_str: cap at 6000 bytes, mirroring shard_doc */
      ins[i].body.p = secs[i].body;
      ins[i].body.n = blen;
      ins[i].tags = tags;
      ins[i].n_tags = n_tags;
      ins[i].salience0 = -1;
    }
    int rc = ngs_remember_many(db, ins, nsec, 0, ids);
    if (rc != NGS_OK) die("ngs_remember_many", db);
    printf("{\"ingested\": %zu, \"sections\": [", nsec);
    for (size_t i = 0; i < nsec; i++) {
      if (i) printf(", ");
      json_str(stdout, titles[i], strlen(titles[i]));
    }
    printf("]}\n");
    ngs_close(db);
    return 0;
  }

  if (strcmp(mode, "recall") == 0) {
    const char *query = arg_val(argc, argv, "--query", NULL);
    const char *k_s = arg_val(argc, argv, "--k", "5");
    const char *tb_s = arg_val(argc, argv, "--token-budget", "1000");
    const char *mc_s = arg_val(argc, argv, "--min-confidence", NULL);
    if (!query) { fprintf(stderr, "{\"error\": \"--query required\"}\n"); return 1; }
    ngs *db = open_store(store);
    ngs_query q = NGS_QUERY_INIT;
    q.ns = S(ns);
    q.text = S(query);
    q.vec = NULL; /* keyword arm only */
    q.k = (uint32_t)atoi(k_s);
    q.token_budget = (uint32_t)atoi(tb_s);
    if (mc_s) q.min_confidence = (float)atof(mc_s);
    ngs_results *res = NULL;
    int rc = ngs_recall(db, &q, &res);
    if (rc != NGS_OK) die("ngs_recall", db);
    printf("{\"hits\": [");
    for (size_t i = 0; i < res->n; i++) {
      ngs_hit *h = &res->hits[i];
      if (i) printf(", ");
      printf("{\"title\": ");
      json_str(stdout, h->title.p, h->title.n);
      printf(", \"score\": %.6g, \"confidence\": %.6g, \"tokens\": %u, "
             "\"stub\": %d, \"tokens_estimated\": %d, \"arm_kw\": %.6g, "
             "\"arm_vec\": %.6g, \"arm_recency\": %.6g, \"arm_salience\": %.6g, "
             "\"arm_link\": %.6g, \"body\": ",
             (double)h->score, (double)h->confidence, h->tokens, h->stub,
             h->tokens_estimated, (double)h->arm[NGS_ARM_KW],
             (double)h->arm[NGS_ARM_VEC], (double)h->arm[NGS_ARM_RECENCY],
             (double)h->arm[NGS_ARM_SALIENCE], (double)h->arm[NGS_ARM_LINK]);
      json_str(stdout, h->body.p, h->body.n);
      printf("}");
    }
    printf("], \"abstained\": %d, \"arms_complete\": %u, \"timed_out\": %d, "
           "\"tokens_used\": %u, \"tokens_budget\": %u, "
           "\"best_confidence\": %.6g, \"min_confidence\": %.6g, "
           "\"confidence_calibrated\": %d, \"elapsed_us\": %u}\n",
           res->abstained, res->arms_complete, res->timed_out,
           res->tokens_used, res->tokens_budget,
           (double)res->best_confidence, (double)res->min_confidence,
           res->confidence_calibrated, res->elapsed_us);
    ngs_free(res);
    ngs_close(db);
    return 0;
  }

  fprintf(stderr, "{\"error\": \"unknown mode %s\"}\n", mode);
  (void)arg_flag;
  return 1;
}
