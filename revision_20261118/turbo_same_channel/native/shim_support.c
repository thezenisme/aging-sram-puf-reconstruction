/* SPDX-License-Identifier: AGPL-3.0-or-later
 * Minimal scalar support for the unmodified srsLTE release_17_12 sources.
 * Allocation/bit utilities below are local compatibility implementations.
 * Code-block sizes are the four ranges in LTE TS 36.212 Table 5.1.3-3.
 */
#include <stdlib.h>
#include <string.h>
#include "srslte/phy/fec/cbsegm.h"
#include "srslte/phy/fec/tc_interl.h"
#include "srslte/phy/utils/bit.h"

int srslte_cbsegm_cbsize(uint32_t index)
{
  if (index < 60) return 40 + 8 * (int)index;
  if (index < 92) return 528 + 16 * (int)(index - 60);
  if (index < 124) return 1056 + 32 * (int)(index - 92);
  if (index < 188) return 2112 + 64 * (int)(index - 124);
  return SRSLTE_ERROR;
}

int srslte_cbsegm_cbindex(uint32_t length)
{
  for (uint32_t i = 0; i < SRSLTE_NOF_TC_CB_SIZES; ++i)
    if ((uint32_t)srslte_cbsegm_cbsize(i) >= length) return (int)i;
  return SRSLTE_ERROR;
}

int srslte_tc_interl_init(srslte_tc_interl_t *h, uint32_t length)
{
  memset(h, 0, sizeof(*h));
  h->forward = malloc(length * sizeof(*h->forward));
  h->reverse = malloc(length * sizeof(*h->reverse));
  if (!h->forward || !h->reverse) {
    srslte_tc_interl_free(h);
    return SRSLTE_ERROR;
  }
  h->max_long_cb = length;
  return SRSLTE_SUCCESS;
}

void srslte_tc_interl_free(srslte_tc_interl_t *h)
{
  free(h->forward);
  free(h->reverse);
  memset(h, 0, sizeof(*h));
}

static unsigned get_bit(const uint8_t *p, uint32_t bit)
{
  return (p[bit / 8] >> (7 - bit % 8)) & 1U;
}

static void put_bit(uint8_t *p, uint32_t bit, unsigned value)
{
  const unsigned mask = 1U << (7 - bit % 8);
  p[bit / 8] = (uint8_t)((p[bit / 8] & ~mask) | (value ? mask : 0U));
}

void srslte_bit_interleaver_init(srslte_bit_interleaver_t *h,
                               const uint16_t *p, uint32_t length)
{
  /* All callers supply persistent global LUTs. No owned allocation is needed. */
  h->permutation = p;
  h->length = length;
}

void srslte_bit_interleaver_free(srslte_bit_interleaver_t *h)
{
  memset(h, 0, sizeof(*h));
}

void srslte_bit_interleaver_run(srslte_bit_interleaver_t *h, uint8_t *input,
                              uint8_t *output, uint32_t output_offset)
{
  for (uint32_t i = 0; i < h->length; ++i)
    put_bit(output, output_offset + i, get_bit(input, h->permutation[i]));
}

uint32_t srslte_bit_pack(uint8_t **input, int length)
{
  uint32_t value = 0;
  for (int i = 0; i < length; ++i) value = (value << 1) | ((*input)[i] & 1U);
  *input += length;
  return value;
}

void srslte_bit_copy(uint8_t *output, uint32_t output_offset, uint8_t *input,
                     uint32_t input_offset, uint32_t length)
{
  for (uint32_t i = 0; i < length; ++i)
    put_bit(output, output_offset + i, get_bit(input, input_offset + i));
}
