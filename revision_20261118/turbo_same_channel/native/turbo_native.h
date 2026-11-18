/* SPDX-License-Identifier: AGPL-3.0-or-later */
#ifndef TURBO_SAME_CHANNEL_NATIVE_H
#define TURBO_SAME_CHANNEL_NATIVE_H
#include <stdint.h>
#ifdef _WIN32
#define TURBO_API __declspec(dllexport)
#else
#define TURBO_API
#endif
#define TURBO_A 2048
#define TURBO_MOTHER 6156
#define TURBO_E 4096

TURBO_API void *turbo_create(void);
TURBO_API void turbo_free(void *handle);
TURBO_API int turbo_encode(void *handle, const uint8_t *input, uint8_t *mother);
/* LLR = log(P(bit=0)/P(bit=1)); output has one byte per information bit.
 * Every iteration runs BOTH constituent MAP decoders, without early stopping.
 */
TURBO_API int turbo_decode(void *handle, const float *mother_llr,
                           uint8_t *output, int iterations);
/* All non-create APIs return 0 on success, negative on invalid input/failure. */
TURBO_API int turbo_rate_indices(int *output);
TURBO_API int turbo_rate_encode(const uint8_t *mother, uint8_t *output);
TURBO_API int turbo_rate_recover(const float *input, float *mother_llr);
/* Audit API: zero-start/zero-end constituent; systematic/parity each length+3.
 * All LLR inputs and posterior output use log(P0/P1). */
TURBO_API int turbo_component_map(const float *systematic, const float *parity,
                                  float *posterior, int length);
#endif
