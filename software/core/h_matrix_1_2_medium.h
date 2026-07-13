#ifndef H_MAT_1_2_MEDIUM
#define H_MAT_1_2_MEDIUM
#include <stdint.h>
#define N_1_2_MEDIUM 2048
#define K_1_2_MEDIUM 1024
#define M_1_2_MEDIUM 1024
#define EXPANSION_FACTOR_Z 64
extern const uint16_t H_row_indices_1_2_medium[1024][64];
extern const uint8_t H_row_degrees_1_2_medium[1024];

// Distributed UEP Config
#define NUM_STRONG_ANCHORS 3
static const int STRONG_ANCHOR_COLS[] = { 0, 768, 1536 };

// LLR Scaling
#define LLR_SCALE_ERASURE 0.0f
#define LLR_SCALE_STRONG  1.0f
#define LLR_SCALE_WEAK    0.6f
extern const uint8_t COL_TYPE_MASK[];
#endif
