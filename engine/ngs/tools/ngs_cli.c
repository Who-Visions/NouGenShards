/*
** ngs_cli.c -- JSON command line over the public ngs.h API.
**
** Built for the NGS console (apps/ngs-console): every command prints exactly
** one JSON object on stdout and exits 0 when the engine call worked, 1 when it
** did not. The console's API routes spawn this binary; nothing here links
** anything but the public header and libnougenshards.a.
**
** Usage:
**   ngs_cli version
**   ngs_cli <dir> stats
**   ngs_cli <dir> remember --ns NS --kind episodic|semantic|procedural
**                          --title TITLE --body BODY [--tag TAG]...
**   ngs_cli <dir> scan [--ns NS] [--limit N]
**   ngs_cli <dir> get <64-hex id>
**   ngs_cli <dir> verify
**   ngs_cli <dir> recall --q TEXT [--ns NS] [--k N]
**   ngs_cli <dir> bench N
**
** Strict ISO C11 plus the public header. Timing uses timespec_get (C11).
*/
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "ngs.h"

#define MAX_TAGS 16

/* ---------- JSON output ---------- */

static void json_str(const char *p, size_t n) {
  size_t i;
  putchar('"');
  for (i = 0; i < n; i++) {
    unsigned char c = (unsigned char)p[i];
    switch (c) {
      case '"':  fputs("\\\"", stdout); break;
      case '\\': fputs("\\\\", stdout); break;
      case '\n': fputs("\\n", stdout); break;
      case '\r': fputs("\\r", stdout); break;
      case '\t': fputs("\\t", stdout); break;
      default:
        if (c < 0x20) printf("\\u%04x", c);
        else putchar((int)c);
    }
  }
  putchar('"');
}

static void json_cstr(const char *s) { json_str(s ? s : "", s ? strlen(s) : 0); }

static void hex32(const uint8_t *b, char out[65]) {
  static const char d[] = "0123456789abcdef";
  int i;
  for (i = 0; i < 32; i++) {
    out[2 * i] = d[b[i] >> 4];
    out[2 * i + 1] = d[b[i] & 15];
  }
  out[64] = 0;
}

static int unhex32(const char *s, uint8_t *b) {
  int i;
  if (strlen(s) != 64) return 0;
  for (i = 0; i < 64; i++) {
    char c = s[i];
    int v = (c >= '0' && c <= '9') ? c - '0'
          : (c >= 'a' && c <= 'f') ? c - 'a' + 10
          : (c >= 'A' && c <= 'F') ? c - 'A' + 10 : -1;
    if (v < 0) return 0;
    if (i % 2 == 0) b[i / 2] = (uint8_t)(v << 4);
    else b[i / 2] |= (uint8_t)v;
  }
  return 1;
}

static double now_ms(void) {
  struct timespec ts;
  if (timespec_get(&ts, TIME_UTC) != TIME_UTC) return 0.0;
  return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1e6;
}

static const char *kind_name(int32_t k) {
  switch (k) {
    case NGS_EPISODIC: return "episodic";
    case NGS_SEMANTIC: return "semantic";
    case NGS_PROCEDURAL: return "procedural";
    default: return "unknown";
  }
}

static int32_t kind_parse(const char *s) {
  if (!s) return 0;
  if (strcmp(s, "episodic") == 0) return NGS_EPISODIC;
  if (strcmp(s, "semantic") == 0) return NGS_SEMANTIC;
  if (strcmp(s, "procedural") == 0) return NGS_PROCEDURAL;
  return 0;
}

static int fail(ngs *db, const char *op, int rc) {
  printf("{\"ok\":false,\"op\":");
  json_cstr(op);
  printf(",\"rc\":%d,\"code\":", rc);
  json_cstr(ngs_errstr(rc));
  printf(",\"error\":");
  json_cstr(db ? ngs_errmsg(db) : ngs_errstr(rc));
  printf("}\n");
  return 1;
}

static void print_fact(const ngs_fact *f) {
  char id[65];
  size_t i;
  hex32(f->id.b, id);
  printf("{\"id\":\"%s\",\"ns\":", id);
  json_str(f->ns.p, f->ns.n);
  printf(",\"kind\":\"%s\",\"seq\":%llu,\"t_event_us\":%lld,\"t_record_us\":%lld,\"title\":",
         kind_name(f->kind), (unsigned long long)f->seq, (long long)f->t_event,
         (long long)f->t_record);
  json_str(f->title.p, f->title.n);
  printf(",\"body\":");
  json_str(f->body.p, f->body.n);
  printf(",\"tags\":[");
  for (i = 0; i < f->n_tags; i++) {
    if (i) putchar(',');
    json_str(f->tags[i].p, f->tags[i].n);
  }
  printf("],\"invalidated\":%s,\"redacted\":%s}",
         f->valid_to != NGS_TIME_MAX ? "true" : "false", f->redacted ? "true" : "false");
}

static const char *arg_value(int argc, char **argv, const char *name) {
  int i;
  for (i = 0; i + 1 < argc; i++)
    if (strcmp(argv[i], name) == 0) return argv[i + 1];
  return NULL;
}

static int open_db(const char *dir, ngs **db) {
  ngs_open_opts o = NGS_OPEN_OPTS_INIT;
  o.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  return ngs_open(dir, &o, db);
}

/* ---------- commands ---------- */

static int cmd_stats(ngs *db) {
  ngs_iter *it = NULL;
  ngs_fact *f = NULL;
  ngs_pubkey pk;
  char pkhex[65];
  unsigned long long facts = 0, bytes = 0;
  int rc;
  double t0 = now_ms();
  if ((rc = ngs_node_pubkey(db, &pk)) != NGS_OK) return fail(db, "stats", rc);
  hex32(pk.b, pkhex);
  if ((rc = ngs_scan(db, NULL, &it)) != NGS_OK) return fail(db, "stats", rc);
  while (ngs_iter_next(it, &f) == NGS_OK) {
    facts++;
    bytes += (unsigned long long)(f->title.n + f->body.n);
    ngs_free(f);
    f = NULL;
  }
  ngs_iter_close(it);
  printf("{\"ok\":true,\"op\":\"stats\",\"version\":");
  json_cstr(ngs_libversion());
  printf(",\"node_pubkey\":\"%s\",\"facts\":%llu,\"text_bytes\":%llu,\"scan_ms\":%.3f}\n",
         pkhex, facts, bytes, now_ms() - t0);
  return 0;
}

static int cmd_remember(ngs *db, int argc, char **argv) {
  ngs_fact_in in = NGS_FACT_IN_INIT;
  ngs_str tags[MAX_TAGS];
  size_t n_tags = 0;
  ngs_id id;
  char idhex[65];
  const char *ns = arg_value(argc, argv, "--ns");
  const char *title = arg_value(argc, argv, "--title");
  const char *body = arg_value(argc, argv, "--body");
  int32_t kind = kind_parse(arg_value(argc, argv, "--kind"));
  double t0;
  int i, rc;
  if (!ns || !title || !body || !kind) {
    printf("{\"ok\":false,\"op\":\"remember\",\"error\":\"need --ns, --kind, --title and --body\"}\n");
    return 1;
  }
  for (i = 0; i + 1 < argc && n_tags < MAX_TAGS; i++)
    if (strcmp(argv[i], "--tag") == 0) {
      tags[n_tags].p = argv[i + 1];
      tags[n_tags].n = strlen(argv[i + 1]);
      n_tags++;
    }
  in.ns.p = ns; in.ns.n = strlen(ns);
  in.kind = kind;
  in.title.p = title; in.title.n = strlen(title);
  in.body.p = body; in.body.n = strlen(body);
  in.tags = n_tags ? tags : NULL;
  in.n_tags = n_tags;
  t0 = now_ms();
  if ((rc = ngs_remember(db, &in, 0, &id)) != NGS_OK) return fail(db, "remember", rc);
  hex32(id.b, idhex);
  printf("{\"ok\":true,\"op\":\"remember\",\"id\":\"%s\",\"durable\":true,\"ms\":%.3f}\n",
         idhex, now_ms() - t0);
  return 0;
}

static int cmd_scan(ngs *db, int argc, char **argv) {
  ngs_scan_opts so = NGS_SCAN_OPTS_INIT;
  ngs_iter *it = NULL;
  ngs_fact *f = NULL;
  ngs_fact **ring;
  const char *ns = arg_value(argc, argv, "--ns");
  const char *lim = arg_value(argc, argv, "--limit");
  size_t limit = lim ? (size_t)strtoul(lim, NULL, 10) : 50, head = 0, count = 0, total = 0, i;
  int rc;
  if (limit == 0 || limit > 500) limit = 50;
  if (ns) { so.ns.p = ns; so.ns.n = strlen(ns); }
  ring = (ngs_fact **)calloc(limit, sizeof *ring);
  if (!ring) return fail(db, "scan", NGS_NOMEM);
  if ((rc = ngs_scan(db, &so, &it)) != NGS_OK) { free(ring); return fail(db, "scan", rc); }
  /* keep the newest `limit` facts in log order */
  while (ngs_iter_next(it, &f) == NGS_OK) {
    if (ring[head]) ngs_free(ring[head]);
    ring[head] = f;
    f = NULL;
    head = (head + 1) % limit;
    if (count < limit) count++;
    total++;
  }
  ngs_iter_close(it);
  printf("{\"ok\":true,\"op\":\"scan\",\"total\":%llu,\"facts\":[", (unsigned long long)total);
  for (i = 0; i < count; i++) {
    size_t at = (head + limit - count + i) % limit;
    if (i) putchar(',');
    print_fact(ring[at]);
    ngs_free(ring[at]);
  }
  printf("]}\n");
  free(ring);
  return 0;
}

static int cmd_get(ngs *db, const char *hex) {
  ngs_id id;
  ngs_fact *f = NULL;
  int rc;
  if (!hex || !unhex32(hex, id.b)) {
    printf("{\"ok\":false,\"op\":\"get\",\"error\":\"need a 64-hex fact id\"}\n");
    return 1;
  }
  if ((rc = ngs_get(db, &id, &f)) != NGS_OK) return fail(db, "get", rc);
  printf("{\"ok\":true,\"op\":\"get\",\"fact\":");
  print_fact(f);
  printf("}\n");
  ngs_free(f);
  return 0;
}

static int cmd_verify(ngs *db) {
  uint8_t *ck = NULL;
  size_t cklen = 0;
  double t0 = now_ms(), t1, t2;
  int rc = ngs_verify(db, NULL, 0);
  t1 = now_ms();
  if (rc != NGS_OK) return fail(db, "verify", rc);
  if ((rc = ngs_checkpoint(db, &ck, &cklen)) != NGS_OK) return fail(db, "checkpoint", rc);
  rc = ngs_verify(db, ck, cklen);
  t2 = now_ms();
  ngs_free(ck);
  if (rc != NGS_OK) return fail(db, "verify_checkpoint", rc);
  printf("{\"ok\":true,\"op\":\"verify\",\"chain_and_signatures\":\"ok\",\"checkpoint\":\"ok\","
         "\"checkpoint_bytes\":%llu,\"verify_ms\":%.3f,\"checkpoint_verify_ms\":%.3f}\n",
         (unsigned long long)cklen, t1 - t0, t2 - t1);
  return 0;
}

static int cmd_recall(ngs *db, int argc, char **argv) {
  ngs_query q = NGS_QUERY_INIT;
  ngs_results *r = NULL;
  const char *text = arg_value(argc, argv, "--q");
  const char *ns = arg_value(argc, argv, "--ns");
  const char *k = arg_value(argc, argv, "--k");
  size_t i;
  int rc;
  char idhex[65];
  if (!text) {
    printf("{\"ok\":false,\"op\":\"recall\",\"error\":\"need --q\"}\n");
    return 1;
  }
  q.text.p = text; q.text.n = strlen(text);
  if (ns) { q.ns.p = ns; q.ns.n = strlen(ns); }
  if (k) q.k = (uint32_t)strtoul(k, NULL, 10);
  if ((rc = ngs_recall(db, &q, &r)) != NGS_OK) return fail(db, "recall", rc);
  printf("{\"ok\":true,\"op\":\"recall\",\"abstained\":%s,\"timed_out\":%s,\"elapsed_us\":%u,"
         "\"best_confidence\":%.4f,\"hits\":[",
         r->abstained ? "true" : "false", r->timed_out ? "true" : "false",
         (unsigned)r->elapsed_us, (double)r->best_confidence);
  for (i = 0; i < r->n; i++) {
    const ngs_hit *h = &r->hits[i];
    int a;
    hex32(h->id.b, idhex);
    if (i) putchar(',');
    printf("{\"id\":\"%s\",\"score\":%.4f,\"confidence\":%.4f,\"title\":", idhex,
           (double)h->score, (double)h->confidence);
    json_str(h->title.p, h->title.n);
    printf(",\"arms\":[");
    for (a = 0; a < NGS_N_ARMS; a++) printf("%s%.4f", a ? "," : "", (double)h->arm[a]);
    printf("]}");
  }
  printf("]}\n");
  ngs_free(r);
  return 0;
}

/* Bulk ingest N facts in batches of 1000 (NO_SYNC, then one flush), then
** scan them all back and verify the chain. Run it on a scratch directory. */
static int cmd_bench(ngs *db, const char *nstr) {
  enum { BATCH = 1000 };
  static ngs_fact_in in[BATCH];
  static ngs_id ids[BATCH];
  static char titles[BATCH][48];
  static const char body[] =
      "NGS bench fact. Signed, hash-chained, append-only; BLAKE3 id, Ed25519 signature, CRC32C framing.";
  unsigned long n = nstr ? strtoul(nstr, NULL, 10) : 10000, done = 0, scanned = 0;
  double t0, t_write, t_flush, t_scan, t_verify;
  ngs_iter *it = NULL;
  ngs_fact *f = NULL;
  int rc;
  size_t i;
  if (n == 0 || n > 200000) n = 10000;
  t0 = now_ms();
  while (done < n) {
    size_t m = (n - done) < BATCH ? (size_t)(n - done) : BATCH;
    for (i = 0; i < m; i++) {
      ngs_fact_in tmp = NGS_FACT_IN_INIT;
      int len = snprintf(titles[i], sizeof titles[i], "bench fact %lu", done + i);
      in[i] = tmp;
      in[i].ns.p = "bench"; in[i].ns.n = 5;
      in[i].kind = NGS_EPISODIC;
      in[i].title.p = titles[i]; in[i].title.n = (size_t)(len > 0 ? len : 0);
      in[i].body.p = body; in[i].body.n = sizeof body - 1;
    }
    if ((rc = ngs_remember_many(db, in, m, NGS_WRITE_NO_SYNC, ids)) != NGS_OK)
      return fail(db, "bench_write", rc);
    done += m;
  }
  t_write = now_ms();
  if ((rc = ngs_flush(db)) != NGS_OK) return fail(db, "bench_flush", rc);
  t_flush = now_ms();
  if ((rc = ngs_scan(db, NULL, &it)) != NGS_OK) return fail(db, "bench_scan", rc);
  while (ngs_iter_next(it, &f) == NGS_OK) { scanned++; ngs_free(f); f = NULL; }
  ngs_iter_close(it);
  t_scan = now_ms();
  if ((rc = ngs_verify(db, NULL, 0)) != NGS_OK) return fail(db, "bench_verify", rc);
  t_verify = now_ms();
  printf("{\"ok\":true,\"op\":\"bench\",\"facts\":%lu,\"scanned\":%lu,"
         "\"write_ms\":%.3f,\"flush_ms\":%.3f,\"scan_ms\":%.3f,\"verify_ms\":%.3f,"
         "\"write_per_sec\":%.1f,\"scan_per_sec\":%.1f,\"verify_per_sec\":%.1f}\n",
         n, scanned, t_write - t0, t_flush - t_write, t_scan - t_flush, t_verify - t_scan,
         n / ((t_write - t0) / 1000.0 + 1e-9), scanned / ((t_scan - t_flush) / 1000.0 + 1e-9),
         scanned / ((t_verify - t_scan) / 1000.0 + 1e-9));
  return 0;
}

int main(int argc, char **argv) {
  ngs *db = NULL;
  const char *cmd;
  int rc, out;
  if (argc >= 2 && strcmp(argv[1], "version") == 0) {
    printf("{\"ok\":true,\"op\":\"version\",\"version\":");
    json_cstr(ngs_libversion());
    printf(",\"version_number\":%d,\"header_version\":\"%s\"}\n", ngs_libversion_number(),
           NGS_VERSION);
    return 0;
  }
  if (argc < 3) {
    fprintf(stderr, "usage: ngs_cli <dir> stats|remember|scan|get|verify|recall|bench ...\n");
    return 2;
  }
  cmd = argv[2];
  if ((rc = open_db(argv[1], &db)) != NGS_OK) {
    out = fail(db, "open", rc);
    if (db) ngs_close(db);
    return out;
  }
  if (strcmp(cmd, "stats") == 0) out = cmd_stats(db);
  else if (strcmp(cmd, "remember") == 0) out = cmd_remember(db, argc - 3, argv + 3);
  else if (strcmp(cmd, "scan") == 0) out = cmd_scan(db, argc - 3, argv + 3);
  else if (strcmp(cmd, "get") == 0) out = cmd_get(db, argc > 3 ? argv[3] : NULL);
  else if (strcmp(cmd, "verify") == 0) out = cmd_verify(db);
  else if (strcmp(cmd, "recall") == 0) out = cmd_recall(db, argc - 3, argv + 3);
  else if (strcmp(cmd, "bench") == 0) out = cmd_bench(db, argc > 3 ? argv[3] : NULL);
  else {
    printf("{\"ok\":false,\"error\":\"unknown command\"}\n");
    out = 2;
  }
  ngs_close(db);
  return out;
}
