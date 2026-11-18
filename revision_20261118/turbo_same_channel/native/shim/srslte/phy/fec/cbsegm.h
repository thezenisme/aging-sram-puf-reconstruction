#ifndef TURBO_LOCAL_CBSEGM_H
#define TURBO_LOCAL_CBSEGM_H
#include "srslte/config.h"
#define SRSLTE_NOF_TC_CB_SIZES 188
int srslte_cbsegm_cbsize(uint32_t index);
int srslte_cbsegm_cbindex(uint32_t length);
#endif
