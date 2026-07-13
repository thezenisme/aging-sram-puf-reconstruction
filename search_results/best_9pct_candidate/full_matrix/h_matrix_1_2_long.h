#ifndef H_MAT_1_2_LONG
#define H_MAT_1_2_LONG
#include <stdint.h>
#define N_1_2_LONG 4096
#define K_1_2_LONG 2048
#define M_1_2_LONG 2048
#define EXPANSION_FACTOR_Z 128
extern const uint16_t H_row_indices_1_2_long[2048][64];
extern const uint8_t H_row_degrees_1_2_long[2048];

// Distributed UEP Config
#define NUM_STRONG_ANCHORS 3
static const int STRONG_ANCHOR_COLS[] = { 0, 1280, 2560 };

// LLR Scaling
#define LLR_SCALE_ERASURE 0.0f
#define LLR_SCALE_STRONG  1.0f
#define LLR_SCALE_WEAK    0.6f
extern const uint8_t COL_TYPE_MASK[];
#endif
