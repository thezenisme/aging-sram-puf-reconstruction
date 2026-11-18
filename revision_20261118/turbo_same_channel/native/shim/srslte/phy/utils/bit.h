#ifndef TURBO_LOCAL_BIT_H
#define TURBO_LOCAL_BIT_H
#include "srslte/config.h"
typedef struct {
  const uint16_t *permutation;
  uint32_t length;
} srslte_bit_interleaver_t;
void srslte_bit_interleaver_init(srslte_bit_interleaver_t *, const uint16_t *, uint32_t);
void srslte_bit_interleaver_free(srslte_bit_interleaver_t *);
void srslte_bit_interleaver_run(srslte_bit_interleaver_t *, uint8_t *, uint8_t *, uint32_t);
uint32_t srslte_bit_pack(uint8_t **, int);
void srslte_bit_copy(uint8_t *, uint32_t, uint8_t *, uint32_t, uint32_t);
#endif
