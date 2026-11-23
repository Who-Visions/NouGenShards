/* crypto_vec.c -- reads "op hexarg..." lines on stdin, prints hex results, so
** test/crypto_oracle.py can compare against independent implementations. */
#include "../src/ngs_internal.h"
#include <stdio.h>

static size_t unhex(const char *s, uint8_t *out) {
  size_t n = 0;
  unsigned v;
  while (s[0] && s[1] && sscanf(s, "%2x", &v) == 1) { out[n++] = (uint8_t)v; s += 2; }
  return n;
}
static void hex(const uint8_t *p, size_t n) { size_t i; for (i = 0; i < n; i++) printf("%02x", p[i]); }

static uint8_t a[1 << 20], b[1 << 20], c[64];
static char line[(1 << 22)];
int main(void) {
  char op[16], x[1 << 21], y[256], z[256];
  while (fgets(line, sizeof line, stdin)) {
    int k = sscanf(line, "%15s %2097151s %255s %255s", op, x, y, z);
    size_t n = (k >= 2 && strcmp(x, "-") != 0) ? unhex(x, a) : 0;
    if (!strcmp(op, "blake3")) { ngs__blake3_hash(a, n, c); hex(c, 32); }
    else if (!strcmp(op, "blake3inc")) {   /* same input, fed in 7-byte pieces */
      ngs__blake3 h; size_t i; ngs__blake3_init(&h);
      for (i = 0; i < n; i += 7) ngs__blake3_update(&h, a + i, n - i < 7 ? n - i : 7);
      ngs__blake3_final(&h, c); hex(c, 32);
    }
    else if (!strcmp(op, "sha512")) { ngs__sha512(a, n, c); hex(c, 64); }
    else if (!strcmp(op, "crc32c")) { printf("%08x", (unsigned)ngs__crc32c(0, a, n)); }
    else if (!strcmp(op, "pub")) { uint8_t pk[32]; unhex(y, b); ngs__ed25519_pubkey(b, pk); hex(pk, 32); }
    else if (!strcmp(op, "sign")) {   /* sign msg seed */
      uint8_t pk[32], sig[64]; unhex(y, b); ngs__ed25519_pubkey(b, pk);
      ngs__ed25519_sign(sig, a, n, b, pk); hex(sig, 64);
    }
    else if (!strcmp(op, "verify")) { /* verify msg sig pk */
      uint8_t sig[64], pk[32]; unhex(y, sig); unhex(z, pk);
      printf("%d", ngs__ed25519_verify(sig, a, n, pk));
    }
    printf("\n");
    fflush(stdout);
  }
  return 0;
}
