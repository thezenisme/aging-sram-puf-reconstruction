#ifndef LDPC_CONFIG_H
#define LDPC_CONFIG_H

#ifdef TEST_LENGTH_SHORT
    #include "h_matrix_1_2_short.h"
    #include "g_matrix_1_2_short.h"
    #include "puf_profile_short.h"
    #define N N_1_2_SHORT
    #define K K_1_2_SHORT
    #define M M_1_2_SHORT
    #define PUF_N PUF_N_SHORT
    #define G_ROWS G_ROWS_1_2_SHORT
    #define H_row_indices H_row_indices_1_2_short
    #define H_row_degrees H_row_degrees_1_2_short
    #define G_row_indices G_row_indices_1_2_short
    #define G_row_degrees G_row_degrees_1_2_short
    #define LENGTH_SUFFIX "short"
#elif defined(TEST_LENGTH_STANDARD)
    #include "h_matrix_1_2_standard.h"
    #include "g_matrix_1_2_standard.h"
    #include "puf_profile_standard.h"
    #define N N_1_2_STANDARD
    #define K K_1_2_STANDARD
    #define M M_1_2_STANDARD
    #define PUF_N PUF_N_STANDARD
    #define G_ROWS G_ROWS_1_2_STANDARD
    #define H_row_indices H_row_indices_1_2_standard
    #define H_row_degrees H_row_degrees_1_2_standard
    #define G_row_indices G_row_indices_1_2_standard
    #define G_row_degrees G_row_degrees_1_2_standard
    #define LENGTH_SUFFIX "standard"
#elif defined(TEST_LENGTH_MEDIUM)
    #include "h_matrix_1_2_medium.h"
    #include "g_matrix_1_2_medium.h"
    #include "puf_profile_medium.h"
    #define N N_1_2_MEDIUM
    #define K K_1_2_MEDIUM
    #define M M_1_2_MEDIUM
    #define PUF_N PUF_N_MEDIUM
    #define G_ROWS G_ROWS_1_2_MEDIUM
    #define H_row_indices H_row_indices_1_2_medium
    #define H_row_degrees H_row_degrees_1_2_medium
    #define G_row_indices G_row_indices_1_2_medium
    #define G_row_degrees G_row_degrees_1_2_medium
    #define LENGTH_SUFFIX "medium"
#elif defined(TEST_LENGTH_LONG)
    #include "h_matrix_1_2_long.h"
    #include "g_matrix_1_2_long.h"
    #include "puf_profile_long.h"
    #define N N_1_2_LONG
    #define K K_1_2_LONG
    #define M M_1_2_LONG
    #define PUF_N PUF_N_LONG
    #define G_ROWS G_ROWS_1_2_LONG
    #define H_row_indices H_row_indices_1_2_long
    #define H_row_degrees H_row_degrees_1_2_long
    #define G_row_indices G_row_indices_1_2_long
    #define G_row_degrees G_row_degrees_1_2_long
    #define LENGTH_SUFFIX "long"
#elif defined(TEST_LENGTH_XL)
    #include "h_matrix_1_2_xl.h"
    #include "g_matrix_1_2_xl.h"
    #include "puf_profile_xl.h"
    #define N N_1_2_XL
    #define K K_1_2_XL
    #define M M_1_2_XL
    #define PUF_N PUF_N_XL
    #define G_ROWS G_ROWS_1_2_XL
    #define H_row_indices H_row_indices_1_2_xl
    #define H_row_degrees H_row_degrees_1_2_xl
    #define G_row_indices G_row_indices_1_2_xl
    #define G_row_degrees G_row_degrees_1_2_xl
#else
    #error "Please define a test length: TEST_LENGTH_SHORT, STANDARD, LONG or XL"
#endif

#define MAX_ROW_DEGREE 64

#endif // LDPC_CONFIG_H
