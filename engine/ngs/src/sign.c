/* SPDX-License-Identifier: Apache-2.0 */
/* sign.c -- Ed25519 wrappers over the vendored orlp/ed25519 (zlib licence). */
#include <stddef.h>
#include <stdint.h>

#include "ngs_int.h"
#include "../third_party/ed25519/ed25519.h"
#include "../third_party/ed25519/ge.h"

void ngs__keypair(uint8_t pk[32], uint8_t sk[64], const uint8_t seed[32]) {
  ed25519_create_keypair(pk, sk, seed);
}

/* The 64-byte secret key is the clamped scalar followed by the hash prefix; the public key is
** scalar * basepoint, exactly as keypair.c computes it. */
void ngs__pub_from_sk(uint8_t pk[32], const uint8_t sk[64]) {
  ge_p3 A;
  ge_scalarmult_base(&A, sk);
  ge_p3_tobytes(pk, &A);
}

void ngs__sign(uint8_t sig[64], const uint8_t msg[32], const uint8_t pk[32], const uint8_t sk[64]) {
  ed25519_sign(sig, msg, 32, pk, sk);
}

int ngs__verify_sig(const uint8_t sig[64], const uint8_t msg[32], const uint8_t pk[32]) {
  return ed25519_verify(sig, msg, 32, pk) == 1;
}
