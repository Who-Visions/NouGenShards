/* kat_shim.c -- test-only shim: #includes the amalgamation so the test
** suite can run known-answer tests against the internal primitives.
** Never shipped, never linked into the library build. */
#include "../src/nougenshards.c"

void ngs_test_blake3(const uint8_t *in, size_t n, uint8_t out[32]) {
  ngs_blake3_hash(in, n, out);
}
void ngs_test_blake3_chunks(const uint8_t *in, size_t n, const size_t *chunks,
                            size_t nchunks, uint8_t out[32]) {
  ngs_blake3 h;
  size_t off = 0, i;
  ngs_blake3_init(&h);
  for (i = 0; i < nchunks && off < n; i++) {
    size_t c = chunks[i];
    if (c > n - off) c = n - off;
    ngs_blake3_update(&h, in + off, c);
    off += c;
  }
  if (off < n) ngs_blake3_update(&h, in + off, n - off);
  ngs_blake3_final(&h, out, 32);
}
void ngs_test_sha512(const uint8_t *in, size_t n, uint8_t out[64]) {
  ngs_sha512(in, n, out);
}
uint32_t ngs_test_crc32c(const uint8_t *in, size_t n) {
  ngs_crc_init();
  return ngs_crc32c(in, n, 0);
}
void ngs_test_ed_keypair(const uint8_t seed[32], uint8_t pub[32]) {
  ngs_ed_ctx ed;
  ngs_ed_ctx_init(&ed);
  ngs_ed25519_pubkey(&ed, seed, pub);
}
void ngs_test_ed_sign(const uint8_t seed[32], const uint8_t *msg, size_t n, uint8_t sig[64]) {
  ngs_ed_ctx ed;
  ngs_ed_ctx_init(&ed);
  ngs_ed25519_sign(&ed, seed, msg, n, sig);
}
int ngs_test_ed_verify(const uint8_t pub[32], const uint8_t *msg, size_t n, const uint8_t sig[64]) {
  ngs_ed_ctx ed;
  ngs_ed_ctx_init(&ed);
  return ngs_ed25519_verify(&ed, pub, msg, n, sig) ? 1 : 0;
}
