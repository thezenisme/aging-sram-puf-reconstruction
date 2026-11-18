#ifndef TURBO_LOCAL_RM_TURBO_H
#define TURBO_LOCAL_RM_TURBO_H
#include "srslte/phy/fec/turbodecoder_gen.h"
#define SRSLTE_TX_NULL 100
#define SRSLTE_RX_NULL 10000
int srslte_rm_turbo_tx(uint8_t *, uint32_t, uint8_t *, uint32_t,
                       uint8_t *, uint32_t, uint32_t);
int srslte_rm_turbo_rx(float *, uint32_t, float *, uint32_t,
                       float *, uint32_t, uint32_t, uint32_t);
#endif
