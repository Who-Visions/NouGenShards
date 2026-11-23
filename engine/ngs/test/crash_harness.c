/* crash_harness.c -- crash + tamper harness for the M1 slice.
**
** Scenarios (run_all executes every one and reports):
**   1. kill-mid-write: a child process appends fsync-acked batches in a
**      loop and is SIGKILLed at a random moment. After reopen, EVERY
**      acknowledged fact must be present and verify must pass.
**   2. torn tail: junk bytes appended at the segment end (a partial write)
**      are truncated on open; the log verifies and all facts survive.
**   3. mid-record truncation: the segment is cut inside a record; open
**      recovers the valid prefix and verify passes on it.
**   4. payload tamper: one flipped payload byte (CRC now wrong) ->
**      verify reports NGS_CORRUPT and appends are refused.
**   5. signature tamper with CRC repaired: the CRC check passes but the
**      Ed25519 check in verify catches it -> NGS_CORRUPT.
**   6. header tamper: a flipped magic byte -> open fails.
**
** Exit status 0 = every scenario behaved as required.
*/
#define _DEFAULT_SOURCE 1
#define _POSIX_C_SOURCE 200809L
#include "../src/nougenshards.c"   /* internals for CRC + record layout */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>

static int g_pass = 0, g_fail = 0;
#define CHECK(cond, name) do { \
    if (cond) { g_pass++; printf("  ok: %s\n", name); } \
    else { g_fail++; printf("  FAIL: %s (%s:%d)\n", name, __FILE__, __LINE__); } \
  } while (0)

static void hex_encode(const uint8_t *in, size_t n, char *out) {
  static const char *H = "0123456789abcdef";
  size_t i;
  for (i = 0; i < n; i++) { out[2 * i] = H[in[i] >> 4]; out[2 * i + 1] = H[in[i] & 15]; }
  out[2 * n] = 0;
}
static int hex_decode(const char *hex, uint8_t *out, size_t n) {
  size_t i;
  for (i = 0; i < n; i++) {
    char a = hex[2 * i], b = hex[2 * i + 1];
    int va = (a >= '0' && a <= '9') ? a - '0' : (a >= 'a' && a <= 'f') ? a - 'a' + 10 : -1;
    int vb = (b >= '0' && b <= '9') ? b - '0' : (b >= 'a' && b <= 'f') ? b - 'a' + 10 : -1;
    if (va < 0 || vb < 0) return -1;
    out[i] = (uint8_t)(va * 16 + vb);
  }
  return 0;
}
static void sh(const char *cmd) { if (system(cmd) != 0) { /* best effort */ } }

/* ---------------- scenario 1: kill mid write ---------------- */

static ngs_str S(const char *z) { ngs_str s; s.p = z; s.n = strlen(z); return s; }

static void writer_child(const char *dir, const char *acks_path) {
  ngs *db = NULL;
  ngs_open_opts oo = NGS_OPEN_OPTS_INIT;
  FILE *acks;
  unsigned batch = 0;
  oo.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  if (ngs_open(dir, &oo, &db) != NGS_OK) _exit(3);
  acks = fopen(acks_path, "a");
  if (!acks) _exit(4);
  for (;;) {
    ngs_fact_in arr[4];
    ngs_id out[4];
    char bodies[4][64];
    char titles[4][32];
    int i;
    for (i = 0; i < 4; i++) {
      snprintf(bodies[i], sizeof bodies[i], "crashfact-%u-%d", batch, i);
      snprintf(titles[i], sizeof titles[i], "crash %u/%d", batch, i);
      arr[i] = (ngs_fact_in)NGS_FACT_IN_INIT;
      arr[i].ns = S("crash");
      arr[i].kind = NGS_SEMANTIC;
      arr[i].title = S(titles[i]);
      arr[i].body = S(bodies[i]);
    }
    if (ngs_remember_many(db, arr, 4, 0, out) != NGS_OK) _exit(5);
    /* remember_many returned => the batch was fsynced (group_commit=0).
    ** Only now acknowledge the ids, durably. */
    for (i = 0; i < 4; i++) {
      char hex[65];
      hex_encode(out[i].b, 32, hex);
      fprintf(acks, "%s %s\n", hex, bodies[i]);
    }
    fflush(acks);
    fsync(fileno(acks));
    batch++;
  }
}

static void scenario_kill_mid_write(const char *work) {
  char dir[1024], acks[1024], cmd[2400];
  pid_t pid;
  int status = 0;
  FILE *f;
  int acked = 0, recovered = 0;
  ngs *db = NULL;

  printf("scenario 1: kill-mid-write\n");
  snprintf(dir, sizeof dir, "%s/crashdb", work);
  snprintf(acks, sizeof acks, "%s/acks.log", work);
  snprintf(cmd, sizeof cmd, "rm -rf '%s' '%s'", dir, acks);
  sh(cmd);

  pid = fork();
  if (pid == 0) { writer_child(dir, acks); _exit(0); }
  /* let it write for a while, then SIGKILL without warning */
  usleep(250000 + (unsigned)(getpid() % 200) * 1000);
  kill(pid, SIGKILL);
  waitpid(pid, &status, 0);
  CHECK(WIFSIGNALED(status) && WTERMSIG(status) == SIGKILL, "writer died by SIGKILL");

  CHECK(ngs_open(dir, NULL, &db) == NGS_OK && db != NULL, "store reopens after kill");
  if (!db) return;
  CHECK(ngs_verify(db, NULL, 0) == NGS_OK, "verify passes after kill");

  f = fopen(acks, "r");
  CHECK(f != NULL, "ack log exists");
  if (f) {
    char line[256];
    while (fgets(line, sizeof line, f)) {
      char hex[65], body[64];
      ngs_id id;
      ngs_fact *fact = NULL;
      if (sscanf(line, "%64s %63s", hex, body) != 2) continue;
      if (hex_decode(hex, id.b, 32) != 0) continue;
      acked++;
      if (ngs_get(db, &id, &fact) == NGS_OK && fact &&
          fact->body.n == strlen(body) &&
          memcmp(fact->body.p, body, fact->body.n) == 0) {
        recovered++;
      }
      if (fact) ngs_free(fact);
    }
    fclose(f);
  }
  printf("  acked=%d recovered=%d\n", acked, recovered);
  CHECK(acked > 0, "writer acknowledged at least one batch");
  CHECK(recovered == acked, "every acknowledged fact recovered intact");
  ngs_close(db);
}

/* ---------------- shared prep for tamper scenarios ---------------- */

static int prep_store(const char *dir, ngs_id *first_id) {
  ngs *db = NULL;
  ngs_open_opts oo = NGS_OPEN_OPTS_INIT;
  int i;
  oo.flags = NGS_OPEN_READWRITE | NGS_OPEN_CREATE;
  if (ngs_open(dir, &oo, &db) != NGS_OK) return -1;
  for (i = 0; i < 6; i++) {
    char body[64];
    ngs_fact_in in = NGS_FACT_IN_INIT;
    ngs_id id;
    snprintf(body, sizeof body, "tamper target fact %d with some body bytes", i);
    in.ns = S("tamper");
    in.kind = NGS_SEMANTIC;
    in.title = S("t");
    in.body = S(body);
    if (ngs_remember(db, &in, 0, &id) != NGS_OK) { ngs_close(db); return -1; }
    if (i == 0 && first_id) *first_id = id;
  }
  if (ngs_close(db) != NGS_OK) return -1;
  return 0;
}

static void seg_path(const char *dir, char *out, size_t n) {
  snprintf(out, n, "%s/log/000001.seg", dir);
}
static uint8_t *read_file(const char *path, size_t *len) {
  FILE *f = fopen(path, "rb");
  uint8_t *buf;
  long n;
  if (!f) return NULL;
  fseek(f, 0, SEEK_END);
  n = ftell(f);
  fseek(f, 0, SEEK_SET);
  buf = (uint8_t *)malloc((size_t)n);
  if (!buf) { fclose(f); return NULL; }
  if (n > 0 && fread(buf, 1, (size_t)n, f) != (size_t)n) { free(buf); fclose(f); return NULL; }
  fclose(f);
  *len = (size_t)n;
  return buf;
}
static int write_file(const char *path, const uint8_t *buf, size_t len) {
  FILE *f = fopen(path, "wb");
  if (!f) return -1;
  if (len && fwrite(buf, 1, len, f) != len) { fclose(f); return -1; }
  fclose(f);
  return 0;
}
static void copy_store(const char *work, const char *name, char *dir_out, size_t n) {
  char cmd[2400];
  snprintf(dir_out, n, "%s/%s", work, name);
  snprintf(cmd, sizeof cmd, "cp -r '%s/base' '%s'", work, dir_out);
  sh(cmd);
}

/* ---------------- scenarios 2..6 ---------------- */

static void scenario_torn_tail(const char *work) {
  char dir[1024], sp[1080];
  ngs *db = NULL;
  FILE *f;
  static const uint8_t junk[10] = {0xFF, 0xFF, 0xFF, 0x7F, 0x01, 'x', 'x', 'x', 'x', 'x'};
  ngs_fact *fact = NULL;

  printf("scenario 2: torn tail\n");
  copy_store(work, "torn", dir, sizeof dir);
  seg_path(dir, sp, sizeof sp);
  f = fopen(sp, "ab");
  CHECK(f != NULL, "torn: segment open for append");
  if (f) { fwrite(junk, 1, sizeof junk, f); fclose(f); }
  CHECK(ngs_open(dir, NULL, &db) == NGS_OK && db != NULL, "torn: open truncates junk tail");
  if (!db) return;
  CHECK(ngs_verify(db, NULL, 0) == NGS_OK, "torn: verify passes");
  {
    ngs_iter *it = NULL;
    int count = 0;
    ngs_scan_opts so = NGS_SCAN_OPTS_INIT;
    so.ns = S("tamper");
    if (ngs_scan(db, &so, &it) == NGS_OK) {
      while (ngs_iter_next(it, &fact) == NGS_OK) { count++; ngs_free(fact); fact = NULL; }
      ngs_iter_close(it);
    }
    CHECK(count == 6, "torn: all 6 facts survive");
  }
  ngs_close(db);
}

static void scenario_mid_truncate(const char *work) {
  char dir[1024], sp[1080];
  ngs *db = NULL;
  ngs_iter *it = NULL;
  ngs_fact *fact = NULL;
  int count = 0;

  printf("scenario 3: mid-record truncation\n");
  copy_store(work, "midtrunc", dir, sizeof dir);
  seg_path(dir, sp, sizeof sp);
  /* keep the 64-byte header + a slice of the first record */
  CHECK(truncate(sp, 64 + 15) == 0, "midtrunc: file truncated inside record 1");
  CHECK(ngs_open(dir, NULL, &db) == NGS_OK && db != NULL, "midtrunc: open recovers prefix");
  if (!db) return;
  CHECK(ngs_verify(db, NULL, 0) == NGS_OK, "midtrunc: verify passes on the prefix");
  if (ngs_scan(db, NULL, &it) == NGS_OK) {
    while (ngs_iter_next(it, &fact) == NGS_OK) { count++; ngs_free(fact); fact = NULL; }
    ngs_iter_close(it);
  }
  CHECK(count == 0, "midtrunc: no complete facts in the prefix");
  ngs_close(db);
}

static void scenario_payload_tamper(const char *work) {
  char dir[1024], sp[1080];
  uint8_t *buf;
  size_t len = 0;
  ngs *db = NULL;
  ngs_id id;
  ngs_fact_in in = NGS_FACT_IN_INIT;

  printf("scenario 4: payload tamper (CRC catches it)\n");
  copy_store(work, "paytamper", dir, sizeof dir);
  seg_path(dir, sp, sizeof sp);
  buf = read_file(sp, &len);
  CHECK(buf != NULL && len > 100, "paytamper: segment read");
  if (!buf) return;
  buf[64 + 5 + 20] ^= 0xFF;   /* inside the first record's payload */
  CHECK(write_file(sp, buf, len) == 0, "paytamper: segment rewritten");
  free(buf);
  CHECK(ngs_open(dir, NULL, &db) == NGS_OK && db != NULL, "paytamper: open keeps the valid prefix");
  if (!db) return;
  CHECK(ngs_verify(db, NULL, 0) == NGS_CORRUPT, "paytamper: verify -> CORRUPT");
  in.ns = S("tamper");
  in.kind = NGS_SEMANTIC;
  in.title = S("t");
  in.body = S("must not land");
  CHECK(ngs_remember(db, &in, 0, &id) == NGS_CORRUPT, "paytamper: appends refused with CORRUPT");
  ngs_close(db);
}

static void scenario_sig_tamper(const char *work) {
  char dir[1024], sp[1080];
  uint8_t *buf;
  size_t len = 0, pos, last_start = 0, last_len = 0;
  ngs *db = NULL;

  printf("scenario 5: signature tamper with CRC repaired (Ed25519 catches it)\n");
  copy_store(work, "sigtamper", dir, sizeof dir);
  seg_path(dir, sp, sizeof sp);
  buf = read_file(sp, &len);
  CHECK(buf != NULL && len > 100, "sigtamper: segment read");
  if (!buf) return;
  /* walk to the last record */
  pos = 64;
  while (pos + 9 <= len) {
    uint32_t rl;
    ngs_load32le(buf + pos, &rl);
    if (pos + 4 + 1 + rl + 4 > len) break;
    last_start = pos;
    last_len = rl;
    pos += 4 + 1 + rl + 4;
  }
  CHECK(last_len > 80, "sigtamper: found the last record");
  /* flip a byte inside the signature (near the payload tail), then repair
  ** the record CRC so only the signature check can catch it */
  buf[last_start + 5 + last_len - 10] ^= 0x01;
  {
    uint32_t crc = ngs_crc32c(buf + last_start + 4, 1 + last_len, 0);
    ngs_store32le(buf + last_start + 5 + last_len, crc);
  }
  CHECK(write_file(sp, buf, len) == 0, "sigtamper: segment rewritten");
  free(buf);
  CHECK(ngs_open(dir, NULL, &db) == NGS_OK && db != NULL, "sigtamper: open ok (CRC valid)");
  if (!db) return;
  CHECK(ngs_verify(db, NULL, 0) == NGS_CORRUPT, "sigtamper: verify -> CORRUPT via signature");
  ngs_close(db);
}

static void scenario_header_tamper(const char *work) {
  char dir[1024], sp[1080];
  uint8_t *buf;
  size_t len = 0;
  ngs *db = NULL;

  printf("scenario 6: header tamper\n");
  copy_store(work, "hdrtamper", dir, sizeof dir);
  seg_path(dir, sp, sizeof sp);
  buf = read_file(sp, &len);
  CHECK(buf != NULL && len > 64, "hdrtamper: segment read");
  if (!buf) return;
  buf[0] ^= 0xFF;   /* magic */
  CHECK(write_file(sp, buf, len) == 0, "hdrtamper: segment rewritten");
  free(buf);
  /* engine contract: open serves the valid prefix (here: empty) with the
  ** corruption sticky -- verify reports it and appends refuse. */
  CHECK(ngs_open(dir, NULL, &db) == NGS_OK && db != NULL, "hdrtamper: open keeps the valid prefix");
  if (db) {
    ngs_id id;
    ngs_fact_in in = NGS_FACT_IN_INIT;
    in.ns = S("tamper");
    in.kind = NGS_SEMANTIC;
    in.title = S("t");
    in.body = S("must not land");
    CHECK(ngs_verify(db, NULL, 0) == NGS_CORRUPT, "hdrtamper: verify -> CORRUPT");
    CHECK(ngs_remember(db, &in, 0, &id) == NGS_CORRUPT, "hdrtamper: appends refused with CORRUPT");
    ngs_close(db);
  }
}

int main(int argc, char **argv) {
  char work[512], base[1024], cmd[2400];
  ngs_id first;
  (void)argc; (void)argv;
  snprintf(work, sizeof work, "/tmp/ngs-crash-XXXXXX");
  if (!mkdtemp(work)) { perror("mkdtemp"); return 2; }
  printf("crash harness workdir: %s\n", work);

  scenario_kill_mid_write(work);

  snprintf(base, sizeof base, "%s/base", work);
  if (prep_store(base, &first) != 0) {
    printf("FAIL: could not prepare the base store\n");
    return 1;
  }
  scenario_torn_tail(work);
  scenario_mid_truncate(work);
  scenario_payload_tamper(work);
  scenario_sig_tamper(work);
  scenario_header_tamper(work);

  printf("CRASH HARNESS: %d passed, %d failed\n", g_pass, g_fail);
  snprintf(cmd, sizeof cmd, "rm -rf '%s'", work);
  sh(cmd);
  return g_fail == 0 ? 0 : 1;
}
