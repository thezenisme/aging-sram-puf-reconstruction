/* SPDX-License-Identifier: AGPL-3.0-or-later
 * Isolated adapter for srsLTE 17.12, commit
 * 8f9ce13b1cb1892ba971dba66f49f6e4e579ecaa. Vendor sources are unchanged.
 */
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include "turbo_native.h"
#include "srslte/phy/fec/turbocoder.h"
#include "srslte/phy/fec/turbodecoder_gen.h"
#include "srslte/phy/fec/rm_turbo.h"

typedef struct {
  srslte_tcod_t encoder;
  srslte_tdec_gen_t decoder;
  float native_llr[TURBO_MOTHER];
} turbo_context;

static INIT_ONCE encoder_once = INIT_ONCE_STATIC_INIT;

static BOOL CALLBACK initialize_encoder(PINIT_ONCE once, PVOID parameter, PVOID *context)
{
  (void)once; (void)parameter; (void)context;
  /* Scalar encode uses the upstream global QPP tables only. They remain valid
   * for the DLL lifetime; context destruction must not free shared tables. */
  srslte_tcod_gentable();
  return TRUE;
}

void *turbo_create(void)
{
  if (!InitOnceExecuteOnce(&encoder_once, initialize_encoder, NULL, NULL)) return NULL;
  turbo_context *h = calloc(1, sizeof(*h));
  if (!h) return NULL;
  h->encoder.max_long_cb = TURBO_A;
  if (srslte_tdec_gen_init(&h->decoder, TURBO_A)) { free(h); return NULL; }
  const int index = srslte_cbsegm_cbindex(TURBO_A);
  if (index != 123 || h->decoder.interleaver[index].forward[1] != 95) {
    turbo_free(h);
    return NULL;
  }
  return h;
}

void turbo_free(void *handle)
{
  turbo_context *h = handle;
  if (!h) return;
  srslte_tdec_gen_free(&h->decoder);
  free(h);
}

int turbo_encode(void *handle, const uint8_t *input, uint8_t *mother)
{
  turbo_context *h = handle;
  if (!h || !input || !mother) return -1;
  for (int i = 0; i < TURBO_A; ++i) if (input[i] > 1) return -1;
  return srslte_tcod_encode(&h->encoder, (uint8_t *)input, mother, TURBO_A);
}

int turbo_decode(void *handle, const float *mother_llr, uint8_t *output, int iterations)
{
  turbo_context *h = handle;
  if (!h || !mother_llr || !output || iterations < 1 || iterations > 1000) return -1;
  for (int i = 0; i < TURBO_MOTHER; ++i) {
    if (!isfinite(mother_llr[i])) return -1;
    h->native_llr[i] = -mother_llr[i];
  }
  if (srslte_tdec_gen_reset(&h->decoder, TURBO_A)) return -2;
  h->decoder.n_iter = 0;
  for (int i = 0; i < iterations; ++i)
    srslte_tdec_gen_iteration(&h->decoder, h->native_llr, TURBO_A);
  srslte_tdec_gen_decision(&h->decoder, output, TURBO_A);
  return 0;
}

int turbo_rate_encode(const uint8_t *mother, uint8_t *output)
{
  uint8_t circular[6240];
  if (!mother || !output) return -1;
  for (int i = 0; i < TURBO_MOTHER; ++i) if (mother[i] > 1) return -1;
  return srslte_rm_turbo_tx(circular, 6240, (uint8_t *)mother,
                            TURBO_MOTHER, output, TURBO_E, 0);
}

int turbo_rate_indices(int *output)
{
  uint8_t mother[TURBO_MOTHER], selected[TURBO_E];
  if (!output) return -1;
  memset(output, 0, TURBO_E * sizeof(*output));
  /* Encode the 13 binary index planes through the unchanged upstream RM.
   * Values are 0/1, so none can collide with its TX_NULL marker of 100. */
  for (int bit = 0; bit < 13; ++bit) {
    for (int i = 0; i < TURBO_MOTHER; ++i) mother[i] = (i >> bit) & 1;
    if (turbo_rate_encode(mother, selected)) return -2;
    for (int i = 0; i < TURBO_E; ++i) output[i] |= (int)selected[i] << bit;
  }
  return 0;
}

int turbo_rate_recover(const float *input, float *mother_llr)
{
  float circular[6240];
  if (!input || !mother_llr) return -1;
  for (int i = 0; i < TURBO_E; ++i)
    if (!isfinite(input[i]) || input[i] == SRSLTE_RX_NULL) return -1;
  for (int i = 0; i < 6240; ++i) circular[i] = SRSLTE_RX_NULL;
  return srslte_rm_turbo_rx(circular, 6240, (float *)input,
                            TURBO_E, mother_llr, TURBO_MOTHER, 0, 0);
}
