#ifndef H_MAT_2_3
#define H_MAT_2_3
#include <stdint.h>
#define N_2_3 768
#define K_2_3 512
#define M_2_3 256
#define EXPANSION_FACTOR_Z 64
extern const uint16_t H_row_indices_2_3[256][64];
extern const uint8_t H_row_degrees_2_3[256];

// Distributed UEP Config
#define NUM_STRONG_ANCHORS 2
static const int STRONG_ANCHOR_COLS[] = { 0, 256 };

// LLR Scaling
#define LLR_SCALE_ERASURE 0.0f
#define LLR_SCALE_STRONG  1.0f
#define LLR_SCALE_WEAK    0.6f
extern const uint8_t COL_TYPE_MASK[];
#endif
