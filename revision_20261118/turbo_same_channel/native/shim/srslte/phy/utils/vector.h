#ifndef TURBO_LOCAL_VECTOR_H
#define TURBO_LOCAL_VECTOR_H
#include <stdlib.h>
static inline void *srslte_vec_malloc(size_t bytes) { return malloc(bytes); }
#endif
