/* SPDX-License-Identifier: AGPL-3.0-or-later */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "turbo_native.h"

static uint32_t rng = 0x9302e9c7U;
static uint32_t random_u32(void)
{
  rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
  return rng;
}

static int component_audit(void)
{
  enum { K = 6 };
  float systematic[K + 3], parity[K + 3], actual[K], best0[K], best1[K];
  for (int trial = 0; trial < 20; ++trial) {
    for (int i = 0; i < K + 3; ++i) {
      systematic[i] = ((int)(random_u32() % 401) - 200) / 73.0f;
      parity[i] = ((int)(random_u32() % 401) - 200) / 89.0f;
    }
    for (int i = 0; i < K; ++i) best0[i] = best1[i] = -1e20f;
    for (unsigned word = 0; word < (1U << K); ++word) {
      unsigned r0 = 0, r1 = 0, r2 = 0;
      float metric = 0.0f;
      for (int t = 0; t < K + 3; ++t) {
        unsigned u = t < K ? ((word >> t) & 1U) : (r2 ^ r1);
        unsigned v = u ^ r2 ^ r1;
        unsigned p = r2 ^ r0 ^ v;
        metric += (u ? -0.5f : 0.5f) * systematic[t];
        metric += (p ? -0.5f : 0.5f) * parity[t];
        r2 = r1; r1 = r0; r0 = v;
      }
      if (r0 || r1 || r2) return 1;
      for (int i = 0; i < K; ++i) {
        float *best = ((word >> i) & 1U) ? &best1[i] : &best0[i];
        if (metric > *best) *best = metric;
      }
    }
    if (turbo_component_map(systematic, parity, actual, K)) return 2;
    for (int i = 0; i < K; ++i)
      if (fabsf(actual[i] - (best0[i] - best1[i])) > 2e-5f) {
        fprintf(stderr, "MAP mismatch trial=%d bit=%d actual=%g exhaustive=%g\n",
                trial, i, actual[i], best0[i] - best1[i]);
        return 3;
      }
  }
  return 0;
}

int main(void)
{
  int indices[TURBO_E], counts[4] = {0}, seen[TURBO_MOTHER] = {0};
  uint8_t input[TURBO_A], mother[TURBO_MOTHER], selected[TURBO_E], decoded[TURBO_A];
  float llr[TURBO_MOTHER], selected_llr[TURBO_E], recovered[TURBO_MOTHER];
  if (component_audit()) return 1;
  if (turbo_rate_indices(indices)) return 2;
  for (int i = 0; i < TURBO_E; ++i) {
    if (indices[i] < 0 || indices[i] >= TURBO_MOTHER || seen[indices[i]]++) return 3;
    counts[indices[i] >= 3 * TURBO_A ? 3 : indices[i] % 3]++;
  }
  if (counts[0] != 1920 || counts[1] != 1084 || counts[2] != 1084 || counts[3] != 8)
    return 4;
  for (int lifetime = 0; lifetime < 2; ++lifetime) {
    void *h = turbo_create();
    if (!h) return 5;
    for (int frame = 0; frame < 24; ++frame) {
      for (int i = 0; i < TURBO_A; ++i)
        input[i] = frame < 2 ? (uint8_t)frame : (uint8_t)(random_u32() & 1U);
      if (turbo_encode(h, input, mother) || turbo_rate_encode(mother, selected)) return 6;
      for (int i = 0; i < TURBO_MOTHER; ++i) llr[i] = mother[i] ? -4.0f : 4.0f;
      if (turbo_decode(h, llr, decoded, 8) || memcmp(input, decoded, TURBO_A)) return 7;
      memset(llr, 0, sizeof(llr));
      for (int i = 0; i < TURBO_E; ++i) {
        if (selected[i] != mother[indices[i]]) return 8;
        selected_llr[i] = selected[i] ? -4.0f : 4.0f;
        llr[indices[i]] = selected_llr[i];
      }
      if (turbo_rate_recover(selected_llr, recovered)) return 9;
      for (int i = 0; i < TURBO_MOTHER; ++i) if (llr[i] != recovered[i]) return 10;
      if (turbo_decode(h, recovered, decoded, 8) || memcmp(input, decoded, TURBO_A)) return 11;
      if (turbo_decode(h, recovered, decoded, 1) || memcmp(input, decoded, TURBO_A)) return 12;
    }
    turbo_free(h);
  }
  puts("PASS: 20 exhaustive 6-bit constituent MAP checks; 4096 unique RV0 indices;");
  puts("PASS: 48 frames (zero/one/random), mother and punctured noiseless decoding;");
  puts("PASS: original rate matching/recovery, repeated contexts, 1 and 8 full iterations.");
  printf("RM data systematic/parity1/parity2/tail = %d/%d/%d/%d\n",
         counts[0], counts[1], counts[2], counts[3]);
  return 0;
}
